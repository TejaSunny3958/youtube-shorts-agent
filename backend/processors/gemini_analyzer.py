"""
GeminiAnalyzer – uses Google Gemini to intelligently pick the best 30-second
moments from a video transcript and generate viral Short titles.

Falls back silently to an empty list so the caller can use the rule-based
VideoAnalyzer instead.
"""

import json
import logging
import os
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-import Gemini so the rest of the app works even without the package
# ---------------------------------------------------------------------------
try:
    from google import genai  # type: ignore
    from google.genai import types as genai_types  # type: ignore
    _GENAI_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore
    genai_types = None  # type: ignore
    _GENAI_AVAILABLE = False
    logger.warning("google-genai not installed – GeminiAnalyzer disabled")


class GeminiAnalyzer:
    """
    Wraps Gemini 1.5 Flash to select & rank the best short-form segments.

    Usage
    -----
    analyzer = GeminiAnalyzer(api_key="...")
    segments = analyzer.analyze(video_info, transcription)
    # segments → same schema as VideoAnalyzer.analyze()
    """

    MODEL = "gemini-2.5-flash"
    MAX_SHORTS = 9

    def __init__(self, api_key: Optional[str] = None):
        self._ready = False
        if not _GENAI_AVAILABLE:
            return
        key = api_key or os.getenv("GOOGLE_API_KEY", "")
        if not key:
            logger.warning("GOOGLE_API_KEY not set – GeminiAnalyzer disabled")
            return
        try:
            self._client = genai.Client(
                api_key=key,
                http_options=genai_types.HttpOptions(api_version="v1"),
            )
            self._ready = True
            logger.info("GeminiAnalyzer ready (model=%s)", self.MODEL)
        except Exception as exc:
            logger.error("GeminiAnalyzer init failed: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def available(self) -> bool:
        return self._ready

    def analyze(
        self,
        video_info: dict,
        transcription: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """
        Ask Gemini to pick the best short segments.

        Returns a list (possibly empty on failure) in the same schema as
        VideoAnalyzer:
          { start, end, duration, label, score, source, rank }
        """
        if not self._ready:
            return []

        transcript_text = self._build_transcript_text(transcription)
        if not transcript_text:
            logger.info("GeminiAnalyzer: empty transcript, skipping")
            return []

        duration = video_info.get("duration", 0)
        title = video_info.get("title", "")
        description = (video_info.get("description") or "")[:800]

        prompt = self._build_prompt(title, description, duration, transcript_text)

        try:
            response = self._client.models.generate_content(
                model=self.MODEL,
                contents=prompt,
            )
            raw = response.text
            logger.debug("Gemini raw response (first 500): %s", raw[:500])
            segments = self._parse_response(raw, duration)
            logger.info("GeminiAnalyzer returned %d segments", len(segments))
            if not segments:
                logger.warning("Gemini returned 0 valid segments. Raw: %s", raw[:300])
            return segments
        except Exception as exc:
            logger.error("GeminiAnalyzer.analyze failed: %s", exc)
            return []

    def generate_titles(
        self,
        video_title: str,
        segments: List[Dict],
        transcription: Optional[List[Dict]] = None,
    ) -> Dict[int, str]:
        """
        Generate a viral YouTube Shorts title for each segment (keyed by rank).
        Returns {} on failure.
        """
        if not self._ready or not segments:
            return {}

        snippets = []
        for seg in segments[:self.MAX_SHORTS]:
            spoken = ""
            if transcription:
                spoken = " ".join(
                    s["text"]
                    for s in transcription
                    if s["end"] > seg["start"] and s["start"] < seg["end"]
                )[:200]
            snippets.append(
                f'Rank {seg["rank"]} ({seg["start"]:.0f}s–{seg["end"]:.0f}s): '
                f'label="{seg.get("label","")}" | spoken="{spoken}"'
            )

        prompt = (
            f'Video: "{video_title}"\n\n'
            "For each clip below, write ONE punchy viral YouTube Shorts title "
            "(max 60 chars, no hashtags, use curiosity/emotion hooks).\n"
            "Return ONLY a JSON object mapping rank (integer) to title (string).\n\n"
            + "\n".join(snippets)
        )

        try:
            response = self._client.models.generate_content(
                model=self.MODEL,
                contents=prompt,
            )
            raw = response.text
            # strip markdown fences if present
            raw = re.sub(r"```[a-z]*\n?", "", raw).strip().rstrip("`").strip()
            data = json.loads(raw)
            # normalise keys to int
            return {int(k): str(v) for k, v in data.items()}
        except Exception as exc:
            logger.error("GeminiAnalyzer.generate_titles failed: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_transcript_text(self, transcription: Optional[List[Dict]]) -> str:
        if not transcription:
            return ""
        lines = []
        for seg in transcription:
            start = seg.get("start", 0)
            text = seg.get("text", "").strip()
            if text:
                lines.append(f"[{start:.1f}s] {text}")
        return "\n".join(lines)

    def _build_prompt(
        self,
        title: str,
        description: str,
        duration: float,
        transcript: str,
    ) -> str:
        # Keep transcript under ~12 000 chars to stay well within token limits
        if len(transcript) > 12000:
            transcript = transcript[:12000] + "\n[transcript truncated]"

        return f"""You are an expert YouTube Shorts editor.

Video title: {title}
Duration: {duration:.0f} seconds
Description: {description}

TRANSCRIPT (format: [timestamp_seconds] text):
{transcript}

Task: Identify the {self.MAX_SHORTS} most engaging, self-contained 30-second windows
for YouTube Shorts. Prefer moments with:
- Surprising facts, emotional peaks, strong hooks
- Clear standalone value (viewer doesn't need context)
- High energy or curiosity-triggering language

Rules:
- Each window MUST be exactly 30 seconds (end = start + 30)
- Windows must NOT overlap
- start >= 0 and end <= {duration:.0f}
- Return ONLY valid JSON — an array of objects, no markdown fences

JSON schema (array of objects):
[
  {{
    "start": <float seconds>,
    "end": <float seconds>,
    "label": "<short catchy title for this clip, max 60 chars>",
    "score": <float 0-10, how engaging>
  }},
  ...
]"""

    def _parse_response(self, raw: str, duration: float) -> List[Dict]:
        # Strip markdown fences
        raw = re.sub(r"```[a-z]*\n?", "", raw).strip().rstrip("`").strip()

        # Try to extract a JSON array even if there's surrounding text
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            logger.error("GeminiAnalyzer: no JSON array in response:\n%s", raw[:400])
            return []

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as exc:
            logger.error("GeminiAnalyzer JSON parse error: %s\n%s", exc, raw[:400])
            return []

        segments = []
        seen_starts: set = set()

        for item in data:
            try:
                start = float(item["start"])
                end = float(item.get("end", start + 30))
                label = str(item.get("label", f"Moment {len(segments)+1}"))
                score = float(item.get("score", 5.0))
            except (KeyError, ValueError, TypeError):
                continue

            # Sanity-check — be lenient: allow up to duration + 30s overrun
            if start < 0 or end > duration + 30 or end <= start:
                continue
            if round(start) in {round(s) for s in seen_starts}:
                continue

            # Clamp end to video length
            end = min(end, duration)
            # Enforce 30s window
            if end - start > 32:
                end = start + 30
            actual_dur = end - start
            if actual_dur < 5:
                continue

            seen_starts.add(start)
            segments.append({
                "start": start,
                "end": end,
                "duration": actual_dur,
                "label": label,
                "score": score,
                "source": "gemini",
            })

        # Sort by score descending, cap, annotate rank
        segments.sort(key=lambda s: s["score"], reverse=True)
        segments = segments[: self.MAX_SHORTS]
        for i, seg in enumerate(segments):
            seg["rank"] = i + 1

        return segments
