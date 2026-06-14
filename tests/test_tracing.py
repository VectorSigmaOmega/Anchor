from anchor.config import Settings
from anchor.services import tracing
from anchor.services.tracing import Tracer


class LangfuseWithoutTrace:
    def __init__(self, **kwargs: str) -> None:
        self.kwargs = kwargs


class BrokenTrace:
    def span(self, name: str, input: object | None = None) -> object:
        raise RuntimeError("span failed")

    def generation(self, name: str, model: str, input: object | None = None) -> object:
        raise RuntimeError("generation failed")

    def update(self, output: object | None = None) -> None:
        raise RuntimeError("update failed")


class LangfuseWithBrokenTrace:
    def __init__(self, **kwargs: str) -> None:
        self.kwargs = kwargs

    def trace(self, **kwargs: object) -> BrokenTrace:
        return BrokenTrace()


def langfuse_settings() -> Settings:
    return Settings.model_validate(
        {
            "database_url": "postgresql://anchor:anchor@localhost:5432/anchor",
            "gemini_api_key": "key",
            "cohere_api_key": "key",
            "langfuse_public_key": "public",
            "langfuse_secret_key": "secret",
        }
    )


def test_tracer_is_noop_when_langfuse_client_has_no_trace(monkeypatch) -> None:
    monkeypatch.setattr(tracing, "Langfuse", LangfuseWithoutTrace)

    trace = Tracer(langfuse_settings()).start_query_trace(
        request_id="request-1",
        question="What are the KYC requirements?",
    )

    trace.span("request_validation").end(output={"valid": True})
    trace.generation("generation", model="gemini").end(output={"status": "answered"})
    trace.end(output={"status": "answered"})


def test_tracer_suppresses_langfuse_runtime_errors(monkeypatch) -> None:
    monkeypatch.setattr(tracing, "Langfuse", LangfuseWithBrokenTrace)

    trace = Tracer(langfuse_settings()).start_query_trace(
        request_id="request-1",
        question="What are the KYC requirements?",
    )

    trace.span("request_validation").end(output={"valid": True})
    trace.generation("generation", model="gemini").end(output={"status": "answered"})
    trace.end(output={"status": "answered"})
