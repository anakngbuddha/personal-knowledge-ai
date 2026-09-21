"""RAG orchestration: retrieval -> injection containment -> LLM -> cited answer.

This is the heart of Phase 3. The service:
1. Receives a question + optional conversation context + optional filters
2. Calls permission-aware search from the retrieval module
3. Wraps each search hit through wrap_untrusted() (injection containment)
4. Builds the prompt using versioned templates from prompts.py
5. Calls the LLM provider (sync or streaming)
6. Maps citations back to SourceMetadata with provenance
7. Records usage for budget tracking

Tool access is opt-in via enable_tools. Document content reaches the LLM only
through wrap_untrusted(), and the system prompt states that document content
can never issue instructions.

2.3 adds one step between search and prompt: when the matched chunk is a child of a
larger section, the parent passage is prompted instead of the child. The citation still
points at the child, so provenance does not get vaguer as context gets wider.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import DocumentChunk
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
    system_prompt_for,
)
from app.retrieval.rewrite import expand_queries, keyword_overlap_score, rewrite_query
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


def _parent_passages(db: Session, chunk_ids: list[str]) -> dict[str, str]:
    """Fetch the stored parent section for each matched child chunk.

    Best effort on purpose. A chunk written before 2.3 has no parent, and a lookup
    failure must never cost the user an answer.
    """
    if not settings.chunk_parent_child_enabled or not chunk_ids:
        return {}

    ids: list[uuid.UUID] = []
    for chunk_id in chunk_ids:
        try:
            ids.append(uuid.UUID(str(chunk_id)))
        except (TypeError, ValueError):
            continue
    if not ids:
        return {}

    ceiling = settings.chunk_size * max(1, settings.chunk_table_max_multiple)
    passages: dict[str, str] = {}
    try:
        rows = db.execute(
            select(DocumentChunk.id, DocumentChunk.chunk_metadata).where(
                DocumentChunk.id.in_(ids)
            )
        ).all()
    except Exception:  # noqa: BLE001 - never fail an answer over extra context
        logger.debug("parent passage lookup failed", exc_info=True)
        return {}

    for row_id, metadata in rows:
        parent = (metadata or {}).get("parent_text")
        if isinstance(parent, str) and parent.strip() and len(parent) <= ceiling:
            passages[str(row_id)] = parent
    return passages


def _prepare_context(
    db: Session,
    principal: Principal,
    question: str,
    filters: dict | None = None,
    exclude_document_ids: list[str] | None = None,
    history: list[dict] | None = None,
) -> tuple[list[dict], list[SourceMetadata]]:
    """Retrieve and prepare context chunks for the LLM.

    Rewrites follow-ups using conversation history, expands broad questions
    into a few sub-queries, optionally reranks the fused hits, and widens each
    surviving hit to its parent section.
    """
    retrieval_filters = _build_retrieval_filters(filters, exclude_document_ids)
    max_chunks = settings.generation_max_context_chunks
    search_query = rewrite_query(question, history)
    queries = expand_queries(search_query)
    candidate_k = (
        settings.generation_rerank_candidates
        if settings.generation_rerank_enabled
        else max_chunks
    )

    merged: dict[str, object] = {}
    for query in queries:
        search_result = run_search(
            db,
            principal=principal,
            query=query,
            filters=retrieval_filters,
            mode="hybrid",
            top_k=candidate_k,
        )
        for hit in search_result.hits:
            previous = merged.get(hit.chunk_id)
            score = float(getattr(hit, "rrf_score", 0) or 0)
            if previous is None or score > float(getattr(previous, "rrf_score", 0) or 0):
                merged[hit.chunk_id] = hit

    hits = list(merged.values())
    if settings.generation_rerank_enabled and hits:
        hits.sort(
            key=lambda hit: (
                keyword_overlap_score(search_query, getattr(hit, "text", "") or ""),
                float(getattr(hit, "rrf_score", 0) or 0),
            ),
            reverse=True,
        )
    hits = hits[:max_chunks]

    parents = _parent_passages(db, [hit.chunk_id for hit in hits])

    context_chunks: list[dict] = []
    source_metadata: list[SourceMetadata] = []

    for i, hit in enumerate(hits):
        # Source toggling: skip excluded documents
        if exclude_document_ids and hit.document_id in exclude_document_ids:
            continue

        index = i + 1
        citation = hit.citation

        # Prompt the parent section when there is one; cite the child either way.
        prompt_text = parents.get(hit.chunk_id) or hit.text

        # Wrap the text through injection containment
        fenced_text = wrap_untrusted(
            prompt_text,
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
    enable_tools: bool = True,
    strict_mode: bool = False,
    persist: bool = True,
) -> GroundedAnswer:
    """Generate a grounded answer (synchronous).

    The full pipeline:
    1. Rate limit check
    2. Token budget check
    3. Retrieve permission-aware context
    4. Build prompt with injection containment
    5. Generate answer (optional single-turn tool loop)
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
        db, principal, question, filters, exclude_document_ids, history
    )

    # Build the full prompt
    context_block = build_context_block(context_chunks, strict_mode=strict_mode)
    user_message = build_user_message(question, context_block)
    prompt = system_prompt_for(enable_tools=enable_tools, strict_mode=strict_mode)

    # Generate
    provider = get_llm_provider()
    if enable_tools:
        if workspace_id is None:
            raise ValueError("enable_tools requires a workspace")
        from app.tools.loop import run_tool_loop
        from app.tools.registry import ToolContext, default_definitions, execute_tool

        ctx = ToolContext(db=db, principal=principal, workspace_id=workspace_id)

        def _execute(call):
            return execute_tool(call, ctx)

        answer = run_tool_loop(
            provider,
            user_message,
            context_chunks,
            system_prompt=prompt,
            history=history,
            tools=default_definitions(ctx),
            execute=_execute,
        )
    else:
        answer = provider.generate_grounded_answer(
            user_message,
            context_chunks,
            system_prompt=prompt,
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
        answer.conversation_id = str(conv_uuid)
        if persist:
            add_message(db, conversation_id=conv_uuid, role="user", content=question)
            assistant_msg = add_message(
                db,
                conversation_id=conv_uuid,
                role="assistant",
                content=answer.text,
                citations=[c.as_dict() for c in answer.citations],
                sources=[s.as_dict() for s in all_sources],
                usage=_usage_with_tools(answer),
                prompt_version=answer.prompt_version,
                refused=answer.refused,
                model_id=answer.model_id,
            )
            auto_title(db, conversation_id=conv_uuid, question=question)
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
    enable_tools: bool = True,
    strict_mode: bool = False,
) -> Iterator[GroundedAnswerChunk]:
    """Generate a grounded answer with streaming.

    If tools are enabled, the tool loop runs first and the final prose is streamed.
    """
    if enable_tools:
        answer = ask(
            db,
            principal=principal,
            question=question,
            conversation_id=conversation_id,
            filters=filters,
            exclude_document_ids=exclude_document_ids,
            workspace_id=workspace_id,
            enable_tools=True,
            strict_mode=strict_mode,
            persist=False,
        )
        words = (answer.text or "").split()
        for i, word in enumerate(words):
            yield GroundedAnswerChunk(delta=word if i == 0 else f" {word}")
        done = GroundedAnswerChunk(
            delta="",
            done=True,
            citations=answer.citations,
            usage=answer.usage,
            refused=answer.refused,
            refusal_reason=answer.refusal_reason,
            conversation_id=answer.conversation_id,
        )
        conv_uuid = uuid.UUID(answer.conversation_id) if answer.conversation_id else None
        if conv_uuid:
            add_message(db, conversation_id=conv_uuid, role="user", content=question)
            assistant_msg = add_message(
                db,
                conversation_id=conv_uuid,
                role="assistant",
                content=answer.text,
                citations=[c.as_dict() for c in answer.citations],
                sources=[s.as_dict() for s in answer.citations],
                usage=_usage_with_tools(answer),
                prompt_version=answer.prompt_version,
                refused=answer.refused,
                model_id=answer.model_id,
            )
            auto_title(db, conversation_id=conv_uuid, question=question)
            done.conversation_id = str(conv_uuid)
            done.message_id = str(assistant_msg.id)
        yield done
        return

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
        db, principal, question, filters, exclude_document_ids, history
    )

    # Build the full prompt
    context_block = build_context_block(context_chunks, strict_mode=strict_mode)
    user_message = build_user_message(question, context_block)
    prompt = system_prompt_for(enable_tools=False, strict_mode=strict_mode)

    # Stream generation
    provider = get_llm_provider()
    accumulated_text = ""

    for chunk in provider.stream_grounded_answer(
        user_message,
        context_chunks,
        system_prompt=prompt,
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


def _usage_with_tools(answer: GroundedAnswer) -> dict | None:
    usage = answer.usage.as_dict() if answer.usage else {}
    if answer.tool_results or answer.tool_calls:
        usage["tool_trace"] = {
            "calls": [c.as_dict() for c in answer.tool_calls],
            "results": [r.as_dict() for r in answer.tool_results],
        }
    return usage or None
