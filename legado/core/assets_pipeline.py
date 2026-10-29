# =============================================================================
# core/assets_pipeline.py
#
# Pipeline de assets visuales para UI/CLI:
#   - Extrae portada embebida (APIC) desde el MP3 final.
#   - Descarga portadas estándar y HD desde Cover Art Archive o iTunes.
#   - Descarga imágenes de artista estándar y HD desde TheAudioDB, Deezer,
#     iTunes o Wikipedia.
#
# Este modulo es best-effort: nunca debe romper el pipeline principal.
# =============================================================================

from __future__ import annotations

import hashlib
import json
import re
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any
from urllib.parse import quote
import mimetypes

try:
    from mutagen.id3 import ID3, APIC
    _MUTAGEN_ID3_OK = True
except ImportError:
    _MUTAGEN_ID3_OK = False

from config.settings import (
    DEFAULT_ASSETS_DIR,
    ENABLE_COVER_ART_ARCHIVE,
    ENABLE_THEAUDIODB_ARTIST_IMAGES,
    ENABLE_ITUNES_COVER_FALLBACK,
    ENABLE_DEEZER_ARTIST_IMAGES,
    ENABLE_WIKIPEDIA_ARTIST_IMAGES,
    ENABLE_ITUNES_ARTIST_IMAGES,
    ASSETS_TIMEOUT_SEG,
    ASSETS_MAX_RETRIES,
    ASSETS_RETRY_BACKOFF_SEG,
    ASSETS_MIN_RESOLUTION,
    ASSETS_CACHE_TTL_SEG,
    ASSETS_NEGATIVE_CACHE_TTL_SEG,
    ASSETS_HD_MAX_IMAGE_BYTES,
    THEAUDIODB_API_KEY,
)
from domain.models import DecisionArchivo
from external.cache import CacheLocal
from infra.logger import obtener_logger

_log = obtener_logger("assets")
_NEGATIVE_CACHE_MARK = "__NO_ASSET__"
_USER_AGENT = "NB-SOUND/2.0 (local music library asset fetcher)"
_MANIFEST_LOCK = threading.Lock()


@dataclass
class AssetCandidate:
    provider_name: str
    asset_kind: str
    source_url: str
    width: int = 0
    height: int = 0
    mime: str = ""
    image_type: str = "portrait"
    license_hint: str = ""
    score_raw: float = 0.0
    score_final: float = 0.0
    reason: str = ""


@dataclass
class AssetFile:
    path: Path
    source_url: str = ""
    provider_name: str = ""
    width: int = 0
    height: int = 0
    mime: str = ""
    bytes_len: int = 0
    is_hd: bool = False


class PipelineAssets:
    def __init__(self, directorio_assets: Optional[Path] = None) -> None:
        self._dir = directorio_assets or DEFAULT_ASSETS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

        self._dir_track_covers = self._dir / "covers" / "tracks"
        self._dir_track_covers_hd = self._dir / "covers" / "tracks_hd"
        self._dir_album_covers = self._dir / "covers" / "albums"
        self._dir_album_covers_hd = self._dir / "covers" / "albums_hd"
        self._dir_artist_imgs = self._dir / "artists"
        self._dir_artist_imgs_hd = self._dir / "artists_hd"
        self._dir_cache_assets = self._dir / "cache"
        self._manifest = self._dir / "assets_manifest.jsonl"
        self._cache = CacheLocal(directorio=self._dir_cache_assets)

        for d in (
            self._dir_track_covers,
            self._dir_track_covers_hd,
            self._dir_album_covers,
            self._dir_album_covers_hd,
            self._dir_artist_imgs,
            self._dir_artist_imgs_hd,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def procesar(self, decision: DecisionArchivo) -> None:
        candidato = decision.candidato_elegido
        ruta_mp3 = decision.ruta_destino
        if candidato is None or ruta_mp3 is None:
            return

        asset_selection: dict[str, dict] = {
            "track": {"selected": None, "provider": None, "score": None, "alternatives": []},
            "album": {"selected": None, "provider": None, "score": None, "alternatives": []},
            "artist": {"selected": None, "provider": None, "score": None, "alternatives": []},
        }
        portada_track_file = None
        portada_track_hd_file = None
        try:
            portada_track_file, portada_track_hd_file = self._extraer_portada_embebida_info(ruta_mp3)
        except Exception as e:
            _log.debug(f"No se pudo extraer portada embebida: {e}")
        if portada_track_file is not None:
            asset_selection["track"] = {
                "selected": str(portada_track_file.path),
                "selected_hd": str(portada_track_hd_file.path) if portada_track_hd_file else None,
                "provider": "embedded_apic",
                "score": 1.0,
                "reason": "embedded artwork",
                "width": portada_track_file.width,
                "height": portada_track_file.height,
                "mime": portada_track_file.mime,
                "bytes": portada_track_file.bytes_len,
                "alternatives": [],
            }

        portada_album_file = None
        portada_album_hd_file = None
        if ENABLE_COVER_ART_ARCHIVE and candidato.release_id:
            try:
                portada_album_file, portada_album_hd_file = self._descargar_portadas_album(
                    candidato.release_id,
                    candidato.release_group_id,
                )
            except Exception as e:
                _log.debug(f"No se pudo descargar portada de album: {e}")
        if portada_album_file is not None:
            asset_selection["album"] = {
                "selected": str(portada_album_file.path),
                "selected_hd": str(portada_album_hd_file.path) if portada_album_hd_file else None,
                "provider": "cover_art_archive",
                "score": 0.92,
                "reason": "release cover from CAA",
                "width": portada_album_file.width,
                "height": portada_album_file.height,
                "mime": portada_album_file.mime,
                "bytes": portada_album_file.bytes_len,
                "alternatives": [],
            }
        if portada_album_file is None:
            try:
                portada_album_file, portada_album_hd_file = self._descargar_portadas_album_fallback(
                    artista=candidato.artista_principal,
                    album=candidato.album_oficial,
                )
            except Exception as e:
                _log.debug(f"No se pudo descargar portada fallback: {e}")
        if portada_album_file is not None and asset_selection["album"]["provider"] is None:
            asset_selection["album"] = {
                "selected": str(portada_album_file.path),
                "selected_hd": str(portada_album_hd_file.path) if portada_album_hd_file else None,
                "provider": "itunes_album_fallback",
                "score": 0.75,
                "reason": "itunes fallback",
                "width": portada_album_file.width,
                "height": portada_album_file.height,
                "mime": portada_album_file.mime,
                "bytes": portada_album_file.bytes_len,
                "alternatives": [],
            }
        if portada_track_hd_file is None and portada_album_hd_file is not None:
            portada_track_hd_file = portada_album_hd_file
            if asset_selection["track"]["selected"] is not None:
                asset_selection["track"]["selected_hd"] = str(portada_album_hd_file.path)
                asset_selection["track"]["hd_reason"] = "album hd fallback"

        imagen_artista_file = None
        imagen_artista_hd_file = None
        artist_candidates: list[AssetCandidate] = []
        if candidato.artista_principal:
            try:
                imagen_artista_file, imagen_artista_hd_file, artist_candidates = self._descargar_imagen_artista_assets(
                    candidato.artista_principal
                )
            except Exception as e:
                _log.debug(f"No se pudo descargar imagen de artista: {e}")
        if imagen_artista_file is not None and artist_candidates:
            top = artist_candidates[0]
            asset_selection["artist"] = {
                "selected": str(imagen_artista_file.path),
                "selected_hd": str(imagen_artista_hd_file.path) if imagen_artista_hd_file else None,
                "provider": top.provider_name,
                "score": top.score_final,
                "reason": top.reason or "best scored provider",
                "type": top.image_type,
                "license": top.license_hint,
                "width": imagen_artista_file.width,
                "height": imagen_artista_file.height,
                "mime": imagen_artista_file.mime,
                "bytes": imagen_artista_file.bytes_len,
                "alternatives": [
                    {"provider": c.provider_name, "score": c.score_final, "url": c.source_url, "type": c.image_type, "license": c.license_hint}
                    for c in artist_candidates[1:]
                ],
            }
        decision.esquema_explicacion.setdefault("asset_selection", asset_selection)

        self._registrar_manifest(
            decision=decision,
            portada_track=portada_track_file.path if portada_track_file else None,
            portada_album=portada_album_file.path if portada_album_file else None,
            artist_image=imagen_artista_file.path if imagen_artista_file else None,
            portada_track_hd=portada_track_hd_file.path if portada_track_hd_file else None,
            portada_album_hd=portada_album_hd_file.path if portada_album_hd_file else None,
            artist_image_hd=imagen_artista_hd_file.path if imagen_artista_hd_file else None,
            asset_selection=asset_selection,
        )

    def _extraer_portada_embebida(self, ruta_mp3: Path) -> Optional[Path]:
        asset, _asset_hd = self._extraer_portada_embebida_info(ruta_mp3)
        return asset.path if asset else None

    def _extraer_portada_embebida_info(self, ruta_mp3: Path) -> tuple[Optional[AssetFile], Optional[AssetFile]]:
        if not _MUTAGEN_ID3_OK:
            return None, None
        tags = ID3(str(ruta_mp3))
        apics = tags.getall("APIC")
        if not apics:
            return None, None

        frame = apics[0]
        if not isinstance(frame, APIC) or not frame.data:
            return None, None

        digest = hashlib.sha1(frame.data).hexdigest()
        info = _inspeccionar_imagen(frame.data, fallback_mime=frame.mime)
        if not info.valida:
            return None, None
        ext = _extension_por_mime(info.mime or frame.mime)
        destino = self._dir_track_covers / f"{digest}.{ext}"
        if not destino.exists():
            _escribir_bytes_atomico(destino, frame.data)
        asset = AssetFile(
            path=destino,
            provider_name="embedded_apic",
            width=info.width,
            height=info.height,
            mime=info.mime or frame.mime,
            bytes_len=len(frame.data),
        )
        asset_hd = None
        if _es_imagen_hd(info):
            destino_hd = self._dir_track_covers_hd / f"{digest}.{ext}"
            if not destino_hd.exists():
                _escribir_bytes_atomico(destino_hd, frame.data)
            asset_hd = AssetFile(
                path=destino_hd,
                provider_name="embedded_apic",
                width=info.width,
                height=info.height,
                mime=info.mime or frame.mime,
                bytes_len=len(frame.data),
                is_hd=True,
            )
        return asset, asset_hd

    def _descargar_portada_album(self, release_id: str, release_group_id: str = "") -> Optional[Path]:
        portada, _portada_hd = self._descargar_portadas_album(release_id, release_group_id)
        return portada.path if portada else None

    def _descargar_portadas_album(
        self,
        release_id: str,
        release_group_id: str = "",
    ) -> tuple[Optional[AssetFile], Optional[AssetFile]]:
        release_id = release_id.strip()
        release_group_id = (release_group_id or "").strip()

        lookups: list[tuple[str, str]] = []
        if release_id:
            lookups.append((f"https://coverartarchive.org/release/{quote(release_id)}", release_id))
        if release_group_id:
            lookups.append((f"https://coverartarchive.org/release-group/{quote(release_group_id)}", release_group_id))

        for metadata_url, key in lookups:
            data = _descargar_json(metadata_url, timeout=ASSETS_TIMEOUT_SEG, retries=ASSETS_MAX_RETRIES)
            standard_url, hd_urls = _seleccionar_urls_caa(data)
            if not standard_url:
                standard_url = f"{metadata_url}/front-500"
                hd_urls = [f"{metadata_url}/front"]

            standard = self._descargar_y_guardar_asset(
                url=standard_url,
                carpeta=self._dir_album_covers,
                prefijo=key,
                provider="cover_art_archive",
                strict=False,
            )
            if standard is None:
                continue
            hd = None
            for hd_url in hd_urls:
                hd = self._descargar_y_guardar_asset(
                    url=hd_url,
                    carpeta=self._dir_album_covers_hd,
                    prefijo=key,
                    provider="cover_art_archive",
                    strict=True,
                    require_hd=True,
                )
                if hd is not None:
                    break
            return standard, hd
        return None, None

    def _descargar_imagen_artista(self, artista: str) -> tuple[Optional[Path], list[AssetCandidate]]:
        standard, _hd, candidates = self._descargar_imagen_artista_assets(artista)
        return (standard.path if standard else None), candidates

    def _descargar_imagen_artista_assets(
        self,
        artista: str,
    ) -> tuple[Optional[AssetFile], Optional[AssetFile], list[AssetCandidate]]:
        nombre = artista.strip()
        if not nombre:
            return None, None, []
        selected, candidates = self._buscar_url_imagen_artista(nombre)
        imagen_url = selected.source_url if selected else ""
        if not imagen_url:
            return None, None, []
        folder = self._dir_artist_imgs / _slug_simple(nombre)
        folder.mkdir(parents=True, exist_ok=True)
        folder_hd = self._dir_artist_imgs_hd / _slug_simple(nombre)
        folder_hd.mkdir(parents=True, exist_ok=True)

        standard = self._descargar_y_guardar_asset(
            url=imagen_url,
            carpeta=folder,
            prefijo="avatar",
            provider=selected.provider_name if selected else "artist",
            strict=False,
            fixed_name="avatar",
        )
        if standard is None:
            return None, None, candidates

        if selected:
            selected.width = standard.width or selected.width
            selected.height = standard.height or selected.height
            selected.mime = standard.mime or selected.mime

        hd = self._descargar_y_guardar_asset(
            url=imagen_url,
            carpeta=folder_hd,
            prefijo="avatar",
            provider=selected.provider_name if selected else "artist",
            strict=True,
            require_hd=True,
            fixed_name="avatar",
        )
        return standard, hd, candidates

    def _buscar_url_imagen_artista(self, nombre: str) -> tuple[Optional[AssetCandidate], list[AssetCandidate]]:
        clave_cache = CacheLocal.construir_clave("assets_artist_lookup", {"artist": nombre})
        cacheado = self._cache.obtener(clave_cache)
        if isinstance(cacheado, str) and cacheado:
            if cacheado == _NEGATIVE_CACHE_MARK:
                return None, []
            return AssetCandidate(provider_name="cache", asset_kind="artist_image", source_url=cacheado, score_raw=0.99, score_final=0.99, reason="cached"), []

        proveedores: list[callable] = []
        if ENABLE_THEAUDIODB_ARTIST_IMAGES and THEAUDIODB_API_KEY:
            proveedores.append(lambda: self._provider_artist_theaudiodb(nombre))
        if ENABLE_DEEZER_ARTIST_IMAGES:
            proveedores.append(lambda: self._provider_artist_deezer(nombre))
        if ENABLE_ITUNES_ARTIST_IMAGES:
            proveedores.append(lambda: self._provider_artist_itunes(nombre))
        if ENABLE_WIKIPEDIA_ARTIST_IMAGES:
            proveedores.append(lambda: self._provider_artist_wikipedia(nombre))

        candidatos: list[AssetCandidate] = []
        for proveedor in proveedores:
            cand = proveedor()
            if cand and cand.source_url:
                cand.score_final = self._score_candidate(cand)
                candidatos.append(cand)
        if candidatos:
            candidatos.sort(key=lambda c: c.score_final, reverse=True)
            top = candidatos[0]
            self._cache.guardar_con_ttl(clave_cache, top.source_url, ASSETS_CACHE_TTL_SEG)
            return top, candidatos
        self._cache.guardar_con_ttl(clave_cache, _NEGATIVE_CACHE_MARK, ASSETS_NEGATIVE_CACHE_TTL_SEG)
        return None, []

    def _provider_artist_theaudiodb(self, nombre: str) -> Optional[AssetCandidate]:
        respuesta = _descargar_json(
            f"https://www.theaudiodb.com/api/v1/json/{quote(THEAUDIODB_API_KEY)}/search.php?s={quote(nombre)}",
            timeout=ASSETS_TIMEOUT_SEG,
            retries=ASSETS_MAX_RETRIES,
        )
        if not respuesta:
            return None
        artistas = respuesta.get("artists") or []
        if not isinstance(artistas, list) or not artistas:
            return None
        url = _seleccionar_url_imagen_artista(artistas[0])
        if not url:
            return None
        return AssetCandidate(
            provider_name="theaudiodb",
            asset_kind="artist_image",
            source_url=url,
            width=720,
            height=720,
            image_type="thumb",
            score_raw=0.8,
            reason="theaudiodb artist image",
        )

    def _provider_artist_deezer(self, nombre: str) -> Optional[AssetCandidate]:
        respuesta = _descargar_json(
            f"https://api.deezer.com/search/artist?q={quote(nombre)}",
            timeout=ASSETS_TIMEOUT_SEG,
            retries=ASSETS_MAX_RETRIES,
        )
        if not respuesta:
            return None
        data = respuesta.get("data") or []
        if not isinstance(data, list) or not data:
            return None
        primero = data[0] if isinstance(data[0], dict) else {}
        sizes = {
            "picture_xl": 1000,
            "picture_big": 500,
            "picture_medium": 250,
            "picture": 0,
        }
        for key in ("picture_xl", "picture_big", "picture_medium", "picture"):
            value = str(primero.get(key) or "").strip()
            if value:
                size = sizes.get(key, 0)
                return AssetCandidate(
                    provider_name="deezer",
                    asset_kind="artist_image",
                    source_url=value,
                    width=size,
                    height=size,
                    image_type="portrait",
                    score_raw=0.72,
                    reason=f"deezer artist {key}",
                )
        return None

    def _provider_artist_itunes(self, nombre: str) -> Optional[AssetCandidate]:
        respuesta = _descargar_json(
            f"https://itunes.apple.com/search?term={quote(nombre)}&entity=musicArtist&limit=3",
            timeout=ASSETS_TIMEOUT_SEG,
            retries=ASSETS_MAX_RETRIES,
        )
        if not respuesta:
            return None
        results = respuesta.get("results") or []
        if not isinstance(results, list):
            return None
        for row in results:
            if not isinstance(row, dict):
                continue
            preview = str(row.get("artworkUrl100") or "").strip()
            if preview:
                return AssetCandidate(provider_name="itunes", asset_kind="artist_image", source_url=_itunes_artwork_variant(preview, 600), width=600, height=600, image_type="portrait", score_raw=0.66, reason="itunes artist artwork")
        return None

    def _provider_artist_wikipedia(self, nombre: str) -> Optional[AssetCandidate]:
        respuesta = _descargar_json(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(nombre)}",
            timeout=ASSETS_TIMEOUT_SEG,
            retries=ASSETS_MAX_RETRIES,
        )
        if not respuesta:
            return None
        original = respuesta.get("originalimage") or {}
        thumbnail = respuesta.get("thumbnail") or {}
        image = original if isinstance(original, dict) and original.get("source") else thumbnail
        if not isinstance(image, dict):
            return None
        source = str(image.get("source") or "").strip()
        if not source:
            return None
        return AssetCandidate(
            provider_name="wikipedia",
            asset_kind="artist_image",
            source_url=source,
            width=int(image.get("width") or 0),
            height=int(image.get("height") or 0),
            image_type="portrait",
            license_hint="wikipedia_summary",
            score_raw=0.58,
            reason="wikipedia summary image",
        )

    @staticmethod
    def _score_candidate(candidate: AssetCandidate) -> float:
        score = candidate.score_raw
        min_resolution_bonus = 0.05 if min(candidate.width or ASSETS_MIN_RESOLUTION, candidate.height or ASSETS_MIN_RESOLUTION) >= ASSETS_MIN_RESOLUTION else -0.08
        provider_bonus = {
            "theaudiodb": 0.10,
            "deezer": 0.07,
            "itunes": 0.05,
            "wikipedia": 0.02,
        }.get(candidate.provider_name, 0.0)
        return round(max(0.0, min(1.0, score + provider_bonus + min_resolution_bonus)), 4)

    def _descargar_portada_album_fallback(self, artista: str, album: str) -> Optional[Path]:
        portada, _portada_hd = self._descargar_portadas_album_fallback(artista, album)
        return portada.path if portada else None

    def _descargar_portadas_album_fallback(
        self,
        artista: str,
        album: str,
    ) -> tuple[Optional[AssetFile], Optional[AssetFile]]:
        if not ENABLE_ITUNES_COVER_FALLBACK:
            return None, None
        artista = (artista or "").strip()
        album = (album or "").strip()
        if not artista or not album:
            return None, None
        clave_cache = CacheLocal.construir_clave("assets_album_cover_lookup", {"artist": artista, "album": album})
        cacheado = self._cache.obtener(clave_cache)
        if not isinstance(cacheado, (str, dict)):
            query = quote(f"{artista} {album}")
            data = _descargar_json(
                f"https://itunes.apple.com/search?term={query}&entity=album&limit=5",
                timeout=ASSETS_TIMEOUT_SEG,
                retries=ASSETS_MAX_RETRIES,
            )
            url = _seleccionar_url_itunes(data, album)
            if url:
                cacheado = {"standard": url, "hd_candidates": _itunes_hd_candidates(url)}
                self._cache.guardar_con_ttl(clave_cache, cacheado, ASSETS_CACHE_TTL_SEG)
            else:
                self._cache.guardar_con_ttl(clave_cache, _NEGATIVE_CACHE_MARK, ASSETS_NEGATIVE_CACHE_TTL_SEG)
                cacheado = _NEGATIVE_CACHE_MARK
        if cacheado == _NEGATIVE_CACHE_MARK:
            return None, None
        if isinstance(cacheado, str):
            standard_url = cacheado
            hd_candidates = _itunes_hd_candidates(cacheado)
        elif isinstance(cacheado, dict):
            standard_url = str(cacheado.get("standard") or "")
            hd_candidates = [str(u) for u in (cacheado.get("hd_candidates") or []) if u]
        else:
            standard_url = ""
            hd_candidates = []
        if not standard_url:
            return None, None

        standard = self._descargar_y_guardar_asset(
            url=standard_url,
            carpeta=self._dir_album_covers,
            prefijo="itunes",
            provider="itunes",
            strict=False,
        )
        if standard is None:
            return None, None

        hd = None
        for url_hd in hd_candidates:
            hd = self._descargar_y_guardar_asset(
                url=url_hd,
                carpeta=self._dir_album_covers_hd,
                prefijo="itunes",
                provider="itunes",
                strict=True,
                require_hd=True,
            )
            if hd is not None:
                break
        return standard, hd

    def _registrar_manifest(
        self,
        decision: DecisionArchivo,
        portada_track: Optional[Path],
        portada_album: Optional[Path],
        artist_image: Optional[Path],
        portada_track_hd: Optional[Path] = None,
        portada_album_hd: Optional[Path] = None,
        artist_image_hd: Optional[Path] = None,
        asset_selection: Optional[dict] = None,
    ) -> None:
        candidato = decision.candidato_elegido
        if candidato is None:
            return

        row = {
            "schema_version": 2,
            "obtained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "selection_policy": {
                "album": "cover_art_archive_release_metadata -> cover_art_archive_release_group_metadata -> itunes_album",
                "album_hd": "original_or_1200_validated -> itunes_hd_best_effort",
                "artist": "theaudiodb -> deezer -> itunes -> wikipedia",
                "artist_hd": "same provider validated at hd threshold",
                "track": "embedded_apic_first",
                "track_hd": "embedded_apic_hd_else_album_hd",
            },
            "archivo": str(decision.ruta_destino) if decision.ruta_destino else None,
            "recording_id": candidato.recording_id,
            "release_id": candidato.release_id,
            "artista": candidato.artista_principal,
            "album": candidato.album_oficial,
            "track_cover": str(portada_track) if portada_track else None,
            "album_cover": str(portada_album) if portada_album else None,
            "artist_avatar": str(artist_image) if artist_image else None,
            "track_cover_hd": str(portada_track_hd) if portada_track_hd else None,
            "album_cover_hd": str(portada_album_hd) if portada_album_hd else None,
            "artist_avatar_hd": str(artist_image_hd) if artist_image_hd else None,
            "asset_selection": asset_selection or {},
        }
        with _MANIFEST_LOCK:
            with open(self._manifest, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _descargar_y_guardar_asset(
        self,
        url: str,
        carpeta: Path,
        prefijo: str,
        provider: str,
        *,
        strict: bool,
        require_hd: bool = False,
        fixed_name: str = "",
    ) -> Optional[AssetFile]:
        img = _descargar_bytes(
            url,
            timeout=ASSETS_TIMEOUT_SEG,
            retries=ASSETS_MAX_RETRIES,
            max_bytes=ASSETS_HD_MAX_IMAGE_BYTES,
        )
        if not img:
            return None
        info = _inspeccionar_imagen(img, fallback_mime=mimetypes.guess_type(url)[0] or "")
        if not info.valida:
            _log.debug(f"Asset invalido descartado ({provider}): {url}")
            return None
        if require_hd and not _es_imagen_hd(info):
            _log.debug(
                f"Asset HD insuficiente descartado ({provider}): "
                f"{url} ({info.width}x{info.height})"
            )
            return None

        ext = _extension_por_mime(info.mime) if info.mime else _extension_desde_url(url)
        digest = hashlib.sha1(img).hexdigest()
        nombre = f"{fixed_name}.{ext}" if fixed_name else f"{prefijo}_{digest}.{ext}"
        destino = carpeta / nombre
        if not destino.exists():
            _escribir_bytes_atomico(destino, img)
        return AssetFile(
            path=destino,
            source_url=url,
            provider_name=provider,
            width=info.width,
            height=info.height,
            mime=info.mime,
            bytes_len=len(img),
            is_hd=require_hd,
        )


from utils.network import safe_download_bytes, safe_download_json

def _descargar_bytes(
    url: str,
    timeout: int,
    retries: int = 0,
    max_bytes: Optional[int] = None,
) -> Optional[bytes]:
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.9,application/json;q=0.8,*/*;q=0.5",
    }
    return safe_download_bytes(
        url=url,
        timeout=timeout,
        retries=retries,
        max_bytes=max_bytes,
        headers=headers,
        backoff_factor=ASSETS_RETRY_BACKOFF_SEG
    )


def _descargar_json(url: str, timeout: int, retries: int = 0) -> Optional[Any]:
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json, text/plain, */*",
    }
    return safe_download_json(
        url=url,
        timeout=timeout,
        retries=retries,
        headers=headers,
        backoff_factor=ASSETS_RETRY_BACKOFF_SEG
    )


@dataclass
class _ImageInfo:
    width: int = 0
    height: int = 0
    mime: str = ""
    valida: bool = False


def _inspeccionar_imagen(data: bytes, fallback_mime: str = "") -> _ImageInfo:
    if not data:
        return _ImageInfo(mime=fallback_mime or "", valida=False)

    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return _ImageInfo(width=int(width), height=int(height), mime="image/png", valida=width > 0 and height > 0)

    if data.startswith(b"\xff\xd8"):
        pos = 2
        while pos + 9 < len(data):
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            pos += 2
            if marker in {0xD8, 0xD9}:
                continue
            if pos + 2 > len(data):
                break
            length = struct.unpack(">H", data[pos:pos + 2])[0]
            if length < 2 or pos + length > len(data):
                break
            if marker in {
                0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
            } and pos + 7 <= len(data):
                height = struct.unpack(">H", data[pos + 3:pos + 5])[0]
                width = struct.unpack(">H", data[pos + 5:pos + 7])[0]
                return _ImageInfo(width=int(width), height=int(height), mime="image/jpeg", valida=width > 0 and height > 0)
            pos += length
        return _ImageInfo(mime="image/jpeg", valida=True)

    if data.startswith(b"RIFF") and len(data) >= 30 and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X" and len(data) >= 30:
            width = int.from_bytes(data[24:27], "little") + 1
            height = int.from_bytes(data[27:30], "little") + 1
            return _ImageInfo(width=width, height=height, mime="image/webp", valida=width > 0 and height > 0)
        if chunk == b"VP8 " and len(data) >= 30:
            width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            return _ImageInfo(width=width, height=height, mime="image/webp", valida=width > 0 and height > 0)
        if chunk == b"VP8L" and len(data) >= 25:
            b0, b1, b2, b3 = data[21], data[22], data[23], data[24]
            width = 1 + (((b1 & 0x3F) << 8) | b0)
            height = 1 + (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
            return _ImageInfo(width=width, height=height, mime="image/webp", valida=width > 0 and height > 0)
        return _ImageInfo(mime="image/webp", valida=True)

    return _ImageInfo(mime=fallback_mime or "", valida=False)


def _es_imagen_hd(info: _ImageInfo) -> bool:
    if not info.valida:
        return False
    if info.width <= 0 or info.height <= 0:
        return False
    return min(info.width, info.height) >= 1000


def _escribir_bytes_atomico(destino: Path, data: bytes) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(destino)


def _seleccionar_urls_caa(data: Optional[Any]) -> tuple[str, list[str]]:
    if not isinstance(data, dict):
        return "", []
    imagenes = data.get("images") or []
    if not isinstance(imagenes, list):
        return "", []
    frontales = [img for img in imagenes if isinstance(img, dict) and img.get("front")]
    candidatas = frontales or [img for img in imagenes if isinstance(img, dict)]
    if not candidatas:
        return "", []
    imagen = candidatas[0]
    thumbs = imagen.get("thumbnails") or {}
    if not isinstance(thumbs, dict):
        thumbs = {}
    standard = str(thumbs.get("500") or thumbs.get("large") or thumbs.get("1200") or imagen.get("image") or "").strip()
    hd_urls = []
    original = str(imagen.get("image") or "").strip()
    if original:
        hd_urls.append(original)
    for key in ("1200", "500", "large"):
        url = str(thumbs.get(key) or "").strip()
        if url and url not in hd_urls:
            hd_urls.append(url)
    return standard, hd_urls


def _seleccionar_url_itunes(data: Optional[dict], album_objetivo: str) -> str:
    if not isinstance(data, dict):
        return ""
    resultados = data.get("results") or []
    if not isinstance(resultados, list) or not resultados:
        return ""
    objetivo = album_objetivo.strip().lower()
    for row in resultados:
        if not isinstance(row, dict):
            continue
        nombre_album = str(row.get("collectionName") or "").strip().lower()
        portada = str(row.get("artworkUrl100") or "").strip()
        if not portada:
            continue
        if objetivo and objetivo in nombre_album:
            return _itunes_artwork_variant(portada, 600)
    primera = resultados[0] if isinstance(resultados[0], dict) else {}
    portada = str(primera.get("artworkUrl100") or "").strip()
    return _itunes_artwork_variant(portada, 600) if portada else ""


def _itunes_artwork_variant(url: str, size: int) -> str:
    base = (url or "").strip()
    if not base:
        return ""
    replaced = re.sub(r"\d+x\d+bb", f"{size}x{size}bb", base)
    if replaced != base:
        return replaced
    replaced = re.sub(r"\d+x\d+-\d+", f"{size}x{size}bb", base)
    if replaced != base:
        return replaced
    for token in ("100x100bb", "100x100-75", "100x100"):
        if token in base:
            return base.replace(token, f"{size}x{size}bb")
    return base


def _itunes_hd_candidates(url: str) -> list[str]:
    candidates = []
    for size in (3000, 2000, 1200, 1000, 600):
        variant = _itunes_artwork_variant(url, size)
        if variant and variant not in candidates:
            candidates.append(variant)
    return candidates


def _seleccionar_url_imagen_artista(artist: dict) -> str:
    if not isinstance(artist, dict):
        return ""
    for key in (
        "strArtistThumb",
        "strArtistWideThumb",
        "strArtistFanart",
        "strArtistFanart2",
        "strArtistFanart3",
        "strArtistFanart4",
    ):
        value = str(artist.get(key) or "").strip()
        if value:
            return value
    return ""


def _extension_desde_url(url: str) -> str:
    guess, _ = mimetypes.guess_type(url)
    if guess:
        if "png" in guess:
            return "png"
        if "jpeg" in guess or "jpg" in guess:
            return "jpg"
        if "webp" in guess:
            return "webp"
    base = url.split("?", 1)[0].lower()
    if base.endswith(".png"):
        return "png"
    if base.endswith(".webp"):
        return "webp"
    return "jpg"


def _extension_por_mime(mime: str) -> str:
    m = (mime or "").lower()
    if "png" in m:
        return "png"
    if "jpeg" in m or "jpg" in m:
        return "jpg"
    if "webp" in m:
        return "webp"
    return "bin"


def _slug_simple(texto: str) -> str:
    out = []
    for c in texto.lower():
        if c.isalnum():
            out.append(c)
        elif c in {" ", "-", "_"}:
            out.append("_")
    slug = "".join(out).strip("_")
    return slug or "desconocido"
