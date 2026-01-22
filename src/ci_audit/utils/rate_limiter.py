"""Rate limiting utilities using token bucket algorithm."""

import time
import threading
from typing import Optional


class RateLimiter:
    """Token bucket rate limiter for API requests.

    This implements a token bucket algorithm that allows bursts of requests
    while maintaining a maximum average rate.
    """

    def __init__(self, requests_per_second: float = 10.0, burst: Optional[int] = None):
        """Initialize rate limiter.

        Args:
            requests_per_second: Maximum average requests per second
            burst: Maximum burst size (tokens in bucket). Defaults to 2x rate.
        """
        self.rate = requests_per_second
        self.bucket_size = burst if burst is not None else int(requests_per_second * 2)
        self.tokens = float(self.bucket_size)
        self.lock = threading.Lock()
        self.last_update = time.time()

    def acquire(self, tokens: int = 1, blocking: bool = True) -> bool:
        """Acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire (default 1)
            blocking: Whether to block until tokens are available

        Returns:
            True if tokens were acquired, False if non-blocking and not available
        """
        with self.lock:
            # Refill bucket based on time elapsed
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.bucket_size, self.tokens + elapsed * self.rate)
            self.last_update = now

            # Check if we have enough tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            if not blocking:
                return False

            # Calculate wait time
            sleep_time = (tokens - self.tokens) / self.rate

        # Release lock while sleeping
        time.sleep(sleep_time)

        # Acquire again after sleeping
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.bucket_size, self.tokens + elapsed * self.rate)
            self.last_update = now
            self.tokens -= tokens

        return True

    def __enter__(self):
        """Context manager entry."""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass
