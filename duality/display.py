import time
import textwrap
from typing import List, Tuple
from .logging_setup import log

class SmartLyricsDisplay:
    """
    Отрисовка 2–3 строк текста с простым пейджингом для длинных строк.
    render(lyrics_data, progress_ms) -> str (до 3 строк, разделенных \n)
    """
    def __init__(self, max_lines: int = 3, max_line_length: int = 42, min_interval_s: float = 0.2):
        self.max_lines = max_lines
        self.max_line_length = max_line_length
        self.min_interval_s = min_interval_s

        self._page_index = 0
        self._last_line_idx = -1
        self._last_render_t = 0.0

        self._cached = ""
        self.stats = {"page_flips": 0, "line_changes": 0}

    def _wrap(self, s: str) -> List[str]:
        if not s:
            return [""]
        chunks = textwrap.wrap(s, self.max_line_length, break_long_words=False, break_on_hyphens=False)
        return chunks or [""]

    def _format_window(self, prev_line: str, curr_line: str, next_line: str) -> str:
        lines = [prev_line, curr_line, next_line][:self.max_lines]
        while len(lines) < self.max_lines:
            lines.append("")
        return "\n".join(lines)

    def render(self, lyrics_data: List[Tuple[int, str]], progress_ms: int) -> str:
        now = time.time()

        # Rate-limit отрисовку
        if now - self._last_render_t < self.min_interval_s:
            return self._cached

        if not lyrics_data:
            self._cached = "Текст не найден\n\nОжидание данных…"
            self._last_render_t = now
            return self._cached

        # Текущая строка
        idx = -1
        for i in range(len(lyrics_data) - 1):
            if lyrics_data[i][0] <= progress_ms < lyrics_data[i+1][0]:
                idx = i
                break
        else:
            if lyrics_data and progress_ms >= lyrics_data[-1][0]:
                idx = len(lyrics_data) - 1

        if idx != self._last_line_idx:
            self._last_line_idx = idx
            self._page_index = 0
            self.stats["line_changes"] += 1
            if self.stats["line_changes"] % 10 == 0:
                log(f"Смена строк: {self.stats['line_changes']} всего", "DEBUG", "display")

        prev_text = lyrics_data[idx-1][1] if idx > 0 else ""
        curr_text = lyrics_data[idx][1] if idx >= 0 else ""
        next_text = lyrics_data[idx+1][1] if 0 <= idx+1 < len(lyrics_data) else ""

        prev_chunks = self._wrap(prev_text)
        curr_chunks = self._wrap(curr_text)
        next_chunks = self._wrap(next_text)

        # Пагинация текущей строки
        if len(curr_chunks) > 1:
            self._page_index = (self._page_index + 1) % len(curr_chunks)
            self.stats["page_flips"] += 1
        else:
            self._page_index = 0

        prev_show = prev_chunks[-1] if prev_chunks else ""
        curr_show = curr_chunks[self._page_index] if curr_chunks else ""
        next_show = next_chunks[0] if next_chunks else ""

        self._cached = self._format_window(prev_show, curr_show, next_show)
        self._last_render_t = now
        return self._cached

__all__ = ["SmartLyricsDisplay"]
