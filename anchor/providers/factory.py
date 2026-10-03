from anchor.config import Settings
from anchor.providers.gemini import EmbeddingProvider, GeminiEmbeddingProvider, GeminiGenerationProvider, GenerationProvider
from anchor.providers.openai import OpenAIEmbeddingProvider, OpenAIGenerationProvider


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "openai":
        return OpenAIEmbeddingProvider(settings)
    return GeminiEmbeddingProvider(settings)


def build_generation_provider(settings: Settings) -> GenerationProvider:
    if settings.generation_provider == "openai":
        return OpenAIGenerationProvider(settings)
    return GeminiGenerationProvider(settings)
