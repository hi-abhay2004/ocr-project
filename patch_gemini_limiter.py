import re

with open("ai/providers/gemini.py", "r") as f:
    code = f.read()

limiter_code = """import threading
from collections import deque

class _SlidingWindowRateLimiter:
    def __init__(self, max_per_minute: int, *, window_seconds: float = 60.0):
        self._max = max_per_minute
        self._window_seconds = window_seconds
        self._call_times = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        import time
        while True:
            with self._lock:
                now = time.monotonic()
                while self._call_times and now - self._call_times[0] >= self._window_seconds:
                    self._call_times.popleft()
                if len(self._call_times) < self._max:
                    self._call_times.append(now)
                    return
                wait_seconds = self._window_seconds - (now - self._call_times[0])
            time.sleep(max(wait_seconds, 0.05))

GEMINI_RATE_LIMITER = _SlidingWindowRateLimiter(14)
"""

if "_SlidingWindowRateLimiter" not in code:
    code = code.replace("DEFAULT_LLM_MODEL =", limiter_code + "\nDEFAULT_LLM_MODEL =")

code = code.replace("client = _client()", "GEMINI_RATE_LIMITER.acquire()\n        client = _client()")

with open("ai/providers/gemini.py", "w") as f:
    f.write(code)
