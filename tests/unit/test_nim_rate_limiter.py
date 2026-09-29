"""
Pure-logic test for ai.providers.nim._SlidingWindowRateLimiter — no network,
no NIM_API_KEY needed. A short `window_seconds` keeps this fast without
mocking time.
"""

import time
from concurrent.futures import ThreadPoolExecutor

from ai.providers.nim import _SlidingWindowRateLimiter


def test_calls_within_the_budget_do_not_block():
    limiter = _SlidingWindowRateLimiter(max_per_minute=5, window_seconds=1.0)
    start = time.monotonic()
    for _ in range(5):
        limiter.acquire()
    assert time.monotonic() - start < 0.5


def test_a_call_over_budget_waits_for_the_window_to_clear():
    limiter = _SlidingWindowRateLimiter(max_per_minute=2, window_seconds=0.3)
    start = time.monotonic()
    limiter.acquire()
    limiter.acquire()
    limiter.acquire()  # third call in the same window must wait
    elapsed = time.monotonic() - start
    assert elapsed >= 0.3


def test_concurrent_callers_never_exceed_the_budget_in_any_window():
    limiter = _SlidingWindowRateLimiter(max_per_minute=3, window_seconds=0.3)
    call_times = []
    lock_free_append = call_times.append  # list.append is already thread-safe

    def call():
        limiter.acquire()
        lock_free_append(time.monotonic())

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: call(), range(8)))

    call_times.sort()
    for t in call_times:
        in_window = sum(1 for other in call_times if 0 <= t - other < 0.3)
        assert in_window <= 3
