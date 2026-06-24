"""Token bucket rate limiter for API calls."""

import time
import threading
from typing import Optional


class RateLimiter:
    """Thread-safe token bucket rate limiter."""

    def __init__(self, max_tokens: int, refill_period_sec: float):
        """
        Args:
            max_tokens: Maximum number of tokens (API calls) allowed.
            refill_period_sec: Time in seconds to fully refill the bucket.
        """
        self._max_tokens = max_tokens
        self._refill_rate = max_tokens / refill_period_sec  # tokens per second
        self._tokens = float(max_tokens)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 0) -> bool:
        """Try to acquire a token. Returns True if successful.

        Args:
            timeout: Max seconds to wait for a token. 0 = no wait.
        """
        deadline = time.monotonic() + timeout

        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True

            if time.monotonic() >= deadline:
                return False

            # Wait a short interval before retrying
            time.sleep(min(0.5, deadline - time.monotonic()))

    def _refill(self):
        """Refill tokens based on elapsed time. Must be called with lock held."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._max_tokens, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

    @property
    def available_tokens(self) -> int:
        with self._lock:
            self._refill()
            return int(self._tokens)

    @property
    def is_available(self) -> bool:
        return self.available_tokens >= 1


class PlatformRateLimiters:
    """Pre-configured rate limiters for each platform."""

    def __init__(self):
        # Threads: 2200 keyword searches / 24h
        self.threads_search = RateLimiter(max_tokens=2200, refill_period_sec=86400)
        # Threads: 250 posts / 24h (replies may not count, but be safe)
        self.threads_reply = RateLimiter(max_tokens=250, refill_period_sec=86400)

        # Facebook: 200 calls / hour / token
        self.facebook = RateLimiter(max_tokens=200, refill_period_sec=3600)

        # Instagram: 200 calls / hour, 30 hashtags / 7 days
        self.instagram_api = RateLimiter(max_tokens=200, refill_period_sec=3600)
        self.instagram_hashtag = RateLimiter(max_tokens=30, refill_period_sec=604800)
