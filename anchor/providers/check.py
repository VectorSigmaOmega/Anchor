"""Check paid provider access without reading or changing the corpus.

Run `python -m anchor.providers.check` with the API environment loaded.
"""

import asyncio
import json

from anchor.config import get_settings
from anchor.providers.factory import build_embedding_provider, build_generation_provider
from anchor.providers.gemini import ProviderError
from anchor.providers.rerank import CohereRerankProvider
from anchor.schemas import RetrievedChunk


async def check_providers() -> bool:
    settings = get_settings()
    settings.validate_query_runtime()
    settings._require("COHERE_API_KEY", settings.cohere_api_key)
    chunk = RetrievedChunk(
        chunk_id="provider-check",
        doc_id="provider-check",
        doc_title="Provider connectivity check",
        regulator="RBI",
        section_path="Connectivity",
        text="This connectivity check confirms that the query service is available.",
        source_url="https://example.invalid/provider-check",
    )

    async def probe(name, operation):
        try:
            async with asyncio.timeout(settings.query_timeout_seconds):
                result = await operation
            metadata = {"name": name, "status": "ok"}
            if name == "embedding":
                metadata["dimension"] = len(result)
            elif name == "generation":
                metadata["model_status"] = result.status
            print(json.dumps(metadata), flush=True)
            return True
        except ProviderError as exc:
            print(json.dumps({"name": name, "status": "unavailable", "http_status": exc.status_code}), flush=True)
        except TimeoutError:
            print(json.dumps({"name": name, "status": "timeout"}), flush=True)
        except Exception as exc:
            print(json.dumps({"name": name, "status": "invalid_response", "error_type": type(exc).__name__}), flush=True)
        return False

    results = await asyncio.gather(
        probe("embedding", build_embedding_provider(settings).embed_query("Provider connectivity check")),
        probe(
            "generation",
            build_generation_provider(settings).generate(question="What does this connectivity check confirm?", context_chunks=[chunk]),
        ),
        probe("rerank", CohereRerankProvider(settings).rerank("query service availability", [chunk], top_n=1)),
    )
    return all(results)


def main() -> None:
    raise SystemExit(0 if asyncio.run(check_providers()) else 1)


if __name__ == "__main__":
    main()
