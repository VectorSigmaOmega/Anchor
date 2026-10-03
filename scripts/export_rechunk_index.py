"""Export evaluated chunks and cached Gemini vectors for atomic deployment."""

import json
from hashlib import sha256

from anchor.config import Settings
from anchor.ingest.chunk import CHUNKING_VERSION
from anchor.ingest.manifest import active_documents, load_manifest
from anchor.schemas import ChunkRecord
from scripts.prepare_chunking_experiment import ROOT


def main():
    settings = Settings()
    if settings.embedding_provider != "gemini":
        raise ValueError("The experimental cache contains Gemini embeddings")
    cache = {r["key"]: r["vector"] for r in map(json.loads, (ROOT / "embedding-cache.jsonl").read_text().splitlines())}
    chunks = [ChunkRecord.model_validate_json(line) for line in (ROOT / "structured.chunks.jsonl").read_text().splitlines()]
    header = {
        "chunking_version": CHUNKING_VERSION, "provider": settings.embedding_provider, "model": settings.embedding_model,
        "dimension": settings.embedding_dimension, "documents": {d.doc_id: d.sha256 for d in active_documents(load_manifest(settings))},
    }
    path = ROOT / "prepared-index.jsonl"
    with path.open("w") as output:
        output.write(json.dumps(header) + "\n")
        for chunk in chunks:
            text = settings.embedding_model + ":" + str(settings.embedding_dimension) + ":" + chunk.retrieval_text()
            key = sha256(text.encode()).hexdigest()
            output.write(json.dumps({"chunk": chunk.model_dump(), "vector": cache[key]}) + "\n")
    print(json.dumps({"chunks": len(chunks), "bytes": path.stat().st_size, "sha256": sha256(path.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
