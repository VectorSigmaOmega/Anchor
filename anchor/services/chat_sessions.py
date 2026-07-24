from __future__ import annotations

import re
import secrets
from hashlib import sha256

from fastapi import Request

from anchor.config import Settings

SESSION_TOKEN_BYTES = 32
SESSION_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,256}$")


def create_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def is_valid_session_token(token: str | None) -> bool:
    return bool(token and SESSION_TOKEN_RE.fullmatch(token))


def hash_session_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def should_secure_session_cookie(request: Request, settings: Settings) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", maxsplit=1)[0]
    return settings.environment == "production" or forwarded_proto.strip().lower() == "https"


def chat_title_from_question(question: str) -> str:
    compact = " ".join(question.split())
    return f"{compact[:43].strip()}..." if len(compact) > 46 else compact
