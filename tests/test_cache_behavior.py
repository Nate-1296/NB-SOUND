import tempfile
import time
import unittest
from pathlib import Path

from external.cache import CacheLocal


class CacheBehaviorTests(unittest.TestCase):
    def test_key_contains_prefix_and_routes_subfolder(self):
        with tempfile.TemporaryDirectory() as td:
            cache = CacheLocal(directorio=Path(td))
            key = CacheLocal.construir_clave("shazam_res", {"id": "abc"})
            cache.guardar(key, {"ok": True})
            expected = Path(td) / "shazam" / f"{key}.json"
            self.assertTrue(expected.exists())
            self.assertEqual(cache.obtener(key), {"ok": True})

    def test_negative_cache_ttl_expires(self):
        with tempfile.TemporaryDirectory() as td:
            cache = CacheLocal(directorio=Path(td))
            key = CacheLocal.construir_clave("mb_isrc", {"isrc": "USAAA"})
            cache.guardar_con_ttl(key, [], ttl=1)
            self.assertEqual(cache.obtener_con_ttl(key, ttl=1), [])
            time.sleep(1.1)
            self.assertIsNone(cache.obtener_con_ttl(key, ttl=1))


if __name__ == "__main__":
    unittest.main()
