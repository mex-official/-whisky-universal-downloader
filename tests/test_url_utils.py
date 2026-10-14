import unittest
from url_utils import is_valid_url

class URLTests(unittest.TestCase):
    def test_valid_https(self):
        self.assertTrue(is_valid_url("https://example.com/video"))

    def test_valid_http(self):
        self.assertTrue(is_valid_url("http://example.com"))

    def test_reject_missing_scheme(self):
        self.assertFalse(is_valid_url("example.com"))

    def test_reject_javascript(self):
        self.assertFalse(is_valid_url("javascript:alert(1)"))

    def test_reject_localhost(self):
        self.assertFalse(is_valid_url("http://localhost"))

    def test_reject_credentials(self):
        self.assertFalse(is_valid_url("https://user:pass@example.com"))

    def test_reject_private_ip(self):
        self.assertFalse(is_valid_url("http://127.0.0.1"))

    def test_reject_empty(self):
        self.assertFalse(is_valid_url(""))

if __name__ == "__main__":
    unittest.main()
