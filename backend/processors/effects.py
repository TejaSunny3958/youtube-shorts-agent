import os
import subprocess
from typing import List, Dict, Tuple
import imageio_ffmpeg


def _ffmpeg_bin() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


class VideoEffects:
    """Applies rich visual effects to short clips using FFmpeg filters."""

    # 7 distinct cinematic effects — each clip in a batch gets its own style
    EFFECTS = [
        "cinematic_cold",   # blue tones + vignette + fade
        "warm_glow",        # warm orange grade + soft glow
        "color_pop",        # vivid saturated + contrast punch
        "neon_dark",        # deep shadows + cyan/magenta push
        "film_grain",       # cinematic bars + grain + fade
        "golden_hour",      # warm lift + brightness + vignette
        "moody_blue",       # desaturate + cyan push + letterbox
    ]

    def __init__(self, output_dir: str = "outputs/shorts"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def apply_all(self, segments: List[Dict]) -> List[Dict]:
        for i, seg in enumerate(segments):
            clip_path = seg.get("clip_path")
            if not clip_path or not os.path.exists(clip_path) or os.path.getsize(clip_path) == 0:
                seg["effect"] = "none"
                seg["effect_path"] = clip_path
                continue
            effect = self.EFFECTS[i % len(self.EFFECTS)]
            try:
                out_path = self._apply_effect(clip_path, effect, seg.get("duration", 30))
                seg["effect"] = effect
                seg["effect_path"] = out_path
            except Exception:
                seg["effect"] = "none"
                seg["effect_path"] = clip_path
        return segments

    # ------------------------------------------------------------------
    # Used by the single-pass pipeline in clipper.py
    # ------------------------------------------------------------------

    def get_effect_filter(self, index: int, duration: float = 30) -> Tuple[str, str]:
        """Return (effect_name, ffmpeg_vf_string) for the clip at `index`."""
        effect = self.EFFECTS[index % len(self.EFFECTS)]
        return effect, self._get_filter(effect, duration)

    # ------------------------------------------------------------------
    # Effect filter definitions
    # ------------------------------------------------------------------

    def _get_filter(self, effect: str, duration: float = 30) -> str:
        fade_in  = "fade=t=in:st=0:d=0.4"
        fade_out = f"fade=t=out:st={max(0, duration - 0.5):.2f}:d=0.5"

        filters = {
            # ── Cool cinematic: blue tint + deep vignette + fades ─────────
            "cinematic_cold": (
                f"eq=saturation=0.85:contrast=1.1:brightness=-0.02,"
                f"colorchannelmixer=rr=0.85:gg=0.95:bb=1.18,"
                f"vignette=PI/3.5,"
                f"{fade_in},{fade_out}"
            ),

            # ── Warm glow: orange/amber grade + lifted shadows ─────────────
            "warm_glow": (
                f"eq=saturation=1.25:contrast=1.05:brightness=0.04,"
                f"colorchannelmixer=rr=1.15:gg=1.02:bb=0.82,"
                f"vignette=PI/5,"
                f"{fade_in},{fade_out}"
            ),

            # ── Vivid colour pop: max saturation + punch ───────────────────
            "color_pop": (
                f"eq=saturation=1.7:contrast=1.15:brightness=0.03,"
                f"unsharp=5:5:0.8:3:3:0,"
                f"{fade_in},{fade_out}"
            ),

            # ── Neon dark: crushed blacks + cyan/magenta grade ─────────────
            "neon_dark": (
                f"eq=saturation=1.4:contrast=1.3:brightness=-0.06,"
                f"colorchannelmixer=rr=0.9:gg=1.05:bb=1.2,"
                f"vignette=PI/2.8,"
                f"{fade_in},{fade_out}"
            ),

            # ── Film grain: cinematic bars + grain texture + fades ─────────
            "film_grain": (
                f"pad=iw:ih+ih*0.12:0:(oh-ih)/2:black,"
                f"noise=alls=8:allf=t+u,"
                f"eq=contrast=1.1:saturation=0.9,"
                f"{fade_in},{fade_out}"
            ),

            # ── Golden hour: warm bright lift + soft vignette ──────────────
            "golden_hour": (
                f"eq=saturation=1.35:contrast=1.08:brightness=0.06,"
                f"colorchannelmixer=rr=1.2:gg=1.08:bb=0.75,"
                f"vignette=PI/4.5,"
                f"{fade_in},{fade_out}"
            ),

            # ── Moody blue: partial desaturate + blue shadow + letterbox ───
            "moody_blue": (
                f"eq=saturation=0.7:contrast=1.2:brightness=-0.04,"
                f"colorchannelmixer=rr=0.8:gg=0.9:bb=1.25,"
                f"pad=iw:ih+ih*0.10:0:(oh-ih)/2:black,"
                f"{fade_in},{fade_out}"
            ),
        }
        return filters.get(effect, f"{fade_in},{fade_out}")

    # ------------------------------------------------------------------
    # Standalone apply (used when effect is a separate pass)
    # ------------------------------------------------------------------

    def _apply_effect(self, clip_path: str, effect: str, duration: float = 30) -> str:
        base = os.path.splitext(clip_path)[0]
        out_path = f"{base}_fx.mp4"
        vf = self._get_filter(effect, duration)
        cmd = [
            _ffmpeg_bin(), "-y",
            "-i", clip_path,
            "-vf", vf,
            "-c:v", "libx264", "-c:a", "copy",
            "-preset", "fast", "-crf", "22",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode(errors="replace")[-500:])
        return out_path

    def __init__(self, output_dir: str = "outputs/shorts"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def apply_all(self, segments: List[Dict]) -> List[Dict]:
        """Apply a rotating set of effects to each clip."""
        for i, seg in enumerate(segments):
            clip_path = seg.get("clip_path")
            if not clip_path or not os.path.exists(clip_path) or os.path.getsize(clip_path) == 0:
                seg["effect"] = "none"
                seg["effect_path"] = clip_path
                continue
            effect = self.EFFECTS[i % len(self.EFFECTS)]
            try:
                out_path = self._apply_effect(clip_path, effect, seg.get("duration", 60))
                seg["effect"] = effect
                seg["effect_path"] = out_path
            except Exception:
                # Fall back to uneffected clip on any error
                seg["effect"] = "none"
                seg["effect_path"] = clip_path
        return segments

    # ------------------------------------------------------------------
    # Individual effect builders
    # ------------------------------------------------------------------

    def _apply_effect(self, clip_path: str, effect: str, duration: float = 60) -> str:
        base = os.path.splitext(clip_path)[0]
        out_path = f"{base}_fx.mp4"

        vf = self._get_filter(effect, duration)

        cmd = [
            _ffmpeg_bin(), "-y",
            "-i", clip_path,
            "-vf", vf,
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-crf", "22",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode(errors="replace")[-500:])
        return out_path

    def _get_filter(self, effect: str, duration: float = 60) -> str:
        fade_out_start = max(0, duration - 0.6)
        filters = {
            # Subtle brightness/contrast punch
            "zoom_pulse": (
                "eq=contrast=1.15:brightness=0.03:saturation=1.2"
            ),
            # Dark circular vignette around edges
            "vignette": (
                "vignette=PI/4"
            ),
            # Boost saturation for vivid colours
            "color_pop": (
                "eq=saturation=1.6:brightness=0.05:contrast=1.1"
            ),
            # Black letterbox bars for cinematic look
            "cinematic_bars": (
                "pad=iw:ih+ih*0.15:0:(oh-ih)/2:black"
            ),
            # Smooth fade-in for first 0.5 s and fade-out for last 0.5 s
            "smooth_fade": (
                f"fade=t=in:st=0:d=0.5,fade=t=out:st={fade_out_start:.2f}:d=0.5"
            ),
        }
        return filters.get(effect, "null")

    def get_effect_filter(self, index: int, duration: float = 60) -> str:
        """Return just the FFmpeg filter string for a given segment index."""
        effect = self.EFFECTS[index % len(self.EFFECTS)]
        return effect, self._get_filter(effect, duration)
