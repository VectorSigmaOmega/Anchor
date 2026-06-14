import asyncio
import json

from anchor.config import get_settings
from anchor.db.pool import Database
from anchor.db.repository import AnchorRepository
from anchor.ingest.fetch import DocumentFetcher
from anchor.ingest.service import IngestionService
from anchor.logging import configure_logging
from anchor.providers.gemini import GeminiEmbeddingProvider


async def run() -> None:
    settings = get_settings()
    settings.validate_ingest_runtime()
    configure_logging(settings.log_level)
    database = Database(settings)
    await database.open()
    try:
        repository = AnchorRepository(database, settings)
        fetcher = DocumentFetcher(settings)
        embedding_provider = GeminiEmbeddingProvider(settings)
        service = IngestionService(repository, fetcher, embedding_provider)
        summary = await service.run()
        print(json.dumps(summary, ensure_ascii=True))
    finally:
        await database.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
