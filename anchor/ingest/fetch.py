from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import httpx

from anchor.config import Settings
from anchor.schemas import DocumentRecord


def file_sha256(path: Path) -> str:
    hasher = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


class DocumentFetcher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.raw_corpus_dir.mkdir(parents=True, exist_ok=True)

    async def fetch(self, document: DocumentRecord) -> Path:
        target = self.settings.raw_corpus_dir / f"{document.doc_id}.{document.format}"
        if target.exists() and file_sha256(target) == document.sha256:
            return target

        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            response = await client.get(document.source_url, headers={"User-Agent": "anchor-ingest/0.1"})
            response.raise_for_status()
        temp_path = target.with_suffix(target.suffix + ".part")
        temp_path.write_bytes(response.content)
        digest = file_sha256(temp_path)
        if digest != document.sha256:
            temp_path.unlink(missing_ok=True)
            raise ValueError(f"hash mismatch for {document.doc_id}")
        temp_path.replace(target)
        return target

