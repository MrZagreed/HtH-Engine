import json
import re
import sqlite3
import time
import hashlib
from typing import List, Tuple, Dict, Any, Optional, Callable
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

try:
    from .tempo import TempoSynchronizer
    from .logging_setup import log
    from .app_paths import LYRICS_DB_FILE, ensure_app_dirs
except ImportError:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from duality.tempo import TempoSynchronizer
    from duality.logging_setup import log
    from duality.app_paths import LYRICS_DB_FILE, ensure_app_dirs

CACHE_TTL_SEC = 7 * 24 * 3600  # 7 дней
REQUEST_TIMEOUT = 10
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_TS = re.compile(r"\[(?:(?P<h>\d{1,2}):)?(?P<m>\d{1,2}):(?P<s>\d{1,2})(?:\.(?P<ms>\d{1,3}))?\]")


def _cut(s: str, n: int) -> str:
    return s if len(s) <= n else s[: max(0, n - 1)] + "…"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _key(song: str, artist: str) -> str:
    base = f"{_norm(artist)}\u241f{_norm(song)}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def _now() -> int:
    return int(time.time())


def _request_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    hdrs = {"User-Agent": UA, **(headers or {})}
    r = requests.get(url, params=params, headers=hdrs, timeout=REQUEST_TIMEOUT)
    if not r.ok:
        return None
    try:
        return r.json()
    except Exception:
        return None


def _request_html(url: str, headers: Optional[Dict[str, str]] = None) -> Optional[str]:
    hdrs = {"User-Agent": UA, **(headers or {})}
    r = requests.get(url, headers=hdrs, timeout=REQUEST_TIMEOUT)
    if not r.ok:
        return None
    return r.text


def _dedup_sorted(lines: List[Tuple[int, str]]) -> List[Tuple[int, str]]:
    lines.sort(key=lambda x: x[0])
    out: List[Tuple[int, str]] = []
    seen = set()
    for t, l in lines:
        l2 = l.strip()
        if not l2:
            continue
        key = (int(t), l2.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append((max(0, int(t)), l2))
    return out


def _as_plain_lines(text: str) -> List[str]:
    raw = re.sub(r"\[.*?\]", "", text or "")
    lines = [ln.strip() for ln in raw.splitlines()]
    return [ln for ln in lines if ln]


def parse_lrclib_synced(text: str) -> List[Tuple[int, str]]:
    if not text:
        return []
    out: List[Tuple[int, str]] = []
    for raw in text.splitlines():
        raw = raw.strip("\ufeff ").rstrip()
        if not raw:
            continue
        stamps = list(_TS.finditer(raw))
        if not stamps:
            continue
        lyric = _TS.sub("", raw).strip()
        for st in stamps:
            h = int(st.group("h") or 0)
            m = int(st.group("m") or 0)
            s = int(st.group("s") or 0)
            ms = int((st.group("ms") or "0").ljust(3, "0")[:3])
            total = ((h * 3600 + m * 60 + s) * 1000) + ms
            out.append((total, lyric))
    return _dedup_sorted(out)


# ---------------------------
# SQLite cache
# ---------------------------

def _db_connect() -> sqlite3.Connection:
    ensure_app_dirs()
    conn = sqlite3.connect(LYRICS_DB_FILE)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lyrics_cache (
            cache_key TEXT PRIMARY KEY,
            artist TEXT NOT NULL,
            song TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            source TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lyrics_created_at ON lyrics_cache(created_at)")
    return conn


def _load_cache_entry(cache_key: str) -> Optional[List[Tuple[int, str]]]:
    cutoff = _now() - CACHE_TTL_SEC
    try:
        with _db_connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM lyrics_cache WHERE cache_key = ? AND created_at >= ?",
                (cache_key, cutoff),
            ).fetchone()
            if not row:
                return None
            payload = json.loads(row[0])
            return [(int(t), str(l)) for t, l in payload]
    except Exception as e:
        log(f"Ошибка чтения SQLite кеша: {e}", "WARNING", "lyrics")
        return None


def _save_cache_entry(cache_key: str, artist: str, song: str, lines: List[Tuple[int, str]], source: str) -> None:
    try:
        payload_json = json.dumps(lines, ensure_ascii=False)
        now = _now()
        cutoff = now - CACHE_TTL_SEC
        with _db_connect() as conn:
            conn.execute(
                """
                INSERT INTO lyrics_cache(cache_key, artist, song, created_at, source, payload_json)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    artist=excluded.artist,
                    song=excluded.song,
                    created_at=excluded.created_at,
                    source=excluded.source,
                    payload_json=excluded.payload_json
                """,
                (cache_key, artist, song, now, source, payload_json),
            )
            conn.execute("DELETE FROM lyrics_cache WHERE created_at < ?", (cutoff,))
    except Exception as e:
        log(f"Не удалось сохранить SQLite кеш: {e}", "WARNING", "lyrics")


# ---------------------------
# Sources
# ---------------------------

def _lrclib(song: str, artist: str) -> Optional[List[Tuple[int, str]] | List[str]]:
    try:
        data = _request_json("https://lrclib.net/api/get", {"track_name": song, "artist_name": artist})
        if data and data.get("syncedLyrics"):
            return parse_lrclib_synced(data["syncedLyrics"])
        if data and data.get("plainLyrics"):
            return _as_plain_lines(data["plainLyrics"])
    except Exception as e:
        log(f"LRCLIB get ошибка: {e}", "WARNING", "lyrics")

    try:
        q = _request_json(
            "https://lrclib.net/api/search",
            {"track_name": song, "artist_name": artist, "limit": 5},
        )
        if not q:
            return None

        best = None
        score_best = -1
        nsong = _norm(song)
        nartist = _norm(artist)
        for item in q:
            s = _norm(item.get("trackName", ""))
            a = _norm(item.get("artistName", ""))
            score = (2 if (nsong in s or s in nsong) else 0) + (2 if (nartist in a or a in nartist) else 0)
            if score > score_best:
                score_best = score
                best = item
        if best:
            if best.get("syncedLyrics"):
                return parse_lrclib_synced(best["syncedLyrics"])
            if best.get("plainLyrics"):
                return _as_plain_lines(best["plainLyrics"])
    except Exception as e:
        log(f"LRCLIB search ошибка: {e}", "WARNING", "lyrics")

    return None


def _lyrics_ovh(song: str, artist: str) -> Optional[List[str]]:
    try:
        j = _request_json(f"https://api.lyrics.ovh/v1/{artist}/{song}")
        if j and "lyrics" in j:
            return _as_plain_lines(j["lyrics"])
    except Exception as e:
        log(f"lyrics.ovh ошибка: {e}", "WARNING", "lyrics")
    return None


def _genius_plain(song: str, artist: str) -> Optional[List[str]]:
    try:
        s = _request_json("https://genius.com/api/search/multi", {"q": f"{artist} {song}", "per_page": 5})
        path = None
        if s and "response" in s:
            for section in s["response"].get("sections", []):
                if section.get("type") == "song":
                    hits = section.get("hits", [])
                    if hits:
                        path = hits[0]["result"].get("path")
                        break
        if not path:
            return None

        html = _request_html(f"https://genius.com{path}")
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        blocks = soup.select('div[data-lyrics-container="true"]')
        if not blocks:
            return None

        txt = "\n".join(b.get_text("\n", strip=True) for b in blocks)
        txt = re.sub(r"^\s*\[[^\]]+\]\s*$", "", txt, flags=re.MULTILINE)
        lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
        return lines or None
    except Exception as e:
        log(f"Genius парсинг ошибка: {e}", "WARNING", "lyrics")
        return None


def _musixmatch_plain(song: str, artist: str) -> Optional[List[str]]:
    try:
        q = f"{_norm(artist)}-{_norm(song)}".replace(" ", "-")
        html = _request_html(f"https://www.musixmatch.com/lyrics/{q}")
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        node = soup.find(class_=re.compile(r"mxm-lyrics__content"))
        if not node:
            return None
        txt = node.get_text("\n", strip=True)
        lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
        return lines or None
    except Exception as e:
        log(f"Musixmatch парсинг ошибка: {e}", "WARNING", "lyrics")
        return None


def _azlyrics_plain(song: str, artist: str) -> Optional[List[str]]:
    """Дополнительный источник plain-lyrics через страницу поиска AZLyrics."""
    try:
        search_url = f"https://search.azlyrics.com/search.php?q={quote_plus(f'{artist} {song}')}"
        html = _request_html(search_url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")
        link = None
        for a in soup.select("td.text-left.visitedlyr a"):
            href = (a.get("href") or "").strip()
            if "azlyrics.com/lyrics/" in href:
                link = href
                break
        if not link:
            return None

        track_html = _request_html(link)
        if not track_html:
            return None

        soup = BeautifulSoup(track_html, "html.parser")
        # Текст лежит в div без класса внутри основного контейнера.
        blocks = soup.select("div.col-xs-12.col-lg-8.text-center > div")
        target = None
        for b in blocks:
            if b.get("class"):
                continue
            txt = b.get_text("\n", strip=True)
            if len(txt) > 40:
                target = txt
                break
        if not target:
            return None
        lines = [ln.strip() for ln in target.splitlines() if ln.strip()]
        return lines or None
    except Exception as e:
        log(f"AZLyrics парсинг ошибка: {e}", "WARNING", "lyrics")
        return None


# ---------------------------
# Main
# ---------------------------

def fetch_lyrics(song: str, artist: str, duration_ms: Optional[int] = None) -> List[Tuple[int, str]]:
    song = song or ""
    artist = artist or ""
    dur = int(duration_ms) if duration_ms else 180_000

    cache_key = _key(song, artist)
    cached = _load_cache_entry(cache_key)
    if cached is not None:
        return cached

    sync = TempoSynchronizer()

    def _save(lines: List[Tuple[int, str]], source: str) -> List[Tuple[int, str]]:
        out = _dedup_sorted(lines)
        _save_cache_entry(cache_key, artist, song, out, source)
        return out

    # 1) LRCLIB
    try:
        lrclib = _lrclib(song, artist)
        if isinstance(lrclib, list) and lrclib and isinstance(lrclib[0], tuple):
            lines = _save(lrclib, "lrclib_synced")
            log(f"LRCLIB synced: {_cut(artist, 24)} — {_cut(song, 32)} [{len(lines)}]", "INFO", "lyrics")
            return lines
        if isinstance(lrclib, list) and lrclib and isinstance(lrclib[0], str):
            lines = _save(sync.synchronize(lrclib, dur, song, artist), "lrclib_plain")
            log(f"LRCLIB plain->sync: {_cut(artist, 24)} — {_cut(song, 32)} [{len(lines)}]", "INFO", "lyrics")
            return lines
    except Exception as e:
        log(f"LRCLIB недоступен: {e}", "WARNING", "lyrics")

    sources: List[Tuple[str, Callable[[str, str], Optional[List[str]]]]] = [
        ("genius", _genius_plain),
        ("musixmatch", _musixmatch_plain),
        ("azlyrics", _azlyrics_plain),
        ("lyrics.ovh", _lyrics_ovh),
    ]

    for source_name, provider in sources:
        try:
            plain = provider(song, artist)
            if plain:
                lines = _save(sync.synchronize(plain, dur, song, artist), f"{source_name}_plain")
                log(f"{source_name} plain->sync: {_cut(artist, 24)} — {_cut(song, 32)} [{len(lines)}]", "INFO", "lyrics")
                return lines
        except Exception as e:
            log(f"{source_name} недоступен: {e}", "WARNING", "lyrics")

    log(f"Текст не найден: {song} — {artist}", "WARNING", "lyrics")
    _save_cache_entry(cache_key, artist, song, [], "not_found")
    return []


__all__ = ["fetch_lyrics", "parse_lrclib_synced"]
