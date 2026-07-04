"""Tests for the WebUI/WS trusted-client (loopback + Tailscale) IP boundary."""

from __future__ import annotations

from types import SimpleNamespace

from nanobot.webui.http_utils import (
    is_localhost,
    is_trusted_webui_client,
    remote_ip_address,
)


def _conn(remote_address):
    return SimpleNamespace(remote_address=remote_address)


def test_loopback_v4_is_trusted():
    conn = _conn(("127.0.0.1", 5000))
    assert is_localhost(conn) is True
    assert is_trusted_webui_client(conn) is True


def test_loopback_v6_is_trusted():
    conn = _conn(("::1", 5000))
    assert is_localhost(conn) is True
    assert is_trusted_webui_client(conn) is True


def test_ipv6_mapped_loopback_is_trusted():
    conn = _conn(("::ffff:127.0.0.1", 5000))
    assert is_trusted_webui_client(conn) is True


def test_ipv6_zone_id_is_stripped():
    conn = _conn(("fe80::1%lo0", 5000))
    assert remote_ip_address(conn) is not None


def test_tailscale_v4_cgnat_is_trusted():
    conn = _conn(("100.64.1.2", 5000))
    assert is_localhost(conn) is False
    assert is_trusted_webui_client(conn) is True


def test_tailscale_v6_is_trusted():
    conn = _conn(("fd7a:115c:a1e0::1", 5000))
    assert is_trusted_webui_client(conn) is True


def test_public_ip_is_not_trusted():
    conn = _conn(("203.0.113.8", 5000))
    assert is_localhost(conn) is False
    assert is_trusted_webui_client(conn) is False


def test_missing_remote_address_is_not_trusted():
    conn = _conn(None)
    assert is_trusted_webui_client(conn) is False


def test_invalid_host_is_not_trusted():
    conn = _conn(("not-an-ip", 5000))
    assert remote_ip_address(conn) is None
    assert is_trusted_webui_client(conn) is False
