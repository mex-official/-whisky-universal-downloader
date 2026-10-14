from urllib.parse import urlparse
import ipaddress
import socket

def is_valid_url(value: str) -> bool:
    try:
        p = urlparse(value.strip())
        if p.scheme not in ("http", "https") or not p.hostname:
            return False
        if p.username or p.password:
            return False
        host = p.hostname.lower().rstrip(".")
        if host == "localhost" or host.endswith((".local", ".internal")):
            return False
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_global
        except ValueError:
            return "." in host and not host.startswith(".")
    except (ValueError, TypeError):
        return False
