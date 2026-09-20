"""RAG orchestration: retrieval → injection containment → LLM → cited answer.

This is the heart of Phase 3. The service:
1. Receives a question + optional conversation context + optional filters
2. Calls permission-aware search from the retrieval module
3. Wraps each search hit through wrap_untrusted() (injection containment)
4. Builds the prompt using versioned templates from prompts.py
5. Calls the LLM provider (sync or streaming)
6. Maps citations back to SourceMetadata with provenance
7. Records usage for budget tracking

No tool access exists in this path. Document content reaches the LLM only
through wrap_untrusted(), and the system prompt states that document content
can never issue instructions.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.documents.injection import wrap_untrusted
from app.generation.conversations import (
    add_message,
    auto_title,
    create_conversation,
    get_conversation,
    get_history,
)
from app.generation.rate_limit import (
    check_rate_limit,
    check_token_budget,
    record_token_usage,
)
from app.llm.base import GroundedAnswer, GroundedAnswerChunk, SourceMetadata
from app.llm.factory import get_llm_provider
from app.llm.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_context_block,
    build_user_message,
)
from app.retrieval.search import search as run_search
from app.retrieval.spec import RetrievalFilters
from app.security.principal import Principal

logger = get_logger(__name__)


def _build_retrieval_filters(
    filters: dict | None,
    exclude_document_ids: list[str] | None = None,
) -> RetrievalFilters:
    """Convert the generation request filters to retrieval filters."""
    if filters is None:
        filters = {}
    excluded = list(exclude_document_ids or filters.get("exclude_document_ids", []))
    return RetrievalFilters(
        products=filters.get("products", []),
        vendor=filters.get("vendor"),
        ownership=filters.get("ownership"),
        account_ref=filters.get("account_ref"),
        approved_only=filters.get("approved_only", True),
        exclude_injection_flagged=filters.get("exclude_injection_flagged", True),
        document_ids=filters.get("document_ids", []),
        exclude_document_ids=excluded,
    )


def _prepare_context(
    db: Session,
    principal: Principal,
    question: str,
    filters: dict | None = None,
    exclude_document_ids: list[str] | None = None,
) -> tuple[list[dict], list[SourceMetadata]]:
    """Retrieve and prepare context chunks for the LLM.

    Returns:
        (context_chunks for the LLM, source_metadata for the response)
    """
    retrieval_filters = _build_retrieval_filters(filters, exclude_document_ids)
    max_chunks = settings.generation_max_context_chunks

    search_result = run_search(
        db,
        principal=principal,
        query=question,
        filters=retrieval_filters,
        mode="hybrid",
        top_k=max_chunks,
    )

    context_chunks: list[dict] = []
    source_metadata: list[SourceMetadata] = []

    for i, hit in enumerate(search_result.hits):
        # Source toggling: skip excluded documents
        if exclude_document_ids and hit.document_id in exclude_document_ids:
            continue

        index = i + 1
        citation = hit.citation

        # Wrap the text through injection containment
        fenced_text = wrap_untrusted(
            hit.text,
            source=citation,
        )

        metadata = {
            "chunk_id": hit.chunk_id,
            "document_id": hit.document_id,
            "document_title": hit.document_title,
            "page_number": hit.page_number,
            "slide_number": hit.slide_number,
            "sheet_name": hit.sheet_name,
            "cell_range": hit.cell_range,
            "heading_path": hit.heading_path,
            "vendor": hit.vendor,
            "ownership": hit.ownership,
            "approval_state": hit.approval_state,
            "sensitivity": hit.sensitivity,
            "valid_until": hit.valid_until,
            "is_stale": hit.is_stale,
        }

        context_chunks.append({
            "index": index,
            "fenced_text": fenced_text,
            "citation": citation,
            "metadata": metadata,
        })

        source_metadata.append(
            SourceMetadata(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                document_title=hit.document_title,
                citation=citation,
                page_number=hit.page_number,
                slide_number=hit.slide_number,
                sheet_name=hit.sheet_name,
                cell_range=hit.cell_range,
                heading_path=hit.heading_path,
                vendor=hit.vendor,
                ownership=hit.ownership,
                approval_state=hit.approval_state,
                sensitivity=hit.sensitivity,
                valid_until=hit.valid_until,
                is_stale=hit.is_stale,
            )
        )

    return context_chunks, source_metadata


def ask(
    db: Session,
    *,
    principal: Principal,
    question: str,
    conversation_id: str | None = None,
    filters: dict | None = None,
    exclude_document_ids: list[str] | None = None,
    workspace_id: uuid.UUID | None = None,
) -> GroundedAnswer:
    """Generate a grounded answer (synchronous).

    The full pipeline:
    1. Rate limit check
    2. Token budget check
    3. Retrieve permission-aware context
    4. Build prompt with injection containment
    5. Generate answer
    6. Record usage + persist message
    """
    # Cost controls
    check_rate_limit(principal.user_id)
    check_token_budget(db, principal.org_id)

    # Conversation management
    conv_uuid: uuid.UUID | None = None
    history: list[dict] | None = None

    if conversation_id:
        conv_uuid = uuid.UUID(conversation_id)
        if workspace_id:
            conv = get_conversation(db, conversation_id=conv_uuid, workspace_id=workspace_id)
            if conv is None:
                raise ValueError(f"Conversation {conversation_id} not found")
        history = get_history(db, conversation_id=conv_uuid)
    elif workspace_id:
        conv = create_conversation(db, workspace_id=workspace_id, title=question[:200])
        conv_uuid = conv.id

    # Retrieve and prepare context
    context_chunks, all_sources = _prepare_context(
        db, principal, question, filters, exclude_document_ids
    )

    # Build the full prompt
    context_block = build_context_block(context_chunks)
    user_message = build_user_message(question, context_block)

    # Generate
    provider = get_llm_provider()
    answer = provider.generate_grounded_answer(
        user_message,
        context_chunks,
        system_prompt=SYSTEM_PROMPT,
        history=history,
    )

    # Record token usage
    if answer.usage:
        record_token_usage(
            db,
            principal.org_id,
            answer.usage.prompt_tokens,
            answer.usage.completion_tokens,
        )

    # Persist messages
    if conv_uuid:
        add_message(db, conversation_id=conv_uuid, role="user", content=question)
        assistant_msg = add_message(
            db,
            conversation_id=conv_uuid,
            role="assistant",
            content=answer.text,
            citations=[c.as_dict() for c in answer.citations],
            sources=[s.as_dict() for s in all_sources],
            usage=answer.usage.as_dict() if answer.usage else None,
            prompt_version=answer.prompt_version,
            refused=answer.refused,
            model_id=answer.model_id,
        )
        auto_title(db, conversation_id=conv_uuid, question=question)
        answer.conversation_id = str(conv_uuid)
        answer.message_id = str(assistant_msg.id)

    logger.info(
        "ask model=%s refused=%s citations=%d prompt_v=%s conv=%s",
        answer.model_id,
        answer.refused,
        len(answer.citations),
        answer.prompt_version,
        conv_uuid,
    )

    return answer


def ask_stream(
    db: Session,
    *,
    principal: Principal,
    question: str,
    conversation_id: str | None = None,
    filters: dict | None = None,
    exclude_document_ids: list[str] | None = None,
    workspace_id: uuid.UUID | None = None,
) -> Iterator[GroundedAnswerChunk]:
    """Generate a grounded answer with streaming.

    Yields GroundedAnswerChunk objects. The final chunk has done=True and
    contains citations and usage. Token usage is recorded after the stream
    completes.
    """
    # Cost controls
    check_rate_limit(principal.user_id)
    check_token_budget(db, principal.org_id)

    # Conversation management
    conv_uuid: uuid.UUID | None = None
    history: list[dict] | None = None

    if conversation_id:
        conv_uuid = uuid.UUID(conversation_id)
        if workspace_id:
            conv = get_conversation(db, conversation_id=conv_uuid, workspace_id=workspace_id)
            if conv is None:
                raise ValueError(f"Conversation {conversation_id} not found")
        history = get_history(db, conversation_id=conv_uuid)
    elif workspace_id:
        conv = create_conversation(db, workspace_id=workspace_id, title=question[:200])
        conv_uuid = conv.id

    # Retrieve and prepare context
    context_chunks, all_sources = _prepare_context(
        db, principal, question, filters, exclude_document_ids
    )

    # Build the full prompt
    context_block = build_context_block(context_chunks)
    user_message = build_user_message(question, context_block)

    # Stream generation
    provider = get_llm_provider()
    accumulated_text = ""

    for chunk in provider.stream_grounded_answer(
        user_message,
        context_chunks,
        system_prompt=SYSTEM_PROMPT,
        history=history,
    ):
        accumulated_text += chunk.delta
        yield chunk

        if chunk.done:
            # Record token usage
            if chunk.usage:
                record_token_usage(
                    db,
                    principal.org_id,
                    chunk.usage.prompt_tokens,
                    chunk.usage.completion_tokens,
                )

            # Persist messages
            if conv_uuid:
                add_message(db, conversation_id=conv_uuid, role="user", content=question)
                assistant_msg = add_message(
                    db,
                    conversation_id=conv_uuid,
                    role="assistant",
                    content=accumulated_text,
                    citations=[c.as_dict() for c in chunk.citations],
                    sources=[s.as_dict() for s in all_sources],
                    usage=chunk.usage.as_dict() if chunk.usage else None,
                    prompt_version=PROMPT_VERSION,
                    refused=chunk.refused,
                    model_id=provider.model_id,
                )
                auto_title(db, conversation_id=conv_uuid, question=question)
                chunk.conversation_id = str(conv_uuid)
                chunk.message_id = str(assistant_msg.id)

            logger.info(
                "ask_stream done model=%s refused=%s citations=%d conv=%s",
                provider.model_id,
                chunk.refused,
                len(chunk.citations),
                conv_uuid,
            )
