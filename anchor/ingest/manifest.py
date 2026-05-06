from collections import Counter
from urllib.parse import urlparse

import yaml

from anchor.config import Settings
from anchor.schemas import DocumentRecord, Manifest

ALLOWED_DOMAINS = {"www.sebi.gov.in", "www.rbi.org.in", "sebi.gov.in", "rbi.org.in"}


def load_manifest(settings: Settings) -> Manifest:
    data = yaml.safe_load(settings.corpus_manifest_path.read_text())
    manifest = Manifest.model_validate(data)
    active_docs = [doc for doc in manifest.documents if doc.active]
    if len(active_docs) < 16:
        raise ValueError("manifest must contain at least 16 active documents")
    counts = Counter(doc.regulator for doc in active_docs)
    if counts["RBI"] < 8 or counts["SEBI"] < 8:
        raise ValueError("manifest must contain at least 8 active RBI docs and 8 active SEBI docs")
    for document in manifest.documents:
        parsed = urlparse(document.source_url)
        if parsed.hostname not in ALLOWED_DOMAINS:
            raise ValueError(f"non-official domain in manifest: {document.source_url}")
        if document.regulator == "RBI" and document.doc_type != "master_direction":
            raise ValueError(f"{document.doc_id} must be an RBI master direction")
        if document.regulator == "SEBI" and document.doc_type != "master_circular":
            raise ValueError(f"{document.doc_id} must be a SEBI master circular")
        if document.snapshot_date != manifest.snapshot_date:
            raise ValueError(f"{document.doc_id} snapshot_date does not match manifest snapshot_date")
    return manifest


def active_documents(manifest: Manifest) -> list[DocumentRecord]:
    return [document for document in manifest.documents if document.active]

