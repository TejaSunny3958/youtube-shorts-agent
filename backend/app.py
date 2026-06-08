import os
import re
import time
import uuid
import threading
import logging

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

import db
from processors.downloader import VideoDownloader
from processors.analyzer import VideoAnalyzer
from processors.gemini_analyzer import GeminiAnalyzer
from processors.clipper import VideoClipper
from processors.effects import VideoEffects
from processors.transcriber import Transcriber

app = Flask(__name__)
CORS(app, origins="*")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(__file__)
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
SHORTS_DIR = os.path.join(OUTPUTS_DIR, "shorts")
DOWNLOADS_DIR = os.path.join(OUTPUTS_DIR, "downloads")
MUSIC_DIR = os.path.join(BASE_DIR, "assets", "music")

os.makedirs(SHORTS_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(MUSIC_DIR, exist_ok=True)

db.init_db()

# ---------------------------------------------------------------------------
# In-memory task registry
# ---------------------------------------------------------------------------
_tasks: dict = {}
_tasks_lock = threading.Lock()

transcriber = Transcriber(model_size="base")
gemini = GeminiAnalyzer()  # reads GOOGLE_API_KEY from env


def _set_task(task_id: str, **kwargs):
    with _tasks_lock:
        current = _tasks.get(task_id, {})
        current.update(kwargs)
        if "_created" not in current:
            current["_created"] = time.time()
        _tasks[task_id] = current


def _cleanup_tasks():
    """Remove completed/error tasks older than 30 minutes."""
    cutoff = time.time() - 1800
    with _tasks_lock:
        stale = [
            k for k, v in _tasks.items()
            if v.get("status") in ("done", "error")
            and v.get("_created", 0) < cutoff
        ]
        for k in stale:
            del _tasks[k]


def _get_music_file():
    exts = (".mp3", ".wav", ".aac", ".m4a", ".ogg")
    for fname in os.listdir(MUSIC_DIR):
        if fname.lower().endswith(exts):
            return os.path.join(MUSIC_DIR, fname)
    return None


# ---------------------------------------------------------------------------
# Background processing task
# ---------------------------------------------------------------------------

def _process_task(task_id: str, url: str):
    def prog(stage: str, message: str, percent: int):
        _set_task(task_id, status="processing", stage=stage,
                  message=message, percent=percent)
        logger.info("[%s] %s – %s (%d%%)", task_id[:8], stage, message, percent)

    try:
        # 1. Download
        prog("download", "Downloading video…", 5)
        downloader = VideoDownloader(output_dir=DOWNLOADS_DIR)
        video_info = downloader.download_with_cache(url)

        # 2. Transcribe (optional)
        all_captions = []
        if transcriber.available():
            prog("transcribe", "Transcribing audio…", 20)

            def _transcribe_progress(pct: int):
                msg = f"Transcribing… {pct}%" if pct < 100 else "Transcription done"
                _set_task(task_id, status="processing", stage="transcribe",
                          message=msg, percent=20 + int(pct * 0.13))

            all_captions = transcriber.transcribe_video(
                video_info["file_path"], progress_cb=_transcribe_progress
            )
        else:
            prog("transcribe", "Whisper not available – skipping captions", 20)

        # 3. Analyse — Gemini first, rule-based fallback
        prog("analyze", "Asking Gemini to pick best moments…", 35)
        if gemini.available():
            segments = gemini.analyze(video_info, transcription=all_captions)
            if not segments:
                logger.info("Gemini returned 0 segments, falling back to rule-based")
        else:
            segments = []

        if not segments:
            prog("analyze", "Selecting best moments (rule-based)…", 38)
            analyzer = VideoAnalyzer()
            segments = analyzer.analyze(video_info, transcription=all_captions)

        # Generate viral AI titles (best-effort)
        ai_titles: dict = {}
        if gemini.available() and segments:
            try:
                ai_titles = gemini.generate_titles(
                    video_info.get("title", ""),
                    segments,
                    transcription=all_captions,
                )
            except Exception:
                pass

        # 4. Clip + effects + captions + music
        music_file = _get_music_file()
        effects_proc = VideoEffects(output_dir=SHORTS_DIR)
        clipper = VideoClipper(output_dir=SHORTS_DIR)
        total = len(segments)

        for i, seg in enumerate(segments):
            pct = 40 + int((i / max(total, 1)) * 55)
            prog("clip", f"Clipping short {i + 1}/{total}…", pct)

            effect_name, extra_vf = effects_proc.get_effect_filter(
                i, seg.get("duration", 30)
            )

            caps = (
                transcriber.clip_captions(all_captions, seg["start"], seg["end"])
                if all_captions
                else []
            )
            subs_file = transcriber.write_ass(caps) if caps else None

            try:
                out_path = clipper.clip_single(
                    video_info["file_path"],
                    seg["start"],
                    seg["end"],
                    video_info["video_id"],
                    seg["rank"],
                    extra_vf=extra_vf,
                    subs_file=subs_file,
                    music_file=music_file,
                )
                seg["clip_path"] = out_path
                seg["effect"] = effect_name
            except Exception as exc:
                logger.error("Clip failed rank=%d: %s", seg["rank"], exc)
                seg["clip_path"] = None
                seg["effect"] = "none"

        # 5. Build response & save history
        prog("done", "Finalising…", 95)
        response_shorts = []
        for seg in segments:
            clip_file = os.path.basename(seg.get("clip_path") or "")
            response_shorts.append(
                {
                    "rank": seg["rank"],
                    "label": seg["label"],
                    "ai_title": ai_titles.get(seg["rank"], ""),
                    "start": seg["start"],
                    "end": seg["end"],
                    "duration": seg["duration"],
                    "score": seg["score"],
                    "effect": seg.get("effect", "none"),
                    "clip_file": clip_file,
                    "download_url": f"/api/shorts/{clip_file}" if clip_file else None,
                    "is_best": seg["rank"] == 1,
                    "has_captions": bool(all_captions),
                    "has_music": bool(music_file),
                    "source": seg.get("source", "rule"),
                }
            )

        result = {
            "video_id": video_info["video_id"],
            "title": video_info["title"],
            "duration": video_info["duration"],
            "total_shorts": len(response_shorts),
            "shorts": response_shorts,
        }

        db.save_result(
            video_info["video_id"],
            video_info["title"],
            video_info["duration"],
            url,
            response_shorts,
        )

        _set_task(task_id, status="done", percent=100,
                  stage="done", message="Done!", result=result)

    except Exception as exc:
        logger.exception("Task %s failed", task_id[:8])
        _set_task(task_id, status="error", error=str(exc))


# ---------------------------------------------------------------------------
# Routes – processing
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/process", methods=["POST"])
def process_video():
    data = request.get_json(force=True) or {}
    url = data.get("url", "").strip()

    if not url:
        return jsonify({"error": "url is required"}), 400
    if "youtube.com" not in url and "youtu.be" not in url:
        return jsonify({"error": "Only YouTube URLs are supported"}), 400

    _cleanup_tasks()
    task_id = str(uuid.uuid4())
    _set_task(task_id, status="queued", stage="queued",
              message="Queued…", percent=0)
    t = threading.Thread(target=_process_task, args=(task_id, url), daemon=True)
    t.start()
    return jsonify({"task_id": task_id})


@app.route("/api/status/<task_id>")
def task_status(task_id: str):
    with _tasks_lock:
        task = dict(_tasks.get(task_id, {"status": "not_found"}))
    return jsonify(task)


# ---------------------------------------------------------------------------
# Routes – serve clips
# ---------------------------------------------------------------------------

@app.route("/api/shorts/<path:filename>")
def serve_short(filename: str):
    safe = os.path.basename(filename)
    resp = send_from_directory(SHORTS_DIR, safe)
    resp.headers["Accept-Ranges"] = "bytes"
    return resp


# ---------------------------------------------------------------------------
# Routes – history
# ---------------------------------------------------------------------------

@app.route("/api/history")
def history():
    return jsonify(db.get_history())


# ---------------------------------------------------------------------------
# Route – remix a single clip (toggle music on/off)
# ---------------------------------------------------------------------------

@app.route("/api/remix", methods=["POST"])
def remix_clip():
    """
    Re-render a single clip with music toggled on or off.
    Body: { clip_file, add_music: bool }
    Returns: { clip_file, download_url }
    """
    data = request.get_json(force=True) or {}
    clip_file = os.path.basename(data.get("clip_file", ""))
    add_music = bool(data.get("add_music", True))
    music_volume = max(0.0, min(1.0, float(data.get("music_volume", 0.15))))

    src = os.path.join(SHORTS_DIR, clip_file)
    if not clip_file or not os.path.exists(src):
        return jsonify({"error": "clip not found"}), 404

    # Strip any previous _music/_nomusic suffix before adding new one
    base = re.sub(r"_(music|nomusic)$", "", clip_file.rsplit(".", 1)[0])
    suffix = "_music" if add_music else "_nomusic"
    out_name = base + suffix + ".mp4"
    out_path = os.path.join(SHORTS_DIR, out_name)

    if os.path.exists(out_path):
        return jsonify({"clip_file": out_name,
                        "download_url": f"/api/shorts/{out_name}"})

    try:
        music_file = _get_music_file() if add_music else None
        if add_music and not music_file:
            return jsonify({"error": "No music file found in assets/music/"}), 422

        import imageio_ffmpeg
        import subprocess as _sp
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        if add_music:
            cmd = [
                ffmpeg, "-y",
                "-i", src,
                "-stream_loop", "-1", "-i", music_file,
                "-filter_complex",
                f"[0:a]volume=1.0[va];[1:a]volume={music_volume:.2f}[ma];[va][ma]amix=inputs=2:duration=first[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest", out_path,
            ]
        else:
            cmd = [
                ffmpeg, "-y", "-i", src,
                "-map", "0:v", "-map", "0:a",
                "-c:v", "copy", "-c:a", "aac",
                out_path,
            ]

        res = _sp.run(cmd, capture_output=True)
        if res.returncode != 0:
            err = res.stderr.decode(errors="replace")[-600:]
            logger.error("remix failed: %s", err)
            return jsonify({"error": err}), 500

        return jsonify({"clip_file": out_name,
                        "download_url": f"/api/shorts/{out_name}"})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/history/<video_id>")
def history_detail(video_id: str):
    data = db.get_video_shorts(video_id)
    if not data:
        return jsonify({"error": "not found"}), 404
    for s in data.get("shorts", []):
        if s.get("clip_file") and not s.get("download_url"):
            s["download_url"] = f"/api/shorts/{s['clip_file']}"
    return jsonify(data)


# ---------------------------------------------------------------------------
# Routes – YouTube upload
# ---------------------------------------------------------------------------

@app.route("/api/youtube/auth")
def yt_auth():
    try:
        from processors.uploader import get_auth_url, secrets_available
        if not secrets_available():
            return jsonify(
                {
                    "error": (
                        "client_secrets.json not found. Download it from "
                        "Google Cloud Console (YouTube Data API v3 → OAuth 2.0 credentials) "
                        "and place it in the backend/ folder."
                    )
                }
            ), 503
        redirect_uri = request.host_url.rstrip("/") + "/api/youtube/callback"
        return jsonify({"auth_url": get_auth_url(redirect_uri)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/youtube/callback")
def yt_callback():
    code = request.args.get("code", "")
    if not code:
        return "<p>Error: no code received.</p>", 400
    try:
        from processors.uploader import exchange_code
        redirect_uri = request.host_url.rstrip("/") + "/api/youtube/callback"
        exchange_code(code, redirect_uri)
        return (
            "<html><body style='font-family:sans-serif;text-align:center;margin-top:80px'>"
            "<h2>✅ YouTube connected!</h2>"
            "<p>You can close this tab and return to the app.</p>"
            "<script>setTimeout(()=>window.close(),2000)</script>"
            "</body></html>"
        )
    except Exception as exc:
        return f"<p>Error: {exc}</p>", 500


@app.route("/api/youtube/upload", methods=["POST"])
def yt_upload():
    data = request.get_json(force=True) or {}
    clip_file = os.path.basename(data.get("clip_file", ""))
    title = data.get("title", "Short")

    if not clip_file:
        return jsonify({"error": "clip_file is required"}), 400

    file_path = os.path.join(SHORTS_DIR, clip_file)
    if not os.path.exists(file_path):
        return jsonify({"error": f"{clip_file} not found on server"}), 404

    try:
        from processors.uploader import upload_short, get_saved_credentials
        if get_saved_credentials() is None:
            return jsonify(
                {"error": "Not authenticated. Open /api/youtube/auth first."}
            ), 401
        yt_url = upload_short(file_path, title)
        return jsonify({"url": yt_url})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
