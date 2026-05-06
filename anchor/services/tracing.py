from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from anchor.config import Settings

try:
    from langfuse import Langfuse
except Exception:  # pragma: no cover
    Langfuse = None  # type: ignore[assignment]


@dataclass
class NullSpan:
    _client: Any = None

    def end(self, output: Any | None = None) -> None:
        if self._client and hasattr(self._client, "end"):
            self._client.end(output=output)


class NullTrace:
    def __init__(self, client: Any = None) -> None:
        self.client = client

    def span(self, name: str, input: Any | None = None) -> NullSpan:
        if self.client and hasattr(self.client, "span"):
            return NullSpan(self.client.span(name=name, input=input))
        return NullSpan()

    def generation(self, name: str, model: str, input: Any | None = None) -> NullSpan:
        if self.client and hasattr(self.client, "generation"):
            return NullSpan(self.client.generation(name=name, model=model, input=input))
        return NullSpan()

    def end(self, output: Any | None = None) -> None:
        if self.client and hasattr(self.client, "update"):
            self.client.update(output=output)


class Tracer:
    def __init__(self, settings: Settings) -> None:
        self._client = None
        if Langfuse and settings.langfuse_public_key and settings.langfuse_secret_key:
            self._client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )

    def start_query_trace(self, *, request_id: str, question: str) -> NullTrace:
        if not self._client:
            return NullTrace()
        trace = self._client.trace(
            name="anchor.query",
            input={"question": question},
            metadata={"request_id": request_id},
        )
        return NullTrace(trace)
