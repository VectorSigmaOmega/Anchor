from anchor.config import Settings
from anchor.ingest.manifest import load_manifest


def test_manifest_loads_and_meets_scope_contract() -> None:
    settings = Settings.model_validate(
        {
            "database_url": "postgresql://anchor:anchor@localhost:5432/anchor",
            "gemini_api_key": "key",
            "cohere_api_key": "key",
        }
    )
    manifest = load_manifest(settings)

    active = [doc for doc in manifest.documents if doc.active]
    assert len(active) == 16
    assert sum(1 for doc in active if doc.regulator == "SEBI") == 8
    assert sum(1 for doc in active if doc.regulator == "RBI") == 8
