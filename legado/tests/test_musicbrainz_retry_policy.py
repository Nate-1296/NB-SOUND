import unittest

from external.musicbrainz_client import _clasificar_error_mb


class DummyError(Exception):
    def __init__(self, msg: str, status=None):
        super().__init__(msg)
        self.status = status


class RetryPolicyTests(unittest.TestCase):
    def test_404_not_retryable_and_negative_cacheable(self):
        retry, neg, cat = _clasificar_error_mb(DummyError("Not found", status=404))
        self.assertFalse(retry)
        self.assertTrue(neg)
        self.assertEqual(cat, "not_found")

    def test_429_retryable(self):
        retry, neg, cat = _clasificar_error_mb(DummyError("rate limited", status=429))
        self.assertTrue(retry)
        self.assertFalse(neg)
        self.assertEqual(cat, "rate_limited")

    def test_timeout_retryable(self):
        retry, neg, cat = _clasificar_error_mb(DummyError("request timed out"))
        self.assertTrue(retry)
        self.assertFalse(neg)
        self.assertEqual(cat, "timeout")


if __name__ == "__main__":
    unittest.main()
