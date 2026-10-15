from concurrent.futures import ThreadPoolExecutor

import pytest
from starlette.requests import Request

from backend.chat_limits import ChatAdmission, ChatSettings, client_key


def test_ten_requests_and_exact_rolling_expiry():
    clock = [0.0]
    gate = ChatAdmission(ChatSettings(max_concurrent=20), clock=lambda: clock[0])
    for t in range(10):
        clock[0] = float(t)
        assert gate.admit("alice").reason == ""
        gate.release()
    assert gate.admit("alice").reason == "rate"
    assert gate.usage("alice").remaining == 0
    assert gate.admit("bob").reason == ""
    gate.release()
    clock[0] = 3599.99
    assert gate.admit("alice").reason == "rate"
    clock[0] = 3600.0
    assert gate.admit("alice").reason == ""  # t=0 has expired; t=1..9 remain
    gate.release()
    assert gate.admit("alice").reason == "rate"
    clock[0] = 7200.0
    assert gate.usage("alice").remaining == 10


def test_simultaneous_requests_cannot_over_admit():
    gate = ChatAdmission(ChatSettings(max_concurrent=100))
    with ThreadPoolExecutor(max_workers=32) as executor:
        results = list(executor.map(lambda _: gate.admit("one-network"), range(50)))
    assert sum(not r.reason for r in results) == 10
    assert sum(r.reason == "rate" for r in results) == 40
    for result in results:
        if not result.reason:
            gate.release()


def test_busy_requests_do_not_consume_quota():
    gate = ChatAdmission(ChatSettings(max_concurrent=1))
    assert not gate.admit("alice").reason
    assert gate.admit("bob").reason == "busy"
    assert gate.usage("bob").remaining == 10
    gate.release()
    assert not gate.admit("bob").reason
    gate.release()


def test_key_capacity_fails_closed_and_expired_keys_are_reclaimed():
    clock = [0]
    gate = ChatAdmission(ChatSettings(), clock=lambda: clock[0], max_keys=1)
    assert not gate.admit("alice").reason
    gate.release()
    assert gate.admit("bob").reason == "capacity"
    clock[0] = 3600
    assert not gate.admit("bob").reason
    gate.release()


def request(headers=(), host="198.51.100.5"):
    return Request({"type": "http", "headers": headers, "client": (host, 1234)})


def test_direct_server_ignores_spoofed_forwarding_headers():
    req = request([(b"x-forwarded-for", b"203.0.113.7"), (b"true-client-ip", b"203.0.113.8")])
    assert client_key(req, on_render=False) == "198.51.100.5"


def test_render_uses_edge_address_not_untrusted_xff_prefix():
    req = request([(b"x-forwarded-for", b"203.0.113.7, 10.0.0.2"), (b"true-client-ip", b"198.51.100.9")])
    assert client_key(req, on_render=True) == "198.51.100.9"
    assert client_key(request([(b"cf-connecting-ip", b"::ffff:198.51.100.9")]), on_render=True) == "198.51.100.9"


@pytest.mark.parametrize("headers", [
    [], [(b"x-forwarded-for", b"203.0.113.7")],
    [(b"true-client-ip", b"garbage")], [(b"true-client-ip", b"198.51.100.1, 198.51.100.2")],
    [(b"true-client-ip", b"198.51.100.1"), (b"true-client-ip", b"198.51.100.2")],
])
def test_render_fails_closed_without_valid_edge_identification(headers):
    with pytest.raises(ValueError):
        client_key(request(headers), on_render=True)


def test_invalid_setting_fails_at_startup(monkeypatch):
    monkeypatch.setenv("ARM_CHAT_RATE_LIMIT", "0")
    with pytest.raises(ValueError, match="ARM_CHAT_RATE_LIMIT"):
        ChatSettings.from_env()
