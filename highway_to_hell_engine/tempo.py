from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict
from .logging_setup import log

class BlastBeatDetector:
    def detect(self, lyrics_data: List[Tuple[int,str]]) -> List[Tuple[int,int]]:
        res = []
        for i in range(len(lyrics_data)-3):
            dt = lyrics_data[i+1][0] - lyrics_data[i][0]
            if dt < 800 and len(lyrics_data[i][1].split()) > 4:
                res.append((lyrics_data[i][0], lyrics_data[i+2][0]))
        return res

class TempoSynchronizer:
    def __init__(self):
        self.blast = BlastBeatDetector()
        self.metal_artists = {"slipknot", "metallica", "megadeth", "anthrax", "pantera",
                              "lamb of god", "gojira", "meshuggah", "opeth"}

    def _syllables(self, text: str) -> int:
        v = "aeiouy"
        cnt = 0
        in_v = False
        for ch in text.lower():
            if ch in v:
                if not in_v:
                    cnt += 1
                    in_v = True
            else:
                in_v = False
        return max(1, cnt)

    def synchronize(self, lines: List[str], duration_ms: int, title: str, artist: str) -> List[Tuple[int,str]]:
        if not lines:
            return []
        per = max(500, duration_ms // max(1, len(lines)))
        out = []
        t = 0
        for ln in lines:
            out.append((t, ln))
            s = self._syllables(ln)
            t += int(per * (1.0 + min(0.5, s/12.0)))

        if artist.lower() in self.metal_artists:
            out = [(max(0, t-50), l) for t, l in out]

        for s, e in self.blast.detect(out):
            out = [(t-40 if s <= t <= e else t, l) for t, l in out]

        return out

__all__ = ["TempoSynchronizer"]
