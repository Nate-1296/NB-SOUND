import json
from pathlib import Path
from tempfile import TemporaryDirectory

from core.discography import OrganizadorDiscografias


def test_organizador_mueve_a_bucket_por_release_type():
    with TemporaryDirectory() as td:
        base = Path(td)
        manifests = base / "manifests"
        tracks_dir = manifests / "tracks"
        albums_dir = manifests / "albums"
        tracks_dir.mkdir(parents=True)
        albums_dir.mkdir(parents=True)

        current = base / "library" / "artist" / "otros" / "old" / "01_song.mp3"
        current.parent.mkdir(parents=True)
        current.write_bytes(b"mp3")

        track = {
            "track_id": "t1",
            "canonical_artist": "Artist",
            "release_mbid": "rel-1",
            "album": "Album Uno",
            "ruta_actual": str(current),
        }
        album = {
            "album_id": "rel-1",
            "release_mbid": "rel-1",
            "release_type": "Album",
        }
        (tracks_dir / "t1.json").write_text(json.dumps(track), encoding="utf-8")
        (albums_dir / "rel-1.json").write_text(json.dumps(album), encoding="utf-8")

        org = OrganizadorDiscografias(manifests, base / "library", ia_client=None)
        out = org.ejecutar(dry_run=False)

        assert out["moves"] == 1
        moved = list((base / "library").rglob("01_song.mp3"))
        assert moved
        assert "albumes" in str(moved[0])
