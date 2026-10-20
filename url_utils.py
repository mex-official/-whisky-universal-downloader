
"""Strict URL validation for Whisky Universal Downloader.

This module validates media-platform URLs and optionally checks DNS answers.
It does not independently secure HTTP redirects or DNS rebinding at connection
time. Those protections must also be enforced by the downloader.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import socket
from typing import Optional, Tuple
from urllib.parse import urlsplit, urlunsplit


MAX_URL_LENGTH = 2048

ALLOWED_SCHEMES = frozenset({"http", "https"})
ALLOWED_PORTS = {"http": 80, "https": 443}

ALLOWED_PLATFORMS = {
    "youtube": frozenset({
        "youtube.com", "youtu.be", "youtube-nocookie.com",
    }),
    "facebook": frozenset({"facebook.com", "fb.com", "fb.watch"}),
    "tiktok": frozenset({"tiktok.com"}),
    "instagram": frozenset({"instagram.com", "instagr.am"}),
    "google_drive": frozenset({"drive.google.com", "docs.google.com"}),
    "snapchat": frozenset({"snapchat.com"}),
    "twitter": frozenset({"twitter.com", "x.com"}),
    "pinterest": frozenset({"pinterest.com", "pin.it"}),
    "reddit": frozenset({"reddit.com", "redd.it"}),
}

BLOCKED_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".test",
    ".invalid",
    ".example",
)


@dataclass(frozen=True)
class URLValidationResult:
    """Immutable URL-validation result."""

    is_valid: bool
    url: str
    normalized_url: Optional[str] = None
    platform: Optional[str] = None
    hostname: Optional[str] = None
    resolved_ips: Tuple[str, ...] = ()
    error: Optional[str] = None


def _failure(url: str, error: str, **kwargs) -> URLValidationResult:
    """Create a consistent validation failure."""
    return URLValidationResult(
        is_valid=False,
        url=url,
        error=error,
        **kwargs,
    )


def is_ip_address_safe(ip_str: str) -> bool:
    """Accept only globally routable IP addresses."""
    if not isinstance(ip_str, str) or not ip_str:
        return False

    try:
        address = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            address = address.ipv4_mapped

    return (
        address.is_global
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


def _normalize_hostname(hostname: str) -> Optional[str]:
    """Validate and normalize a DNS hostname to lowercase ASCII."""
    if not isinstance(hostname, str) or not hostname:
        return None

    if "%" in hostname or "\\" in hostname:
        return None

    if any(ord(char) < 33 or ord(char) == 127 for char in hostname):
        return None

    # Allow one trailing DNS root dot, but reject multiple trailing dots.
    if hostname.endswith(".."):
        return None

    if hostname.endswith("."):
        hostname = hostname[:-1]

    if not hostname or ".." in hostname:
        return None

    try:
        hostname = hostname.encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError):
        return None

    if len(hostname) > 253:
        return None

    for label in hostname.split("."):
        if (
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or not all(
                char.isascii() and (char.isalnum() or char == "-")
                for char in label
            )
        ):
            return None

    return hostname


def _match_platform(hostname: str) -> Optional[str]:
    """Match exact platform domains and genuine subdomains."""
    for platform, domains in ALLOWED_PLATFORMS.items():
        for domain in domains:
            if hostname == domain or hostname.endswith("." + domain):
                return platform

    return None


def _resolve_public_ips(hostname: str, port: int) -> Tuple[str, ...]:
    """Resolve a hostname and reject the entire result if any IP is unsafe."""
    answers = socket.getaddrinfo(
        hostname,
        port,
        family=socket.AF_UNSPEC,
        type=socket.SOCK_STREAM,
    )

    addresses = set()

    for answer in answers:
        try:
            ip_string = answer[4][0]
            address = ipaddress.ip_address(ip_string)
        except (IndexError, TypeError, ValueError) as exc:
            raise OSError("Malformed DNS response") from exc

        if not is_ip_address_safe(str(address)):
            raise OSError("DNS returned a non-public IP address")

        addresses.add(str(address))

    if not addresses:
        raise OSError("DNS returned no addresses")

    return tuple(sorted(addresses))


def validate_url(
    url: object,
    check_dns: bool = True,
) -> URLValidationResult:
    """Validate an HTTP(S) URL for an explicitly allowed media platform.

    DNS validation is enabled by default. Set check_dns=False only when
    DNS and destination safety are independently enforced elsewhere.
    This function does not authorize or perform the download itself.
    """
    original = url if isinstance(url, str) else repr(url)

    if not isinstance(url, str):
        return _failure(original, "Input must be a string")

    if not url:
        return _failure(url, "URL cannot be empty")

    if len(url) > MAX_URL_LENGTH:
        return _failure(url[:100], "URL exceeds maximum length")

    # Reject malformed input rather than silently rewriting it.
    if url != url.strip():
        return _failure(url, "Leading or trailing whitespace is prohibited")

    if "\\" in url:
        return _failure(url, "Backslashes are prohibited")

    if any(
        char.isspace() or ord(char) < 32 or ord(char) == 127
        for char in url
    ):
        return _failure(url, "Whitespace or control characters are prohibited")

    try:
        parsed = urlsplit(url)

        scheme = parsed.scheme.lower()

        if scheme not in ALLOWED_SCHEMES:
            return _failure(url, "Only HTTP and HTTPS are allowed")

        if not parsed.netloc or not parsed.hostname:
            return _failure(url, "URL must contain a hostname")

        if parsed.username is not None or parsed.password is not None:
            return _failure(url, "Embedded credentials are prohibited")

        if "@" in parsed.netloc:
            return _failure(url, "Embedded credentials are prohibited")

        # Accessing parsed.port can raise ValueError for malformed ports.
        explicit_port = parsed.port
        expected_port = ALLOWED_PORTS[scheme]

        if explicit_port is not None and explicit_port != expected_port:
            return _failure(url, "Non-standard port is prohibited")

        hostname = _normalize_hostname(parsed.hostname)

        if hostname is None:
            return _failure(url, "Invalid hostname")

        if hostname == "localhost" or any(
            hostname.endswith(suffix) for suffix in BLOCKED_SUFFIXES
        ):
            return _failure(
                url,
                "Local or reserved hostname is prohibited",
                hostname=hostname,
            )

        # IP literals are never accepted as media-platform URLs.
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            pass
        else:
            return _failure(
                url,
                "IP address targets are prohibited",
                hostname=hostname,
            )

        platform = _match_platform(hostname)

        if platform is None:
            return _failure(
                url,
                "Hostname is not an allowed media platform",
                hostname=hostname,
            )

        resolved_ips: Tuple[str, ...] = ()

        if check_dns:
            try:
                resolved_ips = _resolve_public_ips(hostname, expected_port)
            except (OSError, socket.gaierror, socket.herror, socket.timeout):
                return _failure(
                    url,
                    "DNS validation failed or returned an unsafe address",
                    platform=platform,
                    hostname=hostname,
                )

        # Preserve path, query, and fragment. The default port is omitted.
        normalized_url = urlunsplit((
            scheme,
            hostname,
            parsed.path or "/",
            parsed.query,
            parsed.fragment,
        ))

        return URLValidationResult(
            is_valid=True,
            url=url,
            normalized_url=normalized_url,
            platform=platform,
            hostname=hostname,
            resolved_ips=resolved_ips,
        )

    except (ValueError, UnicodeError, OverflowError):
        return _failure(url, "Malformed URL")



def is_valid_url(url: object, resolve_dns: bool = True) -> bool:
    """Return whether a URL passes the existing strict validation."""
    if not isinstance(resolve_dns, bool):
        return False

    return validate_url(url, check_dns=resolve_dns).is_valid
