import re
from typing import List, Dict, Optional


class VideoAnalyzer:
    """Analyzes video metadata to identify the best segments for shorts."""

    SHORT_MIN = 15   # seconds
    SHORT_MAX = 30   # seconds
    MAX_SHORTS = 9   # hard cap — never return more than this many clips

    # Keywords that signal high-engagement moments
    HOOK_KEYWORDS = [
        r"\btip\b", r"\btrick\b", r"\bhack\b", r"\bsecret\b", r"\bwatch\b",
        r"\bimportant\b", r"\bbest\b", r"\btop\b", r"\bwow\b", r"\bincredible\b",
        r"\bamazing\b", r"\bsurpris\b", r"\bnever\b", r"\balways\b", r"\bhow to\b",
        r"\bwhy\b", r"\bstep\b", r"\bkey\b", r"\bfact\b", r"\bmust\b",
        r"\bnumber\b", r"\bsimple\b", r"\bquick\b", r"\bfast\b", r"\beasy\b",
        r"\bwait\b", r"\blisten\b", r"\bunderstand\b", r"\blearn\b", r"\bchange\b",
    ]

    def analyze(
        self,
        video_info: dict,
        transcription: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """
        Return a list of candidate short segments, scored by relevance.
        If `transcription` (list of {start, end, text} from Whisper) is supplied,
        each segment is also scored by keyword density in the spoken words.
        """
        duration = video_info.get("duration", 0)
        chapters = video_info.get("chapters") or []
        description = video_info.get("description", "")
        title = video_info.get("title", "")

        segments = []

        # --- Strategy 1: Use chapters if available ---
        if chapters:
            for ch in chapters:
                start = ch.get("start_time", 0)
                end = ch.get("end_time", duration)
                seg_duration = end - start
                if self.SHORT_MIN <= seg_duration <= self.SHORT_MAX:
                    score = self._score_text(ch.get("title", ""))
                    score += self._score_transcription(transcription, start, end)
                    segments.append({
                        "start": start,
                        "end": end,
                        "duration": seg_duration,
                        "label": ch.get("title", f"Segment {len(segments)+1}"),
                        "score": score,
                        "source": "chapter",
                    })
                elif seg_duration > self.SHORT_MAX:
                    sub_segments = self._slice_window(
                        start, end, ch.get("title", ""), transcription
                    )
                    segments.extend(sub_segments)

        # --- Strategy 2: Fallback – sliding window over entire video ---
        if not segments:
            segments = self._sliding_window(
                duration, title, description, transcription
            )

        # Sort by score descending
        segments.sort(key=lambda s: s["score"], reverse=True)

        # Deduplicate overlapping segments
        segments = self._deduplicate(segments)

        # Hard cap
        segments = segments[: self.MAX_SHORTS]

        # Annotate rank
        for i, seg in enumerate(segments):
            seg["rank"] = i + 1

        return segments

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _score_text(self, text: str) -> float:
        text_lower = text.lower()
        score = 0.0
        for pattern in self.HOOK_KEYWORDS:
            if re.search(pattern, text_lower):
                score += 1.0
        return score

    def _score_transcription(
        self,
        transcription: Optional[List[Dict]],
        start: float,
        end: float,
    ) -> float:
        """Score a time window using keyword density in the Whisper transcript."""
        if not transcription:
            return 0.0
        text = " ".join(
            s["text"]
            for s in transcription
            if s["end"] > start and s["start"] < end
        )
        return self._score_text(text) * 1.5  # boost transcription-based scores

    def _slice_window(
        self,
        start: float,
        end: float,
        label: str,
        transcription: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        segs = []
        cursor = start
        idx = 1
        while cursor + self.SHORT_MAX <= end:
            seg_end = cursor + self.SHORT_MAX
            score = self._score_text(label)
            score += self._score_transcription(transcription, cursor, seg_end)
            segs.append({
                "start": cursor,
                "end": seg_end,
                "duration": self.SHORT_MAX,
                "label": f"{label} – part {idx}",
                "score": score,
                "source": "chapter_slice",
            })
            cursor = seg_end
            idx += 1
        return segs

    def _sliding_window(
        self,
        duration: float,
        title: str,
        description: str,
        transcription: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        segs = []
        step = 30  # seconds
        window = self.SHORT_MAX
        paragraphs = description.split("\n\n") or [description]

        cursor = 0.0
        idx = 1
        while cursor + window <= duration:
            para_idx = int((cursor / duration) * len(paragraphs))
            para_text = paragraphs[min(para_idx, len(paragraphs) - 1)]
            score = self._score_text(para_text) + self._score_text(title)
            score += self._score_transcription(transcription, cursor, cursor + window)

            segs.append({
                "start": cursor,
                "end": cursor + window,
                "duration": window,
                "label": f"Short {idx}",
                "score": score,
                "source": "sliding_window",
            })
            cursor += step
            idx += 1

        # Always include opening hook and closing CTA
        if duration >= window:
            hook_score = 5.0 + self._score_transcription(transcription, 0, window)
            cta_score = 4.0 + self._score_transcription(
                transcription, duration - window, duration
            )
            segs = [
                {
                    "start": 0, "end": window, "duration": window,
                    "label": "Opening Hook", "score": hook_score, "source": "fixed",
                },
                {
                    "start": duration - window, "end": duration, "duration": window,
                    "label": "Closing CTA", "score": cta_score, "source": "fixed",
                },
            ] + segs

        return segs

    def _deduplicate(
        self, segments: List[Dict], overlap_threshold: float = 0.5
    ) -> List[Dict]:
        kept = []
        for seg in segments:
            overlapping = False
            for k in kept:
                overlap = min(seg["end"], k["end"]) - max(seg["start"], k["start"])
                min_dur = min(seg["duration"], k["duration"])
                if min_dur > 0 and overlap / min_dur > overlap_threshold:
                    overlapping = True
                    break
            if not overlapping:
                kept.append(seg)
        return kept
