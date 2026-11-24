"""Small in-memory sliding-window rate limiter (single-instance prototype).

For multi-instance production, back this with Redis.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status

_hits: dict[str, deque[float]] = defaultdict(deque)


def reset() -> None:
    _hits.clear()


def rate_limit(limit: int, window_seconds: int) -> Callable[[Request], None]:
    def dependency(request: Request) -> None:
        if request.method == "GET":
            return
        ip = request.client.host if request.client else "unknown"
        key = f"{request.url.path}:{ip}"
        now = time.monotonic()
        q = _hits[key]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests. Try again shortly."
            )
        q.append(now)

    return dependency
