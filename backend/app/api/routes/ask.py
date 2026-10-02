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
from sqlalchemy import select, func
from app.db.models import Message
from app.db.pagination import seek_before
from app.core.errors import AppError

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
from app.notebooks import service as notebooks
from app.security.deps import resolve_principal
from app.security.principal import Principal

router = APIRouter(tags=["generation"])


def _notebook_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="That notebook id is not valid.") from exc


def _scoped_ask(
    db: Session, principal: Principal, payload: schemas.AskIn, workspace_id: uuid.UUID
) -> tuple[dict | None, uuid.UUID | None]:
    """Limit retrieval to the notebook's switched-on sources.

    The saved membership is the authority. A client cannot widen it by sending
    extra document ids. An empty notebook searches nothing, so expert mode can
    still answer from general knowledge.
    """
    filters = payload.filters.model_dump() if payload.filters else None
    notebook_id = _notebook_uuid(payload.notebook_id)
    if payload.conversation_id:
        try:
            conv_uuid = uuid.UUID(payload.conversation_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid conversation ID") from exc
        conv = get_conversation(db, conversation_id=conv_uuid, workspace_id=workspace_id)
        # Notebook-less Ask is the workspace-wide mode. Existing conversations
        # may carry legacy notebook metadata, but omitted notebook scope must not
        # silently narrow their follow-up questions back to that old notebook.
        if conv is None or (notebook_id is not None and conv.notebook_id != notebook_id):
            raise HTTPException(status_code=404, detail="Conversation not found")
    if notebook_id is None:
        return filters, None
    from app.core.errors import AppError

    try:
        notebook = notebooks.get_notebook(db, org_id=principal.org_id, notebook_id=notebook_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    if notebook.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Notebook not found.")
    scoped = dict(filters or {})
    scoped["document_ids"] = [str(item) for item in notebooks.enabled_document_ids(db, notebook=notebook)]
    return scoped, notebook_id


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
    filters, notebook_id = _scoped_ask(db, principal, payload, workspace_id)

    if payload.stream:
        return _stream_response(db, principal, payload, workspace_id, filters, notebook_id)

    try:
        answer = generation_ask(
            db,
            principal=principal,
            question=payload.question,
            conversation_id=payload.conversation_id,
            filters=filters,
            exclude_document_ids=payload.exclude_document_ids,
            workspace_id=workspace_id,
            enable_tools=payload.enable_tools,
            strict_mode=payload.strict_mode,
            notebook_id=notebook_id,
            web_search=payload.web_search,
            attachment_document_ids=payload.attachment_document_ids,
            goal=payload.goal,
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


@router.post("/ask/web-sources", response_model=schemas.WebSourceSaveOut, status_code=202)
def save_web_source(
    payload: schemas.WebSourceSaveIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> schemas.WebSourceSaveOut:
    """Ingest one web result into the knowledge base and the current notebook."""
    from urllib.parse import urlparse

    from app.core.errors import AppError, DuplicateDocument, SsrfBlocked
    from app.documents.metadata import DocumentMetadataIn
    from app.documents.service import create_document, enqueue_ingestion
    from app.net import ssrf
    from app.security.labels import SourceType

    try:
        rules = ssrf.fetch_robots(payload.url)
        if not rules.allows(payload.url):
            raise HTTPException(status_code=422, detail="That page asks not to be saved.")
        resource = ssrf.fetch(payload.url)
    except SsrfBlocked as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    path = urlparse(resource.final_url).path
    name = path.rstrip("/").split("/")[-1] or urlparse(resource.final_url).netloc
    if "." not in name:
        name = f"{name}.html"
    meta = DocumentMetadataIn(
        title=payload.title,
        source_type=str(SourceType.URL),
        source_url=resource.final_url,
        source_of_truth_url=resource.final_url,
    )
    try:
        document = create_document(
            db,
            principal=principal,
            original_filename=name[:255],
            data=resource.data,
            mime_type=resource.content_type,
            metadata=meta,
        )
        enqueue_ingestion(db, document)
    except DuplicateDocument as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    notebook_id = _notebook_uuid(payload.notebook_id)
    if notebook_id is not None:
        try:
            notebooks.enable_document(
                db,
                org_id=principal.org_id,
                notebook_id=notebook_id,
                document_id=document.id,
            )
        except AppError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return schemas.WebSourceSaveOut(
        document_id=str(document.id),
        notebook_id=str(notebook_id) if notebook_id else None,
    )


@router.get("/ask/mention-targets", response_model=list[schemas.MentionTargetOut])
def get_mention_targets_endpoint(
    q: str = Query("", min_length=0, max_length=100),
    category: schemas.MentionCategory | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> list[schemas.MentionTargetOut]:
    """Autocomplete targets for @ mentions (notes, products, connectors, websites)."""
    from app.generation.handlers import get_mention_targets

    workspace_id = _workspace_id_from_principal(db, principal)
    return get_mention_targets(
        db, workspace_id, principal.org_id, q=q, category=category, limit=limit, principal=principal
    )


@router.get("/ask/product-connections", response_model=schemas.ProductConnectionsOut)
def get_product_connections_endpoint(
    product: str = Query(..., min_length=1, max_length=255),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> schemas.ProductConnectionsOut:
    """Inspect product connections, prerequisites, conflicts, and integrations."""
    from app.generation.handlers import get_product_connections_data

    workspace_id = _workspace_id_from_principal(db, principal)
    data = get_product_connections_data(db, workspace_id, product)
    if not data:
        raise HTTPException(
            status_code=404, detail=f"Product '{product}' not found in workspace catalog."
        )
    return data


def _stream_response(
    db: Session,
    principal: Principal,
    payload: schemas.AskIn,
    workspace_id: uuid.UUID,
    filters: dict | None = None,
    notebook_id: uuid.UUID | None = None,
) -> StreamingResponse:
    """Return an SSE streaming response."""

    def event_generator():
        try:
            for chunk in generation_ask_stream(
                db,
                principal=principal,
                question=payload.question,
                conversation_id=payload.conversation_id,
                filters=filters,
                exclude_document_ids=payload.exclude_document_ids,
                workspace_id=workspace_id,
                enable_tools=payload.enable_tools,
                strict_mode=payload.strict_mode,
                notebook_id=notebook_id,
                web_search=payload.web_search,
                attachment_document_ids=payload.attachment_document_ids,
                goal=payload.goal,
            ):
                event_data = {
                    "delta": chunk.delta,
                    "done": chunk.done,
                }
                if chunk.status:
                    event_data["status"] = chunk.status
                if chunk.done:
                    results_by_id = {result.id: result for result in chunk.tool_results}
                    event_data["tool_calls"] = [
                        {"id": call.id, "name": call.name, "arguments": call.arguments,
                         "error": results_by_id[call.id].error if call.id in results_by_id else None,
                         "content": results_by_id[call.id].content if call.id in results_by_id else None}
                        for call in chunk.tool_calls
                    ]
                    event_data["citations"] = [
                        c.as_dict() for c in chunk.citations
                    ]
                    event_data["web_note"] = chunk.web_note
                    event_data["web_sources"] = [s.as_dict() for s in chunk.web_sources]
                    if chunk.usage:
                        event_data["usage"] = chunk.usage.as_dict()
                    event_data["refused"] = chunk.refused
                    event_data["refusal_reason"] = chunk.refusal_reason
                    event_data["conversation_id"] = chunk.conversation_id
                    event_data["message_id"] = chunk.message_id
                    event_data["active_goal"] = getattr(chunk, "active_goal", None)
                    conn = getattr(chunk, "connections_result", None)
                    if conn:
                        event_data["connections_result"] = conn.model_dump() if hasattr(conn, "model_dump") else conn

                yield f"data: {json.dumps(event_data)}\n\n"

        except (GenerationRateLimited, TokenBudgetExhausted) as exc:
            yield f"data: {json.dumps({'error': str(exc), 'done': True})}\n\n"
        except (ProviderError, ProviderRateLimited) as exc:
            yield f"data: {json.dumps({'error': str(exc), 'done': True})}\n\n"
        except ValueError as exc:
            if "Conversation" in str(exc) and "not found" in str(exc):
                yield f"data: {json.dumps({'error': 'Conversation not found', 'status_code': 404, 'done': True})}\n\n"
            else:
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
    notebook_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> schemas.ConversationOut:
    """Create a new conversation."""
    workspace_id = _workspace_id_from_principal(db, principal)
    if notebook_id is not None:

        try:
            notebook = notebooks.get_notebook(db, org_id=principal.org_id, notebook_id=notebook_id)
        except AppError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
        if notebook.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="Notebook not found.")
    conv = create_conversation(
        db,
        workspace_id=workspace_id,
        notebook_id=notebook_id,
        org_id=principal.org_id,
    )
    return _conv_to_out(conv)


@router.get("/conversations", response_model=schemas.ConversationListOut)
def list_conversations_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    notebook_id: uuid.UUID | None = Query(default=None),
    cursor: str | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> schemas.ConversationListOut:
    """List conversations (paginated)."""
    workspace_id = _workspace_id_from_principal(db, principal)
    if notebook_id is not None:

        try:
            notebooks.get_notebook(db, org_id=principal.org_id, notebook_id=notebook_id)
        except AppError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    try:
        conversations, total = list_conversations(
            db, workspace_id=workspace_id, limit=limit, offset=offset, notebook_id=notebook_id, cursor=cursor
        )
    except AppError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc
    return schemas.ConversationListOut(
        conversations=[_conv_to_out(c) for c in conversations],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/conversations/{conversation_id}", response_model=schemas.ConversationOut)
def get_conversation_endpoint(
    conversation_id: str,
    notebook_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10000),
    cursor: str | None = None,
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
    if conv is None or (notebook_id is not None and conv.notebook_id != notebook_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    try:
        statement = seek_before(select(Message).where(Message.conversation_id == conv.id), Message.created_at, Message.id, cursor)
    except AppError as exc:
        raise HTTPException(exc.status_code, exc.message) from exc
    rows = list(db.scalars(statement.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit).offset(0 if cursor else offset)))
    rows.reverse()
    result = _conv_to_out(conv, include_messages=True, message_rows=rows)
    result.message_total = db.scalar(select(func.count()).select_from(Message).where(Message.conversation_id == conv.id)) or 0
    result.message_limit = limit
    result.message_offset = offset
    from app.generation.conversations import get_active_goal
    result.goal = get_active_goal(db, conversation_id=conv.id)
    return result


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
    filters, notebook_uuid = _scoped_ask(db, principal, payload, workspace_id)

    if payload.stream:
        return _stream_response(db, principal, payload, workspace_id, filters, notebook_uuid)

    try:
        answer = generation_ask(
            db,
            principal=principal,
            question=payload.question,
            conversation_id=conversation_id,
            filters=filters,
            exclude_document_ids=payload.exclude_document_ids,
            workspace_id=workspace_id,
            enable_tools=payload.enable_tools,
            strict_mode=payload.strict_mode,
            notebook_id=notebook_uuid,
            web_search=payload.web_search,
            attachment_document_ids=payload.attachment_document_ids,
            goal=payload.goal,
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
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=10000),
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

    for msg in db.scalars(select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at.desc(), Message.id.desc()).limit(limit).offset(offset)):
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
        web_note=getattr(answer, "web_note", None),
        web_sources=[
            schemas.SourceMetadataOut(**s.as_dict()) for s in getattr(answer, "web_sources", [])
        ],
        active_goal=getattr(answer, "active_goal", None),
        connections_result=getattr(answer, "connections_result", None),
    )


def _conv_to_out(
    conv, include_messages: bool = False, message_rows=None
) -> schemas.ConversationOut:
    """Convert a Conversation ORM object to the output schema."""
    messages: list[schemas.MessageOut] = []
    if include_messages:
        for msg in message_rows if message_rows is not None else conv.messages:
            sources_raw = msg.sources or []
            citations_raw = (msg.citations or {}).get("items", []) if isinstance(msg.citations, dict) else []
            trace = (msg.usage or {}).get("tool_trace", {})
            results = {row.get("id"): row for row in trace.get("results", [])}
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
                        if msg.usage and "prompt_tokens" in msg.usage
                        else None
                    ),
                    tool_calls=[schemas.ToolCallOut(id=call["id"], name=call["name"],
                        arguments=call.get("arguments") or {},
                        error=(results.get(call["id"]) or {}).get("error"),
                        content=(results.get(call["id"]) or {}).get("content"))
                        for call in trace.get("calls", [])],
                    prompt_version=msg.prompt_version,
                    refused=msg.refused,
                    model_id=msg.model_id,
                    created_at=msg.created_at.isoformat(),
                    active_goal=(msg.usage or {}).get("ask_state", {}).get("active_goal"),
                    connections_result=(msg.usage or {}).get("ask_state", {}).get("connections_result"),
                )
            )

    return schemas.ConversationOut(
        id=str(conv.id),
        workspace_id=str(conv.workspace_id),
        notebook_id=str(conv.notebook_id) if conv.notebook_id else None,
        title=conv.title,
        messages=messages,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
    )
