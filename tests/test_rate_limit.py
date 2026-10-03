import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from anchor.config import Settings
from anchor.services import rate_limit
from anchor.services.rate_limit import RateLimiter, RateLimitExceeded


class UsageRepository:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def hash_ip(self, ip: str) -> str:
        return ip

    async def increment_daily_usage(self, ip_hash: str) -> int:
        self.counts[ip_hash] = self.counts.get(ip_hash, 0) + 1
        return self.counts[ip_hash]


async def test_minute_limit_is_per_ip_and_covers_concurrent_requests() -> None:
    repository = UsageRepository()
    limiter = RateLimiter(repository, Settings(database_url="postgresql://unused", rate_limit_rpm=3))

    results = await asyncio.gather(*(limiter.check("192.0.2.1") for _ in range(8)), return_exceptions=True)

    assert sum(result is None for result in results) == 3
    assert sum(isinstance(result, RateLimitExceeded) for result in results) == 5
    assert repository.counts["192.0.2.1"] == 3
    await limiter.check("192.0.2.2")
    assert repository.counts["192.0.2.2"] == 1


async def test_daily_limit_survives_a_limiter_restart() -> None:
    repository = UsageRepository()
    settings = Settings(database_url="postgresql://unused", rate_limit_rpd=2)
    await RateLimiter(repository, settings).check("192.0.2.1")
    await RateLimiter(repository, settings).check("192.0.2.1")

    with pytest.raises(RateLimitExceeded, match="daily") as caught:
        await RateLimiter(repository, settings).check("192.0.2.1")

    assert 1 <= caught.value.retry_after_seconds <= 86400


async def test_expired_minute_windows_are_reclaimed(monkeypatch: pytest.MonkeyPatch) -> None:
    class Clock:
        current = datetime(2026, 10, 3, tzinfo=UTC)

        @classmethod
        def now(cls, tz):
            return cls.current

    monkeypatch.setattr(rate_limit, "datetime", Clock)
    limiter = RateLimiter(UsageRepository(), Settings(database_url="postgresql://unused", rate_limit_rpm=1))
    await limiter.check("192.0.2.1")
    with pytest.raises(RateLimitExceeded):
        await limiter.check("192.0.2.1")

    Clock.current += timedelta(seconds=60)
    await limiter.check("192.0.2.2")

    assert "192.0.2.1" not in limiter._rpm_windows
    await limiter.check("192.0.2.1")
