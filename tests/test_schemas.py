import pytest
from pydantic import ValidationError

from anchor.schemas import ConversationTurn, QueryRequest


def test_query_request_accepts_bounded_conversation_history() -> None:
    request = QueryRequest(
        question="  What about NBFCs?  ",
        history=[
            ConversationTurn(role="user", content="  What does the RBI KYC direction require?  "),
            ConversationTurn(role="assistant", content="It requires customer due diligence."),
        ],
    )

    assert request.question == "What about NBFCs?"
    assert request.history[0].content == "What does the RBI KYC direction require?"


def test_query_request_rejects_unbounded_conversation_history() -> None:
    with pytest.raises(ValidationError):
        QueryRequest(
            question="What about NBFCs?",
            history=[
                ConversationTurn(role="user", content=f"Question {index}")
                for index in range(7)
            ],
        )


def test_query_request_rejects_blank_question_after_trim() -> None:
    with pytest.raises(ValidationError):
        QueryRequest(question="   ")


def test_conversation_turn_rejects_blank_content_after_trim() -> None:
    with pytest.raises(ValidationError):
        ConversationTurn(role="user", content="   ")
