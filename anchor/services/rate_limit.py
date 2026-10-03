from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import UTC, datetime
from math import ceil

from anchor.config import Settings
from anchor.db.repository import AnchorRepository


class RateLimitExceeded(Exception):
    def __init__(self, message: str, *, retry_after_seconds: int = 60) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class RateLimiter:
    def __init__(self, repository: AnchorRepository, settings: Settings) -> None:
        self.repository = repository
        self.settings = settings
        self._rpm_windows: dict[str, deque[datetime]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._last_cleanup = datetime.now(UTC)

    async def check(self, ip_address: str) -> None:
        await self._check_per_minute(ip_address)
        ip_hash = await self.repository.hash_ip(ip_address)
        request_count = await self.repository.increment_daily_usage(ip_hash)
        if request_count > self.settings.rate_limit_rpd:
            now = datetime.now(UTC)
            next_day_seconds = 86400 - (now.hour * 3600 + now.minute * 60 + now.second)
            raise RateLimitExceeded("daily limit exceeded", retry_after_seconds=next_day_seconds)

    async def _check_per_minute(self, ip_address: str) -> None:
        now = datetime.now(UTC)
        async with self._lock:
            if (now - self._last_cleanup).total_seconds() >= 60:
                for ip, existing_window in list(self._rpm_windows.items()):
                    while existing_window and (now - existing_window[0]).total_seconds() >= 60:
                        existing_window.popleft()
                    if not existing_window:
                        del self._rpm_windows[ip]
                self._last_cleanup = now
            window = self._rpm_windows[ip_address]
            while window and (now - window[0]).total_seconds() >= 60:
                window.popleft()
            if len(window) >= self.settings.rate_limit_rpm:
                retry_after = max(1, ceil(60 - (now - window[0]).total_seconds()))
                raise RateLimitExceeded("rate limit exceeded", retry_after_seconds=retry_after)
            window.append(now)
