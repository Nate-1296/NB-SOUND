from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

from config.settings import (
    ENABLE_LYRICS_ENRICHMENT,
    ENABLE_LRCLIB,
    ENABLE_LYRICS_OVH,
    LYRICS_TIMEOUT_SEG,
    LYRICS_MAX_RETRIES,
    LYRICS_RETRY_BACKOFF_SEG,
    LYRICS_SUGGEST_LIMIT,
)
from infra.logger import obtener_logger
from utils.text import normalizar_titulo, para_comparacion, similitud_combinada

_log = obtener_logger("lyrics")


@dataclass
class LyricsResult:
    status: str = "not_found"  # found | partial | not_found | blocked | unsupported
    provider: str = ""
    plain_lyrics: str = ""
    synced_lyrics: str = ""
    language: Optional[str] = None
    instrumental: bool = False
    is_translation: bool = False
    confidence: float = 0.0
    match_method: str = ""
    fetched_at: str = ""


class LyricsClient:
    def __init__(self) -> None:
        self._enabled = ENABLE_LYRICS_ENRICHMENT

    @property
    def active(self) -> bool:
        return self._enabled

    def fetch(
        self,
        artist: str,
        title: str,
        duration: Optional[float] = None,
        album: str = "",
    ) -> LyricsResult:
        if not self._enabled:
            return LyricsResult(status="unsupported")

        artist = (artist or "").strip()
        title = (title or "").strip()
        if not artist or not title:
            return LyricsResult(status="partial", match_method="missing_artist_or_title")

        blocked: Optional[LyricsResult] = None
        if ENABLE_LRCLIB:
            result = self._from_lrclib(artist, title, duration)
            if result.status in {"found", "partial", "blocked"}:
                if result.status == "blocked":
                    blocked = result
                else:
                    return result
            if blocked is None:
                result = self._from_lrclib_search(artist, title, duration, album)
                if result.status in {"found", "partial"}:
                    return result
                if result.status == "blocked":
                    blocked = result

        if ENABLE_LYRICS_OVH:
            result = self._from_lyrics_ovh(artist, title)
            if result.status in {"found", "partial", "blocked"}:
                if result.status == "blocked":
                    blocked = blocked or result
                else:
                    return result
            result = self._from_lyrics_ovh_suggest(artist, title)
            if result.status in {"found", "partial"}:
                return result
            if result.status == "blocked":
                blocked = blocked or result

        if blocked is not None:
            return blocked
        return LyricsResult(status="not_found", match_method="all_providers_exhausted")

    def _from_lrclib(self, artist: str, title: str, duration: Optional[float]) -> LyricsResult:
        base = f"https://lrclib.net/api/get?artist_name={quote(artist)}&track_name={quote(title)}"
        if duration:
            base += f"&duration={int(round(duration))}"
        data = _fetch_json(base)
        if isinstance(data, dict) and data.get("__blocked__"):
            return LyricsResult(status="blocked", provider="lrclib", match_method="rate_limited")
        if not isinstance(data, dict) or not data:
            return LyricsResult(status="not_found", provider="lrclib")

        return _result_from_lrclib_payload(data, match_method="lrclib_get")

    def _from_lrclib_search(
        self,
        artist: str,
        title: str,
        duration: Optional[float],
        album: str = "",
    ) -> LyricsResult:
        query = quote(f"{artist} {title}")
        data = _fetch_json(f"https://lrclib.net/api/search?q={query}")
        if isinstance(data, dict) and data.get("__blocked__"):
            return LyricsResult(status="blocked", provider="lrclib", match_method="rate_limited")
        if not isinstance(data, list):
            return LyricsResult(status="not_found", provider="lrclib", match_method="lrclib_search_empty")

        scored: list[tuple[float, dict]] = []
        for row in data:
            if not isinstance(row, dict):
                continue
            score = _score_lrclib_row(row, artist, title, duration, album)
            if score >= 0.72:
                scored.append((score, row))
        if not scored:
            return LyricsResult(status="not_found", provider="lrclib", match_method="lrclib_search_no_match")

        scored.sort(key=lambda item: item[0], reverse=True)
        result = _result_from_lrclib_payload(scored[0][1], match_method="lrclib_search")
        result.confidence = max(result.confidence, min(0.9, scored[0][0]))
        return result

    def _from_lyrics_ovh(self, artist: str, title: str) -> LyricsResult:
        data = _fetch_json(f"https://api.lyrics.ovh/v1/{quote(artist)}/{quote(title)}")
        if isinstance(data, dict) and data.get("__blocked__"):
            return LyricsResult(status="blocked", provider="lyrics_ovh", match_method="rate_limited")
        if not isinstance(data, dict) or not data:
            return LyricsResult(status="not_found", provider="lyrics_ovh")

        plain = str(data.get("lyrics") or "").strip()
        if not plain:
            return LyricsResult(status="not_found", provider="lyrics_ovh")

        return LyricsResult(
            status="partial",
            provider="lyrics_ovh",
            plain_lyrics=plain,
            confidence=0.65,
            match_method="lyrics_ovh_title_artist",
            fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    def _from_lyrics_ovh_suggest(self, artist: str, title: str) -> LyricsResult:
        if LYRICS_SUGGEST_LIMIT <= 0:
            return LyricsResult(status="not_found", provider="lyrics_ovh", match_method="suggest_disabled")
        query = quote(f"{artist} {title}")
        data = _fetch_json(f"https://api.lyrics.ovh/suggest/{query}")
        if isinstance(data, dict) and data.get("__blocked__"):
            return LyricsResult(status="blocked", provider="lyrics_ovh", match_method="rate_limited")
        rows = data.get("data") if isinstance(data, dict) else []
        if not isinstance(rows, list):
            return LyricsResult(status="not_found", provider="lyrics_ovh", match_method="suggest_empty")

        intentos = 0
        for row in rows:
            if intentos >= LYRICS_SUGGEST_LIMIT:
                break
            if not isinstance(row, dict):
                continue
            candidate_title = str(row.get("title_short") or row.get("title") or "").strip()
            candidate_artist = ""
            artist_obj = row.get("artist") or {}
            if isinstance(artist_obj, dict):
                candidate_artist = str(artist_obj.get("name") or "").strip()
            if _score_text_match(candidate_artist, artist, candidate_title, title) < 0.72:
                continue
            intentos += 1
            result = self._from_lyrics_ovh(candidate_artist or artist, candidate_title or title)
            if result.status in {"found", "partial"}:
                result.match_method = "lyrics_ovh_suggest"
                result.confidence = max(result.confidence, 0.72)
                return result
        return LyricsResult(status="not_found", provider="lyrics_ovh", match_method="suggest_no_match")


def _result_from_lrclib_payload(data: dict, match_method: str) -> LyricsResult:
    plain = str(data.get("plainLyrics") or "").strip()
    synced = str(data.get("syncedLyrics") or "").strip()
    instrumental = bool(data.get("instrumental") or False)

    if not plain and not synced:
        return LyricsResult(status="not_found", provider="lrclib", match_method=match_method)

    return LyricsResult(
        status="found" if plain else "partial",
        provider="lrclib",
        plain_lyrics=plain,
        synced_lyrics=synced,
        language=str(data.get("language") or "").strip() or None,
        instrumental=instrumental,
        confidence=0.93 if plain and synced else 0.82,
        match_method=match_method,
        fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def _score_lrclib_row(
    row: dict,
    artist: str,
    title: str,
    duration: Optional[float],
    album: str,
) -> float:
    candidate_artist = str(row.get("artistName") or "").strip()
    candidate_title = str(row.get("trackName") or row.get("name") or "").strip()
    candidate_album = str(row.get("albumName") or "").strip()
    score = _score_text_match(candidate_artist, artist, candidate_title, title)

    if album and candidate_album:
        score = (score * 0.85) + (similitud_combinada(candidate_album, album) * 0.15)

    if duration:
        try:
            candidate_duration = float(row.get("duration") or 0.0)
        except (TypeError, ValueError):
            candidate_duration = 0.0
        if candidate_duration > 0:
            delta = abs(candidate_duration - float(duration))
            if delta <= 3:
                score += 0.08
            elif delta <= 10:
                score += 0.03
            elif delta > 30:
                score -= 0.18

    return round(max(0.0, min(1.0, score)), 4)


def _score_text_match(candidate_artist: str, artist: str, candidate_title: str, title: str) -> float:
    title_score = similitud_combinada(
        normalizar_titulo(candidate_title),
        normalizar_titulo(title),
    )
    artist_score = similitud_combinada(
        para_comparacion(candidate_artist),
        para_comparacion(artist),
    )
    return round((title_score * 0.62) + (artist_score * 0.38), 4)


def _fetch_json(url: str) -> Optional[object]:
    from utils.network import _SAFE_OPENER
    for intento in range(1, LYRICS_MAX_RETRIES + 2):
        try:
            req = Request(url, headers={"User-Agent": "NB-SOUND/2.0"})
            with _SAFE_OPENER.open(req, timeout=LYRICS_TIMEOUT_SEG) as resp:
                if resp.status >= 400:
                    return None
                payload = resp.read().decode("utf-8", errors="replace")
                return json.loads(payload)
        except HTTPError as e:
            if e.code == 429:
                return {"__blocked__": True}
            if e.code in {500, 502, 503, 504} and intento <= LYRICS_MAX_RETRIES:
                time.sleep(LYRICS_RETRY_BACKOFF_SEG * intento)
                continue
            return None
        except (URLError, TimeoutError, json.JSONDecodeError):
            if intento <= LYRICS_MAX_RETRIES:
                time.sleep(LYRICS_RETRY_BACKOFF_SEG * intento)
                continue
            return None
        except Exception as e:
            _log.debug(f"Lyrics fetch error ({url}): {e}")
            return None
    return None
