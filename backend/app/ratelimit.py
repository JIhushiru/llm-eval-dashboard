"""In-memory per-client rate limiter (pure ASGI middleware).

A sliding 60s window keyed by bearer token (if present) else client IP. Written
as raw ASGI rather than BaseHTTPMiddleware so it never interferes with the
runner's FastAPI BackgroundTasks. State is per-process and in-memory — right for
a single-instance local tool; a multi-instance deployment would want Redis.
"""

import time
from collections import defaultdict, deque

from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings

_WINDOW_SECONDS = 60.0
_EXEMPT_PATHS = frozenset({"/api/health"})

# Process-wide window store, module-level so tests can reset it deterministically.
_HITS: dict[str, deque[float]] = defaultdict(deque)


def reset_rate_limit_state() -> None:
    """Clear all recorded request windows (test helper)."""
    _HITS.clear()


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = get_settings().evalforge_rate_limit_per_minute
        if (
            limit <= 0
            or scope["method"] == "OPTIONS"
            or scope["path"] in _EXEMPT_PATHS
        ):
            await self.app(scope, receive, send)
            return

        key = self._client_key(scope)
        now = time.monotonic()
        window = _HITS[key]
        cutoff = now - _WINDOW_SECONDS
        while window and window[0] <= cutoff:
            window.popleft()

        if len(window) >= limit:
            retry_after = max(1, int(_WINDOW_SECONDS - (now - window[0])))
            await self._reject(send, retry_after)
            return

        window.append(now)
        await self.app(scope, receive, send)

    @staticmethod
    def _client_key(scope: Scope) -> str:
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                decoded = value.decode("latin-1")
                if decoded.lower().startswith("bearer "):
                    return "token:" + decoded[7:].strip()
        client = scope.get("client")
        return "ip:" + (client[0] if client else "unknown")

    @staticmethod
    async def _reject(send: Send, retry_after: int) -> None:
        body = b'{"detail":"rate limit exceeded; slow down"}'
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"retry-after", str(retry_after).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
