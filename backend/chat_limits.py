"""Bounded, process-local admission control for the anonymous public demo."""

from __future__ import annotations

import math
import os
import time
from collections import deque
from dataclasses import dataclass
from ipaddress import ip_address
from threading import Lock
from typing import Callable

MAX_QUESTION_CHARS = 2_000
MAX_MESSAGE_CHARS = 12_000
MAX_HISTORY_MESSAGES = 21  # ten prior exchanges plus the new question
MAX_HISTORY_CHARS = 20_000
MAX_REQUEST_BYTES = 128 * 1024


def _positive_env(name: str, default: int) -> int:
    value = int(os.environ.get(name, default))
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True)
class ChatSettings:
    limit: int = 10
    window_seconds: int = 3_600
    max_concurrent: int = 2
    timeout_seconds: int = 120
    max_output_tokens: int = 1_200
    max_model_calls: int = 12
    max_tool_calls: int = 24
    on_render: bool = False

    @classmethod
    def from_env(cls) -> "ChatSettings":
        return cls(
            limit=_positive_env("ARM_CHAT_RATE_LIMIT", 10),
            window_seconds=_positive_env("ARM_CHAT_WINDOW_SECONDS", 3_600),
            max_concurrent=_positive_env("ARM_CHAT_MAX_CONCURRENT", 2),
            timeout_seconds=_positive_env("ARM_CHAT_TIMEOUT_SECONDS", 120),
            max_output_tokens=_positive_env("ARM_CHAT_MAX_OUTPUT_TOKENS", 1_200),
            max_model_calls=_positive_env("ARM_CHAT_MAX_MODEL_CALLS", 12),
            max_tool_calls=_positive_env("ARM_CHAT_MAX_TOOL_CALLS", 24),
            on_render=os.environ.get("RENDER", "").lower() == "true",
        )


def client_key(request, *, on_render: bool) -> str:
    """Trust edge-owned IP headers only inside Render's managed ingress.

    X-Forwarded-For can contain a caller-supplied prefix. Render's Cloudflare
    edge supplies True-Client-IP / CF-Connecting-IP instead. Missing or invalid
    edge identification fails closed; it must not create new quota buckets.
    Run Uvicorn with --no-proxy-headers so direct deployments use the socket IP.
    """
    if on_render:
        header = "true-client-ip" if request.headers.get("true-client-ip") else "cf-connecting-ip"
        values = request.headers.getlist(header)
        value = values[0] if len(values) == 1 else None
        if not value:
            raise ValueError("The hosting proxy did not supply a client address.")
    else:
        value = request.client.host if request.client else "unknown"
    try:
        address = ip_address(value)
    except ValueError:
        if on_render:
            raise ValueError("The hosting proxy supplied an invalid client address.") from None
        return value  # e.g. an ASGI test client's hostname; not a request header
    return str(getattr(address, "ipv4_mapped", None) or address)


@dataclass(frozen=True)
class Admission:
    reason: str
    limit: int
    remaining: int
    reset_after: int

    @property
    def headers(self) -> dict[str, str]:
        return {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset-After": str(self.reset_after),
            "Cache-Control": "no-store",
        }


class ChatAdmission:
    """Exact rolling window + concurrency reservation in one atomic operation.

    Admitted requests consume quota even if the upstream model subsequently
    fails. Invalid, rate-rejected and busy requests do not consume quota.
    Counts reset on process restart; use one worker and one service instance.
    """

    def __init__(
        self, settings: ChatSettings, *, clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ):
        self.settings = settings
        self.clock = clock
        self.max_keys = max_keys
        self._requests: dict[str, deque[float]] = {}
        self._active = 0
        self._lock = Lock()
        self._last_cleanup = clock()

    def _prune(self, key: str, now: float) -> deque[float]:
        entries = self._requests.get(key, deque())
        cutoff = now - self.settings.window_seconds
        while entries and entries[0] <= cutoff:
            entries.popleft()
        return entries

    def _result(self, entries: deque[float], now: float, reason: str = "") -> Admission:
        reset = max(0, math.ceil(entries[0] + self.settings.window_seconds - now)) if entries else 0
        return Admission(reason, self.settings.limit, max(0, self.settings.limit - len(entries)), reset)

    def usage(self, key: str) -> Admission:
        with self._lock:
            now = self.clock()
            entries = self._prune(key, now)
            if not entries:
                self._requests.pop(key, None)
            return self._result(entries, now)

    def admit(self, key: str) -> Admission:
        with self._lock:
            now = self.clock()
            if now - self._last_cleanup >= self.settings.window_seconds or len(self._requests) >= self.max_keys:
                for old_key in list(self._requests):
                    if not self._prune(old_key, now):
                        self._requests.pop(old_key, None)
                self._last_cleanup = now
            entries = self._prune(key, now)
            if len(entries) >= self.settings.limit:
                return self._result(entries, now, "rate")
            if self._active >= self.settings.max_concurrent:
                return self._result(entries, now, "busy")
            if key not in self._requests and len(self._requests) >= self.max_keys:
                return self._result(entries, now, "capacity")
            entries.append(now)
            self._requests[key] = entries
            self._active += 1
            return self._result(entries, now)

    def release(self) -> None:
        with self._lock:
            self._active -= 1


class ChatBodyLimit:
    """Reject oversized chat bodies before JSON parsing, including chunked bodies."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] != "/api/chat" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > MAX_REQUEST_BYTES:
                from starlette.responses import JSONResponse
                response = JSONResponse({"detail": "The chat request is too large."}, status_code=413)
                return await response(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
