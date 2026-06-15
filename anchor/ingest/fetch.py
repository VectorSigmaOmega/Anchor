from __future__ import annotations

import asyncio
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

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

        temp_path = target.with_suffix(target.suffix + ".part")
        last_error: Exception | None = None
        async with httpx.AsyncClient(follow_redirects=True, timeout=120.0) as client:
            for attempt in range(1, 5):
                temp_path.unlink(missing_ok=True)
                try:
                    content_type = None
                    final_url = document.source_url
                    async with client.stream(
                        "GET",
                        document.source_url,
                        headers={"User-Agent": "anchor-ingest/0.1"},
                    ) as response:
                        response.raise_for_status()
                        content_type = response.headers.get("content-type")
                        final_url = str(response.url)
                        with temp_path.open("wb") as handle:
                            async for chunk in response.aiter_bytes():
                                handle.write(chunk)
                    digest = file_sha256(temp_path)
                    if digest == document.sha256:
                        temp_path.replace(target)
                        return target
                    byte_count = temp_path.stat().st_size
                    last_error = ValueError(
                        "hash mismatch for "
                        f"{document.doc_id}: expected={document.sha256} "
                        f"actual={digest} bytes={byte_count} "
                        f"content_type={content_type or 'unknown'} "
                        f"final_url={_safe_url(final_url)}"
                    )
                except Exception as exc:
                    last_error = exc
                temp_path.unlink(missing_ok=True)
                if attempt < 4:
                    await asyncio.sleep(2 * attempt)
        if last_error:
            raise last_error
        raise ValueError(f"failed to fetch {document.doc_id}")


def _safe_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.query and not parsed.fragment:
        return url
    return parsed._replace(query="", fragment="").geturl()
