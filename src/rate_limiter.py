"""Rate limiter for API calls."""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class RateLimiter:
    """Simple rate limiter to ensure minimum time between API calls."""
    
    min_interval: float  # Minimum seconds between calls
    _last_call: float = field(default=0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    
    async def acquire(self) -> None:
        """Wait until we can make another API call."""
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_call
            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed
                await asyncio.sleep(wait_time)
            self._last_call = time.time()


class RateLimiterManager:
    """Manages multiple rate limiters for different APIs."""
    
    def __init__(self):
        self._limiters: Dict[str, RateLimiter] = {}
    
    def register(self, name: str, min_interval: float) -> None:
        """Register a rate limiter for a specific API."""
        self._limiters[name] = RateLimiter(min_interval=min_interval)
    
    async def acquire(self, name: str) -> None:
        """Acquire rate limit for a specific API."""
        if name in self._limiters:
            await self._limiters[name].acquire()
    
    def get(self, name: str) -> RateLimiter:
        """Get a specific rate limiter."""
        return self._limiters.get(name)

