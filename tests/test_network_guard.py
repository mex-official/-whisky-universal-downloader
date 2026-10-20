import socket

import pytest

import network_guard as guard


def dns_result(address):
    return (
        socket.AF_INET,
        socket.SOCK_STREAM,
        socket.IPPROTO_TCP,
        "",
        (address, 443),
    )


def test_public_address_is_allowed():
    result = [dns_result("8.8.8.8")]
    assert guard._validate_results(result) == result


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "::1",
        "fc00::1",
        "::ffff:127.0.0.1",
    ],
)
def test_non_public_addresses_are_blocked(address):
    with pytest.raises(socket.gaierror):
        guard._validate_results([dns_result(address)])


def test_mixed_public_and_private_results_fail_closed():
    with pytest.raises(socket.gaierror):
        guard._validate_results(
            [dns_result("8.8.8.8"), dns_result("127.0.0.1")]
        )


def test_empty_dns_results_are_rejected():
    with pytest.raises(socket.gaierror):
        guard._validate_results([])


def test_malformed_dns_result_is_rejected():
    with pytest.raises(socket.gaierror):
        guard._validate_results([("malformed",)])


def test_guarded_lookup_checks_resolved_addresses(monkeypatch):
    monkeypatch.setattr(
        guard,
        "_ORIGINAL_GETADDRINFO",
        lambda *args: [dns_result("127.0.0.1")],
    )

    with pytest.raises(socket.gaierror):
        guard._guarded_getaddrinfo("example.com", 443)
