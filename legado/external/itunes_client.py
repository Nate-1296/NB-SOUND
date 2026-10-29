from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

from external.cache import CacheLocal
from infra.logger import obtener_logger

_log = obtener_logger("itunes_client")


@dataclass
class ItunesTrackHint:
    artist: str = ""
    title: str = ""
    collection: str = ""
    isrc: Optional[str] = None
    duration_sec: Optional[float] = None


class ClienteItunes:
    """Cliente mínimo para iTunes Search API (gratuita, sin API key)."""

    BASE_URL = "https://itunes.apple.com/search"

    def __init__(self, cache: CacheLocal, timeout_seg: int = 8) -> None:
        self._cache = cache
        self._timeout = timeout_seg

    def buscar_hint(self, artist: str, title: str) -> Optional[ItunesTrackHint]:
        if not artist and not title:
            return None

        key = CacheLocal.construir_clave("itunes_search", {"a": artist, "t": title})
        cached = self._cache.obtener(key)
        if cached is None:
            url = self._build_url(artist, title)
            cached = self._request_json(url)
            self._cache.guardar(key, cached if cached is not None else {})

        if not cached or not isinstance(cached, dict):
            return None
        results = cached.get("results") or []
        if not results:
            return None

        best = results[0]
        return ItunesTrackHint(
            artist=str(best.get("artistName") or ""),
            title=str(best.get("trackName") or ""),
            collection=str(best.get("collectionName") or ""),
            isrc=(best.get("isrc") or None),
            duration_sec=(best.get("trackTimeMillis") or 0) / 1000 if best.get("trackTimeMillis") else None,
        )

    def _build_url(self, artist: str, title: str) -> str:
        term = f"{artist} {title}".strip()
        params = urllib.parse.urlencode({
            "term": term,
            "entity": "song",
            "limit": 5,
        })
        return f"{self.BASE_URL}?{params}"

    def _request_json(self, url: str) -> Optional[dict]:
        from utils.network import safe_download_json
        try:
            return safe_download_json(url, timeout=self._timeout, headers={"User-Agent": "NBSoundLocal/2.0"})
        except Exception as e:
            _log.debug(f"iTunes lookup failed: {e}")
            return None
