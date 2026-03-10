import time
import textwrap
from typing import List, Tuple

from .logging_setup import log


class SmartLyricsDisplay:
    """
    Renders 2-3 lyric lines with smoother switching.
    Third line is shown as a short preview ("2.5 lines" feeling).
    """

    def __init__(
        self,
        max_lines: int = 3,
        max_line_length: int = 26,
        min_interval_s: float = 0.2,
        page_flip_interval_s: float = 0.9,
        next_preview_ratio: float = 0.5,
    ):
        self.max_lines = max(2, int(max_lines))
        self.max_line_length = max(12, int(max_line_length))
        self.min_interval_s = max(0.05, float(min_interval_s))
        self.page_flip_interval_s = max(0.25, float(page_flip_interval_s))
        self.next_preview_ratio = max(0.25, min(1.0, float(next_preview_ratio)))

        self._page_index = 0
        self._last_line_idx = -1
        self._last_render_t = 0.0
        self._last_page_flip_t = 0.0

        self._cached = ""
        self.stats = {"page_flips": 0, "line_changes": 0}

    def _wrap(self, s: str) -> List[str]:
        if not s:
            return [""]
        chunks = textwrap.wrap(s, self.max_line_length, break_long_words=False, break_on_hyphens=False)
        return chunks or [""]

    def _next_preview(self, line: str) -> str:
        line = (line or "").strip()
        if not line:
            return ""

        preview_len = max(6, int(self.max_line_length * self.next_preview_ratio))
        if len(line) <= preview_len:
            return line
        return line[: max(1, preview_len - 1)].rstrip() + "…"

    def _format_window(self, prev_line: str, curr_line: str, next_line: str) -> str:
        lines = [prev_line, curr_line, next_line][: self.max_lines]
        while len(lines) < self.max_lines:
            lines.append("")
        return "\n".join(lines)

    def render(self, lyrics_data: List[Tuple[int, str]], progress_ms: int) -> str:
        now = time.time()

        if now - self._last_render_t < self.min_interval_s:
            return self._cached

        if not lyrics_data:
            self._cached = "Lyrics not found\n\nWaiting for data..."
            self._last_render_t = now
            return self._cached

        idx = -1
        for i in range(len(lyrics_data) - 1):
            if lyrics_data[i][0] <= progress_ms < lyrics_data[i + 1][0]:
                idx = i
                break
        else:
            if lyrics_data and progress_ms >= lyrics_data[-1][0]:
                idx = len(lyrics_data) - 1

        if idx != self._last_line_idx:
            self._last_line_idx = idx
            self._page_index = 0
            self._last_page_flip_t = now
            self.stats["line_changes"] += 1
            if self.stats["line_changes"] % 10 == 0:
                log(f"Line switches: {self.stats['line_changes']} total", "DEBUG", "display")

        prev_text = lyrics_data[idx - 1][1] if idx > 0 else ""
        curr_text = lyrics_data[idx][1] if idx >= 0 else ""
        next_text = lyrics_data[idx + 1][1] if 0 <= idx + 1 < len(lyrics_data) else ""

        prev_chunks = self._wrap(prev_text)
        curr_chunks = self._wrap(curr_text)
        next_chunks = self._wrap(next_text)

        if len(curr_chunks) > 1 and (now - self._last_page_flip_t) >= self.page_flip_interval_s:
            self._page_index = (self._page_index + 1) % len(curr_chunks)
            self._last_page_flip_t = now
            self.stats["page_flips"] += 1
        elif len(curr_chunks) <= 1:
            self._page_index = 0

        prev_show = prev_chunks[-1] if prev_chunks else ""
        curr_show = curr_chunks[self._page_index] if curr_chunks else ""
        next_raw = next_chunks[0] if next_chunks else ""
        next_show = self._next_preview(next_raw)

        self._cached = self._format_window(prev_show, curr_show, next_show)
        self._last_render_t = now
        return self._cached


__all__ = ["SmartLyricsDisplay"]
