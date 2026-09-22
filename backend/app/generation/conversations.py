"""Conversation CRUD for Phase 3.

Uses the existing Conversation and Message models from app.db.models.
Conversations are scoped to a workspace, and messages carry structured
citations and token usage for provenance tracking.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Conversation, Message

logger = get_logger(__name__)


def create_conversation(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    title: str | None = None,
    notebook_id: uuid.UUID | None = None,
    org_id: uuid.UUID | None = None,
) -> Conversation:
    """Create a new conversation in the given workspace."""
    conv = Conversation(
        workspace_id=workspace_id, title=title, notebook_id=notebook_id, org_id=org_id
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    logger.info("created conversation %s in workspace %s", conv.id, workspace_id)
    return conv


def get_conversation(
    db: Session,
    *,
    conversation_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Conversation | None:
    """Get a conversation by ID, scoped to workspace for tenant isolation."""
    return db.scalars(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace_id,
        )
    ).first()


def list_conversations(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
    notebook_id: uuid.UUID | None = None,
) -> tuple[list[Conversation], int]:
    """List conversations in a workspace with pagination."""
    filters = [Conversation.workspace_id == workspace_id]
    if notebook_id is not None:
        filters.append(Conversation.notebook_id == notebook_id)
    total = db.scalar(select(func.count()).select_from(Conversation).where(*filters)) or 0

    conversations = list(
        db.scalars(
            select(Conversation)
            .where(*filters)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return conversations, total


def delete_conversation(
    db: Session,
    *,
    conversation_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> bool:
    """Delete a conversation (cascade deletes messages). Returns True if found."""
    conv = get_conversation(db, conversation_id=conversation_id, workspace_id=workspace_id)
    if conv is None:
        return False
    db.delete(conv)
    db.commit()
    logger.info("deleted conversation %s", conversation_id)
    return True


def add_message(
    db: Session,
    *,
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    citations: list[dict] | None = None,
    sources: list[dict] | None = None,
    usage: dict | None = None,
    prompt_version: str | None = None,
    refused: bool = False,
    model_id: str | None = None,
) -> Message:
    """Add a message to a conversation."""
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        citations={"items": citations} if citations else None,
        sources=sources,
        usage=usage,
        prompt_version=prompt_version,
        refused=refused,
        model_id=model_id,
    )
    db.add(msg)

    # Touch the conversation's updated_at
    conv = db.get(Conversation, conversation_id)
    if conv:
        conv.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(msg)
    return msg


def get_history(
    db: Session,
    *,
    conversation_id: uuid.UUID,
    max_turns: int | None = None,
) -> list[dict]:
    """Get conversation history formatted for the LLM.

    Returns the most recent `max_turns` messages as role/content dicts.
    """
    max_turns = max_turns or settings.generation_max_history_turns

    messages = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
    )

    # Keep only the last N turns (each user+assistant pair = 2 messages)
    if len(messages) > max_turns * 2:
        messages = messages[-(max_turns * 2):]

    return [
        {"role": msg.role, "content": msg.content}
        for msg in messages
    ]


def auto_title(
    db: Session,
    *,
    conversation_id: uuid.UUID,
    question: str,
) -> None:
    """Set the conversation title from the first question if not already titled."""
    conv = db.get(Conversation, conversation_id)
    if conv and not conv.title:
        conv.title = question[:200].strip()
        db.commit()
