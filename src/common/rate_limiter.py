import os
import time
import threading
from collections import deque
from fastapi import HTTPException, status

# Limits configurable via environment variables (RETAIL=5/min, BROKER=20/min by default)
_LIMITS: dict[str, int] = {
    "RETAIL": int(os.getenv("RATE_LIMIT_RETAIL", "5")),
    "BROKER": int(os.getenv("RATE_LIMIT_BROKER", "20")),
}
_WINDOW_SECONDS = 60
_DEFAULT_LIMIT = 5

# {actor_id: deque of request timestamps (monotonic seconds)}
_counters: dict[str, deque] = {}
_lock = threading.Lock()


def check_rate_limit(actor_id: str, role: str) -> None:
    """Enforce per-actor sliding-window rate limit.

    Keyed on actor_id (the JWT sub claim). The window is 60 seconds.
    Limits are read from env vars at module load:
      RATE_LIMIT_RETAIL  (default 5)
      RATE_LIMIT_BROKER  (default 20)

    Raises HTTP 429 with reason_code RATE_LIMIT_EXCEEDED when over limit.
    Returns None and records the request timestamp when within limit.

    Note: counter state is in-process memory only and resets on worker restart.
    This is acceptable for the demo; a production deployment would use Redis.
    """
    limit = _LIMITS.get(role, _DEFAULT_LIMIT)
    now = time.monotonic()
    cutoff = now - _WINDOW_SECONDS

    with _lock:
        if actor_id not in _counters:
            _counters[actor_id] = deque()
        window = _counters[actor_id]
        # Evict timestamps that have fallen outside the current window
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"reason_code": "RATE_LIMIT_EXCEEDED", "message": "Rate limit exceeded"},
            )
        window.append(now)
