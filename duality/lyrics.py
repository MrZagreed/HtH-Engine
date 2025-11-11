import re
import os
import json
import time
import hashlib
import requests
from typing import List, Tuple, Dict, Any, Optional
from bs4 import BeautifulSoup

# ---- универсальный импорт для запуска и как модуля, и как скрипта ----
try:
    # когда запускаем через "python -m duality.lyrics"
    from .tempo import TempoSynchronizer
    from .logging_setup import log
except ImportError:
    # когда запускаем напрямую "python duality/lyrics.py"
    import sys
    from pathlib import Path
    # добавим родительскую папку проекта в sys.path
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from duality.tempo import TempoSynchronizer
    from duality.logging_setup import log
# ----------------------------------------------------------------------

# ---------------------------
# Константы и утилиты
# ---------------------------

CACHE_FILE = ".lyrics_cache.json"
CACHE_TTL_SEC = 7 * 24 * 3600  # 7 дней
REQUEST_TIMEOUT = 10
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

def _cut(s: str, n: int) -> str:
    return s if len(s) <= n else s[:max(0, n - 1)] + "…"

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()

def _key(song: str, artist: str) -> str:
    base = f"{_norm(artist)}\u241f{_norm(song)}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()

def _load_cache() -> Dict[str, Any]:
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_cache(data: Dict[str, Any]) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        log(f"Не удалось сохранить кэш: {e}", "WARNING", "lyrics")

def _now() -> int:
    return int(time.time())

def _request_json(url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
    headers = {**({"User-Agent": UA}), **(headers or {})}
    r = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
    if not r.ok:
        return None
    try:
        return r.json()
    except Exception:
        return None

def _request_html(url: str, headers: Optional[Dict[str, str]] = None) -> Optional[str]:
    headers = {**({"User-Agent": UA}), **(headers or {})}
    r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
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
        key = (t, l2.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append((max(0, int(t)), l2))
    return out

def _as_plain_lines(text: str) -> List[str]:
    raw = re.sub(r"\[.*?\]", "", text or "")
    lines = [ln.strip() for ln in raw.splitlines()]
    return [ln for ln in lines if ln]

# ---------------------------
# Парсеры LRC
# ---------------------------

_TS = re.compile(r"\[(?:(?P<h>\d{1,2}):)?(?P<m>\d{1,2}):(?P<s>\d{1,2})(?:\.(?P<ms>\d{1,3}))?\]")

def parse_lrclib_synced(text: str) -> List[Tuple[int, str]]:
    """
    Совместимый с твоей сигнатурой парсер LRC.
    Поддерживает часы и миллисекунды, убирает метаданные и дубликаты.
    """
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
# Источники
# ---------------------------

def _lrclib(song: str, artist: str) -> Optional[List[Tuple[int, str]]]:
    # 1) точный get
    try:
        data = _request_json("https://lrclib.net/api/get", {
            "track_name": song, "artist_name": artist
        })
        if data and data.get("syncedLyrics"):
            return parse_lrclib_synced(data["syncedLyrics"])
        if data and data.get("plainLyrics"):
            return _as_plain_lines(data["plainLyrics"])
    except Exception as e:
        log(f"LRCLIB get ошибка: {e}", "WARNING", "lyrics")

    # 2) поиск (иногда get не находит)
    try:
        q = _request_json("https://lrclib.net/api/search", {
            "track_name": song, "artist_name": artist, "limit": 3
        })
        if not q:
            return None
        # выбираем лучший матч по вхождению имени артиста и трека
        best = None
        score_best = -1
        nsong = _norm(song)
        nartist = _norm(artist)
        for item in q:
            s = _norm(item.get("trackName", ""))
            a = _norm(item.get("artistName", ""))
            score = (2 if nsong in s or s in nsong else 0) + (2 if nartist in a or a in nartist else 0)
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
    """
    Пытаемся через публичный поиск и парс HTML страницы трека.
    """
    try:
        # Быстрый поиск через их API
        s = _request_json(
            "https://genius.com/api/search/multi",
            {"q": f"{artist} {song}", "per_page": 5}
        )
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
        # Тексты Genius сейчас хранятся в <div data-lyrics-container="true">
        blocks = soup.select('div[data-lyrics-container="true"]')
        if not blocks:
            return None
        txt = "\n".join(b.get_text("\n", strip=True) for b in blocks)
        # чистим мусорные теги и подсказки внутри скобок иногда оставляем
        txt = re.sub(r"^\s*\[[^\]]+\]\s*$", "", txt, flags=re.MULTILINE)
        lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
        return lines or None
    except Exception as e:
        log(f"Genius парсинг ошибка: {e}", "WARNING", "lyrics")
        return None

def _musixmatch_plain(song: str, artist: str) -> Optional[List[str]]:
    """
    Лёгкий HTML-скрейп страницы трека. Musixmatch любит обфускацию,
    но для базовой версии текст лежит в теге с классом 'mxm-lyrics__content'.
    Может не работать в редких странах/аккаунтах.
    """
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

# ---------------------------
# Главная функция
# ---------------------------

def fetch_lyrics(song: str, artist: str, duration_ms: Optional[int] = None) -> List[Tuple[int, str]]:
    """
    Возвращает синхронизированные строки [(ms, text)].
    Алгоритм:
      1) Проверяем кэш.
      2) LRCLIB (synced -> LRC; plain -> авто-синхронизация).
      3) Genius (plain -> авто-синхронизация).
      4) Musixmatch (plain -> авто-синхронизация).
      5) lyrics.ovh (plain -> авто-синхронизация).
    """
    song = song or ""
    artist = artist or ""
    dur = int(duration_ms) if duration_ms else None

    cache = _load_cache()
    k = _key(song, artist)
    entry = cache.get(k)
    if entry and (entry.get("ts", 0) + CACHE_TTL_SEC) > _now():
        cached = entry.get("data") or []
        if cached:
            return [(int(t), str(l)) for t, l in cached]

    sync = TempoSynchronizer()

    # 1) LRCLIB
    try:
        lrclib = _lrclib(song, artist)
        if isinstance(lrclib, list) and lrclib and isinstance(lrclib[0], tuple):
            lines = _dedup_sorted(lrclib)
            cache[k] = {"ts": _now(), "data": lines}
            _save_cache(cache)
            log(f"LRCLIB synced: {_cut(artist, 24)} — {_cut(song, 32)} [{len(lines)}]", "INFO", "lyrics")
            return lines
        if isinstance(lrclib, list) and lrclib and isinstance(lrclib[0], str):
            # plain lyrics → авто-синхронизация
            lines = sync.synchronize(lrclib, dur or 180_000, song, artist)
            lines = _dedup_sorted(lines)
            cache[k] = {"ts": _now(), "data": lines}
            _save_cache(cache)
            log(f"LRCLIB plain→sync: {_cut(artist, 24)} — {_cut(song, 32)} [{len(lines)}]", "INFO", "lyrics")
            return lines
    except Exception as e:
        log(f"LRCLIB недоступен: {e}", "WARNING", "lyrics")

    # 2) GENIUS
    try:
        g = _genius_plain(song, artist)
        if g:
            lines = sync.synchronize(g, dur or 180_000, song, artist)
            lines = _dedup_sorted(lines)
            cache[k] = {"ts": _now(), "data": lines}
            _save_cache(cache)
            log(f"Genius plain→sync: {_cut(artist, 24)} — {_cut(song, 32)} [{len(lines)}]", "INFO", "lyrics")
            return lines
    except Exception as e:
        log(f"Genius недоступен: {e}", "WARNING", "lyrics")

    # 3) MUSIXMATCH
    try:
        m = _musixmatch_plain(song, artist)
        if m:
            lines = sync.synchronize(m, dur or 180_000, song, artist)
            lines = _dedup_sorted(lines)
            cache[k] = {"ts": _now(), "data": lines}
            _save_cache(cache)
            log(f"Musixmatch plain→sync: {_cut(artist, 24)} — {_cut(song, 32)} [{len(lines)}]", "INFO", "lyrics")
            return lines
    except Exception as e:
        log(f"Musixmatch недоступен: {e}", "WARNING", "lyrics")

    # 4) LYRICS.OVH
    try:
        ovh = _lyrics_ovh(song, artist)
        if ovh:
            lines = sync.synchronize(ovh, dur or 180_000, song, artist)
            lines = _dedup_sorted(lines)
            cache[k] = {"ts": _now(), "data": lines}
            _save_cache(cache)
            log(f"lyrics.ovh plain→sync: {_cut(artist, 24)} — {_cut(song, 32)} [{len(lines)}]", "INFO", "lyrics")
            return lines
    except Exception as e:
        log(f"Lyrics.ovh недоступен: {e}", "WARNING", "lyrics")

    # 5) Ничего не нашли
    log(f"Текст не найден: {song} — {artist}", "WARNING", "lyrics")
    cache[k] = {"ts": _now(), "data": []}
    _save_cache(cache)
    return []

__all__ = ["fetch_lyrics", "parse_lrclib_synced"]
