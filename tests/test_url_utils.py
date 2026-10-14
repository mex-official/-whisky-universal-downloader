import pytest
from url_utils import is_valid_url

@pytest.mark.parametrize("url", [
 "https://youtube.com/watch?v=abc", "https://www.youtube.com/shorts/abc", "https://youtu.be/abc",
 "https://www.instagram.com/reel/abc", "https://www.tiktok.com/@user/video/123",
 "https://x.com/user/status/123", "https://twitter.com/user/status/123", "https://pin.it/abc",
 "https://www.pinterest.com/pin/123", "https://www.reddit.com/r/test/comments/abc/title",
 "https://redd.it/abc", "http://youtube.com/watch?v=abc",
])
def test_supported_platforms(url):
    # No DNS lookup in unit tests; production validation resolves DNS.
    assert is_valid_url(url, resolve_dns=False)

@pytest.mark.parametrize("url", [
 "", "example.com", "javascript:alert(1)", "file:///etc/passwd", "ftp://youtube.com/a",
 "http://localhost", "http://localhost.localdomain", "http://127.0.0.1", "http://10.0.0.1",
 "http://192.168.1.1", "http://169.254.169.254/latest/meta-data", "http://[::1]/",
 "http://[fc00::1]/", "https://user:pass@youtube.com/a", "https://evil.example/video",
 "https://youtube.com.evil.example/a", "https://foo.local/a", "https://foo.internal/a",
 "https://youtube.com:bad/a", "https://", None, 42,
])
def test_rejected_urls(url):
    assert not is_valid_url(url, resolve_dns=False)

def test_dns_failure_fails_closed(monkeypatch):
    import url_utils
    monkeypatch.setattr(url_utils.socket, "getaddrinfo", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    assert not is_valid_url("https://youtube.com/watch?v=abc")

def test_dns_private_ip_fails_closed(monkeypatch):
    import url_utils
    monkeypatch.setattr(url_utils.socket, "getaddrinfo", lambda *a, **k: [(None,None,None,None,("127.0.0.1",0))])
    assert not is_valid_url("https://youtube.com/watch?v=abc")
