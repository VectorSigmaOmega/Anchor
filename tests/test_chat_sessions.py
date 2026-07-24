from anchor.config import Settings
from anchor.services.chat_sessions import (
    chat_title_from_question,
    create_session_token,
    hash_session_token,
    is_valid_session_token,
)


def test_session_token_is_valid_and_hashed() -> None:
    token = create_session_token()

    assert is_valid_session_token(token)
    assert hash_session_token(token) != token
    assert len(hash_session_token(token)) == 64


def test_invalid_session_token_is_rejected() -> None:
    assert not is_valid_session_token(None)
    assert not is_valid_session_token("")
    assert not is_valid_session_token("not valid because it has spaces")


def test_chat_title_from_question_matches_ui_truncation() -> None:
    title = chat_title_from_question("  What customer due diligence steps apply to individual customers?  ")

    assert title == "What customer due diligence steps apply to..."


def test_chat_cookie_settings_have_safe_defaults() -> None:
    settings = Settings.model_validate(
        {
            "database_url": "postgresql://anchor:anchor@localhost:5432/anchor",
        }
    )

    assert settings.session_cookie_name == "anchor_session"
    assert settings.session_cookie_max_age_days == 400
