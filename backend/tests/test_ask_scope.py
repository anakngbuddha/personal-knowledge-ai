"""Ask defaults to workspace scope while keeping legacy chat history usable."""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.routes import ask as ask_routes
from app.generation.schemas import AskIn


def test_legacy_notebook_conversation_can_continue_in_workspace_scope():
    conversation_id = uuid.uuid4()
    legacy_notebook_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    payload = AskIn(question="Follow up", conversation_id=str(conversation_id))

    with patch.object(
        ask_routes,
        "get_conversation",
        return_value=SimpleNamespace(notebook_id=legacy_notebook_id),
    ):
        filters, notebook_id = ask_routes._scoped_ask(
            SimpleNamespace(),
            SimpleNamespace(org_id=uuid.uuid4()),
            payload,
            workspace_id,
        )

    assert notebook_id is None
    assert filters is not None
    assert filters["document_ids"] == []


def test_explicit_notebook_scope_still_rejects_conversation_from_another_notebook():
    conversation_id = uuid.uuid4()
    requested_notebook_id = uuid.uuid4()
    payload = AskIn(
        question="Follow up",
        conversation_id=str(conversation_id),
        notebook_id=str(requested_notebook_id),
    )

    with patch.object(
        ask_routes,
        "get_conversation",
        return_value=SimpleNamespace(notebook_id=uuid.uuid4()),
    ):
        with pytest.raises(HTTPException) as exc_info:
            ask_routes._scoped_ask(
                SimpleNamespace(),
                SimpleNamespace(org_id=uuid.uuid4()),
                payload,
                uuid.uuid4(),
            )

    assert exc_info.value.status_code == 404
