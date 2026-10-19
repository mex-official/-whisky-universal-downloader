"""Defense-in-depth filter for non-public socket destinations.

This is not a complete SSRF, redirect, or DNS-rebinding solution.
"""
from __future__ import annotations

import ipaddress
import socket
import threading

_ORIGINAL_GETADDRINFO = socket.getaddrinfo
_INSTALL_LOCK = threading.Lock()
_INSTALLED = False


def _is_public_address(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False

    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False

    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped

    return address.is_global


def _validate_results(results):
    if not results:
        raise socket.gaierror("DNS returned no addresses")

    for item in results:
        try:
            address = item[4][0]
        except (IndexError, TypeError, KeyError):
            raise socket.gaierror(
                "Malformed address resolution result"
            ) from None

        if not _is_public_address(address):
            raise socket.gaierror(
                "Blocked non-public network destination"
            )

    return results


def _guarded_getaddrinfo(
    host, port, family=0, type=0, proto=0, flags=0
):
    results = _ORIGINAL_GETADDRINFO(
        host, port, family, type, proto, flags
    )

    # Preserve the standard behavior for passive/bind lookups.
    if host is None:
        return results

    return _validate_results(results)


def install_public_network_guard():
    """Install the process-wide DNS result filter once."""
    global _INSTALLED

    with _INSTALL_LOCK:
        if not _INSTALLED:
            socket.getaddrinfo = _guarded_getaddrinfo
            _INSTALLED = True
