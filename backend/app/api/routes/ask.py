"""API routes for Phase 3: grounded answers and conversations.

Endpoints:
    POST /ask                          — grounded answer (sync or SSE streaming)
    POST /conversations                — create a conversation
    GET  /conversations                — list conversations (paginated)
    GET  /conversations/{id}           — get conversation with messages
    DELETE /conversations/{id}         — delete conversation
    POST /conversations/{id}/ask       — ask within a conversation (carries history)

All endpoints require resolve_principal. All respect permission-aware retrieval.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.errors import (
    GenerationRateLimited,
    PermissionFilterMissing,
    ProviderError,
    ProviderRateLimited,
    TokenBudgetExhausted,
)
from app.db.session import get_db
from app.generation import schemas
from app.generation.conversations import (
    create_conversation,
    delete_conversation,
    get_conversation,
    list_conversations,
)
from app.generation.service import ask as generation_ask
from app.generation.service import ask_stream as generation_ask_stream
from app.security.deps import resolve_principal
from app.security.principal import Principal

router = APIRouter(tags=["generation"])


def _workspace_id_from_principal(db: Session, principal: Principal) -> uuid.UUID:
    """Get or create the default workspace for the principal's org.

    This is the Phase 0 shortcut: with one owner, there is one workspace per org.
    When Phase 0 lands, workspace selection becomes explicit.
    """
    from app.db.models import Workspace

    from sqlalchemy import select

    workspace = db.scalars(
        select(Workspace).where(Workspace.org_id == principal.org_id).limit(1)
    ).first()
    if workspace:
        return workspace.id
    # Create default workspace
    workspace = Workspace(org_id=principal.org_id, name="Default Workspace")
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace.id


# ── ask endpoint ────────────────────────────────────────────────────────


@router.post("/ask", response_model=schemas.AskOut)
def ask_endpoint(
    payload: schemas.AskIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> schemas.AskOut | StreamingResponse:
    """Generate a grounded answer from the knowledge base.

    If `stream=true`, returns an SSE stream of GroundedAnswerChunk events.
    Otherwise returns a complete AskOut response.
    """
    workspace_id = _workspace_id_from_principal(db, principal)

    if payload.stream:
        return _stream_response(db, principal, payload, workspace_id)

    try:
        answer = generation_ask(
            db,
            principal=principal,
            question=payload.question,
            conversation_id=payload.conversation_id,
            filters=payload.filters.model_dump() if payload.filters else None,
            exclude_document_ids=payload.exclude_document_ids,
            workspace_id=workspace_id,
            enable_tools=payload.enable_tools,
            strict_mode=payload.strict_mode,
        )
    except GenerationRateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except TokenBudgetExhausted as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ProviderRateLimited as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except PermissionFilterMissing:
        raise HTTPException(
            status_code=500, detail="retrieval is misconfigured and was refused"
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _answer_to_out(answer, fallback_conversation_id=payload.conversation_id)


def _stream_response(
    db: Session,
    principal: Principal,
    payload: schemas.AskIn,
    workspace_id: uuid.UUID,
) -> StreamingResponse:
    """Return an SSE streaming response."""

    def event_generator():
        try:
            for chunk in generation_ask_stream(
                db,
                principal=principal,
                question=payload.question,
                conversation_id=payload.conversation_id,
                filters=payload.filters.model_dump() if payload.filters else None,
                exclude_document_ids=payload.exclude_document_ids,
                workspace_id=workspace_id,
                enable_tools=payload.enable_tools,
                strict_mode=payload.strict_mode,
            ):
                event_data = {
                    "delta": chunk.delta,
                    "done": chunk.done,
                }
                if chunk.done:
                    event_data["citations"] = [
                        c.as_dict() for c in chunk.citations
                    ]
                    if chunk.usage:
                        event_data["usage"] = chunk.usage.as_dict()
                    event_data["refused"] = chunk.refused
                    event_data["refusal_reason"] = chunk.refusal_reason
                    event_data["conversation_id"] = chunk.conversation_id
                    event_data["message_id"] = chunk.message_id

                yield f"data: {json.dumps(event_data)}\n\n"

        except (GenerationRateLimited, TokenBudgetExhausted) as exc:
            yield f"data: {json.dumps({'error': str(exc), 'done': True})}\n\n"
        except (ProviderError, ProviderRateLimited) as exc:
            yield f"data: {json.dumps({'error': str(exc), 'done': True})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── conversation endpoints ──────────────────────────────────────────────


@router.post("/conversations", response_model=schemas.ConversationOut, status_code=201)
def create_conversation_endpoint(
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> schemas.ConversationOut:
    """Create a new conversation."""
    workspace_id = _workspace_id_from_principal(db, principal)
    conv = create_conversation(db, workspace_id=workspace_id)
    return _conv_to_out(conv)


@router.get("/conversations", response_model=schemas.ConversationListOut)
def list_conversations_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> schemas.ConversationListOut:
    """List conversations (paginated)."""
    workspace_id = _workspace_id_from_principal(db, principal)
    conversations, total = list_conversations(
        db, workspace_id=workspace_id, limit=limit, offset=offset
    )
    return schemas.ConversationListOut(
        conversations=[_conv_to_out(c) for c in conversations],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/conversations/{conversation_id}", response_model=schemas.ConversationOut)
def get_conversation_endpoint(
    conversation_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> schemas.ConversationOut:
    """Get a conversation with all its messages."""
    workspace_id = _workspace_id_from_principal(db, principal)
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID") from None

    conv = get_conversation(db, conversation_id=conv_uuid, workspace_id=workspace_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _conv_to_out(conv, include_messages=True)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation_endpoint(
    conversation_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> None:
    """Delete a conversation and all its messages."""
    workspace_id = _workspace_id_from_principal(db, principal)
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID") from None

    deleted = delete_conversation(db, conversation_id=conv_uuid, workspace_id=workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.post(
    "/conversations/{conversation_id}/ask", response_model=schemas.AskOut
)
def ask_in_conversation_endpoint(
    conversation_id: str,
    payload: schemas.AskIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> schemas.AskOut | StreamingResponse:
    """Ask a question within an existing conversation (carries history)."""
    workspace_id = _workspace_id_from_principal(db, principal)
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID") from None

    conv = get_conversation(db, conversation_id=conv_uuid, workspace_id=workspace_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Override conversation_id in the payload
    payload.conversation_id = conversation_id

    if payload.stream:
        return _stream_response(db, principal, payload, workspace_id)

    try:
        answer = generation_ask(
            db,
            principal=principal,
            question=payload.question,
            conversation_id=conversation_id,
            filters=payload.filters.model_dump() if payload.filters else None,
            exclude_document_ids=payload.exclude_document_ids,
            workspace_id=workspace_id,
            enable_tools=payload.enable_tools,
            strict_mode=payload.strict_mode,
        )
    except GenerationRateLimited as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except TokenBudgetExhausted as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ProviderRateLimited as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except PermissionFilterMissing:
        raise HTTPException(
            status_code=500, detail="retrieval is misconfigured and was refused"
        ) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _answer_to_out(answer, fallback_conversation_id=conversation_id)


@router.get(
    "/conversations/{conversation_id}/sources",
    response_model=list[schemas.SourceMetadataOut],
)
def get_conversation_sources_endpoint(
    conversation_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> list[schemas.SourceMetadataOut]:
    """Inspect source collateral for a conversation across all turns."""
    workspace_id = _workspace_id_from_principal(db, principal)
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation ID") from None

    conv = get_conversation(db, conversation_id=conv_uuid, workspace_id=workspace_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    seen_chunks: set[str] = set()
    aggregated_sources: list[schemas.SourceMetadataOut] = []

    for msg in conv.messages:
        sources_raw = msg.sources or []
        for s in sources_raw:
            chunk_id = s.get("chunk_id")
            if chunk_id and chunk_id not in seen_chunks:
                seen_chunks.add(chunk_id)
                aggregated_sources.append(schemas.SourceMetadataOut(**s))
            elif not chunk_id:
                aggregated_sources.append(schemas.SourceMetadataOut(**s))

    return aggregated_sources


# ── helpers ─────────────────────────────────────────────────────────────


def _answer_to_out(answer, *, fallback_conversation_id: str | None) -> schemas.AskOut:
    results_by_id = {r.id: r for r in answer.tool_results}
    tool_calls = []
    for call in answer.tool_calls:
        result = results_by_id.get(call.id)
        tool_calls.append(
            schemas.ToolCallOut(
                id=call.id,
                name=call.name,
                arguments=call.arguments,
                error=result.error if result else None,
                content=result.content if result else None,
            )
        )
    usage_out = None
    if answer.usage:
        usage_out = schemas.TokenUsageOut(**answer.usage.as_dict())
    return schemas.AskOut(
        answer=answer.text,
        citations=[schemas.SourceMetadataOut(**c.as_dict()) for c in answer.citations],
        model_id=answer.model_id,
        prompt_version=answer.prompt_version,
        refused=answer.refused,
        refusal_reason=answer.refusal_reason,
        usage=usage_out,
        conversation_id=answer.conversation_id or fallback_conversation_id,
        message_id=answer.message_id,
        tool_calls=tool_calls,
    )


def _conv_to_out(
    conv, include_messages: bool = False
) -> schemas.ConversationOut:
    """Convert a Conversation ORM object to the output schema."""
    messages: list[schemas.MessageOut] = []
    if include_messages and hasattr(conv, "messages"):
        for msg in conv.messages:
            sources_raw = msg.sources or []
            citations_raw = (msg.citations or {}).get("items", []) if isinstance(msg.citations, dict) else []
            messages.append(
                schemas.MessageOut(
                    id=str(msg.id),
                    role=msg.role,
                    content=msg.content,
                    citations=[
                        schemas.SourceMetadataOut(**c) for c in citations_raw
                    ],
                    sources=[
                        schemas.SourceMetadataOut(**s) for s in sources_raw
                    ],
                    usage=(
                        schemas.TokenUsageOut(**msg.usage)
                        if msg.usage
                        else None
                    ),
                    prompt_version=msg.prompt_version,
                    refused=msg.refused,
                    model_id=msg.model_id,
                    created_at=msg.created_at.isoformat(),
                )
            )

    return schemas.ConversationOut(
        id=str(conv.id),
        workspace_id=str(conv.workspace_id),
        title=conv.title,
        messages=messages,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
    )
