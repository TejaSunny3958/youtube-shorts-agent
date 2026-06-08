import yt_dlp
import os
import json
import imageio_ffmpeg


def _ffmpeg_bin() -> str:
    """Return the bundled ffmpeg executable path."""
    return imageio_ffmpeg.get_ffmpeg_exe()


class VideoDownloader:
    def __init__(self, output_dir: str = "outputs/downloads"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def _meta_cache_path(self, video_id: str) -> str:
        return os.path.join(self.output_dir, f"{video_id}.meta.json")

    def _save_meta(self, video_id: str, info: dict):
        try:
            keep = {k: info.get(k) for k in ("id", "title", "duration", "description", "chapters")}
            with open(self._meta_cache_path(video_id), "w", encoding="utf-8") as f:
                json.dump(keep, f, ensure_ascii=False)
        except Exception:
            pass

    def _load_meta(self, video_id: str) -> dict | None:
        path = self._meta_cache_path(video_id)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def download(self, url: str) -> dict:
        """Download a YouTube video and return metadata + file path.

        Forces max 720p to keep FFmpeg processing fast.
        If a cached file already exists it is reused.
        """
        ydl_opts = {
            # Force H.264 (avc1) at ≤720p — AV1/VP9 are much slower to decode
            "format": (
                "bestvideo[height<=720][vcodec^=avc1]+bestaudio[ext=m4a]"
                "/bestvideo[height<=720][vcodec^=avc]+bestaudio[ext=m4a]"
                "/bestvideo[height<=720][ext=mp4][vcodec!*=av01][vcodec!*=vp9]+bestaudio[ext=m4a]"
                "/best[height<=720][ext=mp4]"
                "/best"
            ),
            "outtmpl": os.path.join(self.output_dir, "%(id)s.%(ext)s"),
            "merge_output_format": "mp4",
            "ffmpeg_location": _ffmpeg_bin(),
            # Use browser cookies to bypass YouTube bot-detection
            "cookiesfrombrowser": ("chrome",),
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)  # fetch metadata first
            video_id = info.get("id", "unknown")
            file_path = os.path.join(self.output_dir, f"{video_id}.mp4")

            # Reuse cached download to skip a potentially long download
            if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                ydl.download([url])

            title = info.get("title", "unknown")
            duration = info.get("duration", 0)
            description = info.get("description", "")
            chapters = info.get("chapters") or []

            # Cache metadata so future re-runs skip the network call
            self._save_meta(video_id, info)

        return {
            "video_id": video_id,
            "title": title,
            "duration": duration,
            "description": description,
            "chapters": chapters,
            "file_path": file_path,
        }

    def download_with_cache(self, url: str) -> dict:
        """
        Like download() but checks for a cached video + metadata first.
        If both exist, skips all YouTube network calls entirely.
        """
        # Try to derive video_id from the URL cheaply
        import re
        m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
        if m:
            video_id = m.group(1)
            file_path = os.path.join(self.output_dir, f"{video_id}.mp4")
            meta = self._load_meta(video_id)
            if meta and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                return {
                    "video_id": video_id,
                    "title": meta.get("title", "unknown"),
                    "duration": meta.get("duration", 0),
                    "description": meta.get("description", ""),
                    "chapters": meta.get("chapters") or [],
                    "file_path": file_path,
                }
        # No cache hit — fall through to full download
        return self.download(url)

    def get_info(self, url: str) -> dict:
        """Get video info without downloading."""
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return info
