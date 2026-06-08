"""
Optional Whisper-based transcription and ASS subtitle generation.

Uses faster-whisper (CTranslate2) if installed — ~10x faster on CPU.
Falls back to openai-whisper, then gracefully returns [] if neither is available.
"""
import json
import os
import subprocess
import tempfile
from typing import List, Dict, Optional, Callable

import imageio_ffmpeg


def _ffmpeg():
    return imageio_ffmpeg.get_ffmpeg_exe()


class Transcriber:
    def __init__(self, model_size: str = "tiny"):
        self.model_size = model_size
        self._model = None
        self._fw_model = None

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def available(self) -> bool:
        try:
            from faster_whisper import WhisperModel  # noqa: F401
            return True
        except ImportError:
            pass
        try:
            import whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def transcribe_video(
        self,
        video_path: str,
        progress_cb: Optional[Callable[[int], None]] = None,
    ) -> List[Dict]:
        """
        Return [{start, end, text}] for the entire video.
        Returns [] if no whisper backend is available or transcription fails.

        progress_cb(pct: int) is called with 0-100 as transcription proceeds.
        """
        if not self.available():
            return []
        try:
            audio_path = video_path.rsplit(".", 1)[0] + "_16k.wav"
            transcript_cache = video_path.rsplit(".", 1)[0] + "_transcript.json"

            # Return cached transcript if it exists
            if os.path.exists(transcript_cache):
                if progress_cb:
                    progress_cb(100)
                with open(transcript_cache, encoding="utf-8") as f:
                    return json.load(f)

            # Extract 16kHz mono WAV if not yet cached
            if not os.path.exists(audio_path):
                proc = subprocess.run(
                    [
                        _ffmpeg(), "-y", "-i", video_path,
                        "-vn", "-ar", "16000", "-ac", "1",
                        "-f", "wav", audio_path,
                    ],
                    capture_output=True,
                )
                if proc.returncode != 0:
                    raise RuntimeError(
                        proc.stderr.decode(errors="replace")[-400:]
                    )

            # ── Try faster-whisper (preferred) ─────────────────────────
            segments = self._transcribe_faster(audio_path, progress_cb)

            # ── Fall back to openai-whisper ─────────────────────────────
            if segments is None:
                segments = self._transcribe_openai(audio_path)

            if segments is None:
                return []

            # Cache transcript so future runs are instant
            try:
                with open(transcript_cache, "w", encoding="utf-8") as f:
                    json.dump(segments, f, ensure_ascii=False)
            except Exception:
                pass

            return segments

        except Exception as exc:
            print(f"[transcriber] transcription failed: {exc}")
            return []

    def _transcribe_faster(
        self,
        audio_path: str,
        progress_cb: Optional[Callable[[int], None]],
    ) -> Optional[List[Dict]]:
        try:
            from faster_whisper import WhisperModel
            if self._fw_model is None:
                self._fw_model = WhisperModel(
                    self.model_size, device="cpu", compute_type="int8"
                )
            fw_segments, info = self._fw_model.transcribe(
                audio_path, beam_size=1, vad_filter=True
            )
            total = max(info.duration or 1.0, 1.0)
            result = []
            for seg in fw_segments:
                result.append({
                    "start": float(seg.start),
                    "end": float(seg.end),
                    "text": seg.text.strip(),
                })
                if progress_cb:
                    pct = int(min(99, seg.end / total * 100))
                    progress_cb(pct)
            if progress_cb:
                progress_cb(100)
            return result
        except ImportError:
            return None
        except Exception as exc:
            print(f"[transcriber] faster-whisper failed: {exc}")
            return None

    def _transcribe_openai(self, audio_path: str) -> Optional[List[Dict]]:
        try:
            import numpy as np
            from scipy.io import wavfile

            rate, data = wavfile.read(audio_path)
            if data.dtype == __import__('numpy').int16:
                audio = data.astype(np.float32) / 32768.0
            elif data.dtype == __import__('numpy').int32:
                audio = data.astype(np.float32) / 2147483648.0
            else:
                audio = data.astype(np.float32)

            model = self._get_model()
            result = model.transcribe(audio, verbose=False, fp16=False)
            return [
                {
                    "start": float(s["start"]),
                    "end": float(s["end"]),
                    "text": s["text"].strip(),
                }
                for s in result.get("segments", [])
            ]
        except Exception as exc:
            print(f"[transcriber] openai-whisper failed: {exc}")
            return None

    def clip_captions(
        self,
        all_segs: List[Dict],
        clip_start: float,
        clip_end: float,
    ) -> List[Dict]:
        """Filter & re-time segments to clip-local timestamps."""
        caps = []
        for s in all_segs:
            if s["end"] <= clip_start or s["start"] >= clip_end:
                continue
            caps.append(
                {
                    "start": max(0.0, s["start"] - clip_start),
                    "end": min(clip_end - clip_start, s["end"] - clip_start),
                    "text": s["text"],
                }
            )
        return caps

    def write_ass(self, captions: List[Dict]) -> str | None:
        """
        Write an ASS subtitle file to a temp path and return that path.
        Returns None if captions list is empty.
        """
        if not captions:
            return None

        def _t(sec: float) -> str:
            h = int(sec // 3600)
            m = int((sec % 3600) // 60)
            s = sec % 60
            return f"{h}:{m:02d}:{s:05.2f}"

        lines = [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "",
            "[V4+ Styles]",
            (
                "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
                "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                "Alignment, MarginL, MarginR, MarginV, Encoding"
            ),
            (
                "Style: Default,Arial,56,&H00FFFFFF,&H000000FF,"
                "&H00000000,&H90000000,1,0,0,0,"
                "100,100,0,0,1,3,2,2,30,30,100,1"
            ),
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        for cap in captions:
            text = cap["text"].strip().upper().replace("\n", "\\N")
            lines.append(
                f"Dialogue: 0,{_t(cap['start'])},{_t(cap['end'])},"
                f"Default,,0,0,0,,{text}"
            )

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".ass", delete=False, encoding="utf-8"
        )
        tmp.write("\n".join(lines))
        tmp.close()
        return tmp.name

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _get_model(self):
        if self._model is None:
            import whisper
            self._model = whisper.load_model(self.model_size)
        return self._model
