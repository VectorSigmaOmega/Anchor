from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest

from anchor.schemas import QueryResponse


class Metrics:
    def __init__(self, namespace: str) -> None:
        self.registry = CollectorRegistry()
        self.requests_total = Counter(
            f"{namespace}_requests_total",
            "Total query requests",
            labelnames=("status",),
            registry=self.registry,
        )
        self.refusals_total = Counter(
            f"{namespace}_refusals_total",
            "Refusal responses by reason",
            labelnames=("reason",),
            registry=self.registry,
        )
        self.citation_validation_failures = Counter(
            f"{namespace}_citation_validation_failures_total",
            "Citation validation failures",
            registry=self.registry,
        )
        self.query_latency = Histogram(
            f"{namespace}_query_latency_seconds",
            "Query latency in seconds",
            buckets=(0.25, 0.5, 1, 2, 3.5, 5, 8, 13),
            registry=self.registry,
        )

    def record_response(self, response: QueryResponse) -> None:
        self.requests_total.labels(status=response.status).inc()
        if response.status == "refused" and response.refusal_reason:
            self.refusals_total.labels(reason=response.refusal_reason).inc()

    def render(self) -> tuple[bytes, str]:
        return generate_latest(self.registry), CONTENT_TYPE_LATEST
