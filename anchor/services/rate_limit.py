from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import UTC, datetime

from anchor.config import Settings
from anchor.db.repository import AnchorRepository


class RateLimitExceeded(Exception):
    pass


class RateLimiter:
    def __init__(self, repository: AnchorRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings
        self._rpm_windows: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, ip_address: str) -> None:
        await self._check_per_minute(ip_address)
        ip_hash = await self.repository.hash_ip(ip_address)
        request_count = await self.repository.increment_daily_usage(ip_hash)
        if request_count > self.settings.rate_limit_rpd:
            raise RateLimitExceeded("daily limit exceeded")

    async def _check_per_minute(self, ip_address: str) -> None:
        now = datetime.now(UTC)
        async with self._lock:
            window = self._rpm_windows[ip_address]
            while window and (now - window[0]).total_seconds() >= 60:
                window.popleft()
            if len(window) >= self.settings.rate_limit_rpm:
                raise RateLimitExceeded("rate limit exceeded")
            window.append(now)
