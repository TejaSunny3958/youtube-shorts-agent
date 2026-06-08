import os
import platform
import subprocess
from typing import List, Dict, Optional
import imageio_ffmpeg


def _ffmpeg_bin() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _escape_subtitle_path(path: str) -> str:
    """
    Escape a file path for use inside FFmpeg's subtitles/ass filter value.
    On Windows, backslashes must become forward slashes and the drive-letter
    colon must be escaped as \\:.
    """
    p = path.replace("\\", "/")
    if platform.system() == "Windows" and len(p) > 1 and p[1] == ":":
        p = p[0] + "\\:" + p[2:]
    return p


class VideoClipper:
    """Cuts video segments using FFmpeg with optional effects, captions, and music."""

    def __init__(self, output_dir: str = "outputs/shorts"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public convenience wrapper (used by the old synchronous pipeline)
    # ------------------------------------------------------------------

    def clip_all(
        self,
        video_path: str,
        segments: List[Dict],
        video_id: str,
        effect_filters: List[tuple] = None,
    ) -> List[Dict]:
        """Clip every segment (with optional baked-in effect)."""
        for i, seg in enumerate(segments):
            effect_name, extra_vf = (
                effect_filters[i]
                if effect_filters and i < len(effect_filters)
                else ("none", None)
            )
            try:
                out_path = self.clip_single(
                    video_path, seg["start"], seg["end"],
                    video_id, seg["rank"], extra_vf=extra_vf,
                )
                seg["clip_path"] = out_path
                seg["effect"] = effect_name
                seg["effect_path"] = out_path
            except Exception as e:
                seg["clip_path"] = None
                seg["effect"] = "none"
                seg["effect_path"] = None
                seg["clip_error"] = str(e)
        return segments

    # ------------------------------------------------------------------
    # Main clip function – handles effects + captions + background music
    # ------------------------------------------------------------------

    def clip_single(
        self,
        video_path: str,
        start: float,
        end: float,
        video_id: str,
        rank: int,
        extra_vf: Optional[str] = None,
        subs_file: Optional[str] = None,
        music_file: Optional[str] = None,
        out_name: Optional[str] = None,
    ) -> str:
        """
        Clip [start, end] from video_path and write a 1080×1920 portrait mp4.

        extra_vf   – additional FFmpeg video filter string (visual effects)
        subs_file  – path to an .ass subtitle file to burn in
        music_file – path to background music to mix at low volume
        """
        duration = end - start
        has_fx = bool(extra_vf or subs_file or music_file)
        suffix = "_fx" if has_fx else ""
        if out_name:
            out_path = os.path.join(self.output_dir, out_name)
        else:
            out_path = os.path.join(
                self.output_dir, f"{video_id}_short_{rank}{suffix}.mp4"
            )

        # ── Video filter chain ──────────────────────────────────────────
        # Fit video into 1080×1920 portrait frame without cropping or
        # oversizing — letterbox/pillarbox with black bars if needed.
        base_vf = (
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black,"
            "setsar=1"
        )
        vf_parts = [base_vf]
        if extra_vf:
            vf_parts.append(extra_vf)
        if subs_file:
            escaped = _escape_subtitle_path(subs_file)
            vf_parts.append(f"subtitles='{escaped}'")
        vf = ",".join(vf_parts)

        # ── Build FFmpeg command ────────────────────────────────────────
        cmd = [
            _ffmpeg_bin(), "-y",
            "-ss", str(start),
            "-i", video_path,
            "-t", str(duration),
        ]

        if music_file:
            # Add looping music input
            cmd += ["-stream_loop", "-1", "-i", music_file, "-t", str(duration)]
            # Mix: original audio at full volume + music at 15 %
            audio_fc = (
                "[0:a]volume=1.0[va];"
                "[1:a]volume=0.15[ma];"
                "[va][ma]amix=inputs=2:duration=first[aout]"
            )
            cmd += [
                "-vf", vf,
                "-filter_complex", audio_fc,
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "libx264",
                "-c:a", "aac",
                "-preset", "ultrafast",
                "-crf", "23",
                out_path,
            ]
        else:
            cmd += [
                "-c:v", "libx264",
                "-c:a", "aac",
                "-preset", "ultrafast",
                "-crf", "23",
                "-vf", vf,
                out_path,
            ]

        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode(errors="replace")[-800:])
        return out_path

    # Keep _clip as an alias for backwards compatibility
    def _clip(self, *args, **kwargs):
        return self.clip_single(*args, **kwargs)
