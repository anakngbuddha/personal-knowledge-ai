"""RAG orchestration: retrieval -> injection containment -> LLM -> cited answer.

This is the heart of Phase 3. The service:
1. Receives a question + optional conversation context + optional filters
2. Calls permission-aware search from the retrieval module
3. Wraps each search hit through wrap_untrusted() (injection containment)
4. Builds the prompt using versioned templates from prompts.py
5. Calls the LLM provider (sync or streaming)
6. Maps citations back to SourceMetadata with provenance, and scores how well each
   cited passage supports the claim it is attached to (audit finding 5)
7. Records usage for budget tracking

Strict (sources-only) is the default answer mode (GENERATION_STRICT_DEFAULT).

Tool access is opt-in via enable_tools. Document content reaches the LLM only
through wrap_untrusted(), and the system prompt states that document content
can never issue instructions.

2.3 adds one step between search and prompt: when the matched chunk is a child of a
larger section, the parent passage is prompted instead of the child. The citation still
points at the child, so provenance does not get vaguer as context gets wider.

3.5 adds another: when the question names a product the map knows, the accepted
relationships around it are stated in the prompt, and the best passage for each
neighbour is retrieved as well, so the model can cite the pairing rather than assert it.
Each neighbour costs a full hybrid search, so the number of neighbour searches and
their total time are capped (audit finding 9).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import DocumentChunk
from app.documents.injection import wrap_untrusted
from app.generation.claim_support import (
    annotate_citations,
    sanitize_general_guidance,
    weak_citation_count,
)
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
    build_context_block,
    build_relationships_block,
    build_user_message,
    system_prompt_for,
)
from app.retrieval import graph_context as map_lookup
from app.retrieval.rewrite import expand_queries, keyword_overlap_score, rewrite_query
from app.retrieval.search import search as run_search
from app.retrieval.web import gather_web_fallback
from app.retrieval.spec import RetrievalFilters
from app.security.labels import SourceType
from app.security.principal import Principal

logger = get_logger(__name__)


def resolve_strict_mode(strict_mode: bool | None) -> bool:
    if strict_mode is None:
        return bool(getattr(settings, "generation_strict_default", True))
    return bool(strict_mode)


@dataclass
class PreparedContext:
    chunks: list[dict]
    sources: list[SourceMetadata]
    relationships_block: str
    needs_web: bool
    search_query: str
    web_note: str | None = None
    web_sources: list[SourceMetadata] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)


def hits_are_weak(hits: list, query: str) -> bool:
    """True when local passages do not cover the question."""
    if not hits:
        return True
    best = max(keyword_overlap_score(query, getattr(hit, "text", "") or "") for hit in hits)
    return best < settings.web_fallback_min_score


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
        exclude_source_types=[SourceType.RFP_INTAKE],
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


def _expand_neighbours(
    db: Session,
    principal: Principal,
    names: list[str],
    hits: list,
    retrieval_filters: RetrievalFilters,
    timings: dict[str, float],
) -> None:
    """Bring each neighbour's best passage along, within a count and time budget."""
    known = {hit.chunk_id for hit in hits}
    per_neighbour = max(1, settings.graph_expansion_chunks_per_neighbour)
    max_searches = max(0, int(getattr(settings, "graph_expansion_max_neighbour_searches", 3)))
    budget_ms = float(getattr(settings, "graph_expansion_time_budget_ms", 0) or 0)
    started = time.perf_counter()
    searched = 0
    for name in names:
        if searched >= max_searches:
            break
        elapsed = (time.perf_counter() - started) * 1000.0
        if budget_ms and elapsed >= budget_ms:
            logger.info("graph expansion stopped at time budget (%.0f ms)", elapsed)
            break
        searched += 1
        try:
            extra = run_search(
                db,
                principal=principal,
                query=name,
                filters=retrieval_filters,
                mode="hybrid",
                top_k=per_neighbour,
                candidate_k=settings.generation_search_candidate_k,
            )
        except Exception:  # noqa: BLE001 - a neighbour is a bonus, never a blocker
            logger.debug("neighbour lookup failed for %s", name, exc_info=True)
            continue
        for hit in extra.hits:
            if hit.chunk_id in known:
                continue
            known.add(hit.chunk_id)
            hits.append(hit)
    timings["graph_expansion_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
    timings["graph_neighbour_searches"] = float(searched)
    logger.info(
        "graph expansion searched %d of %d neighbour(s) in %.1f ms",
        searched,
        len(names),
        timings["graph_expansion_ms"],
    )


def _prepare_context(
    db: Session,
    principal: Principal,
    question: str,
    filters: dict | None = None,
    exclude_document_ids: list[str] | None = None,
    history: list[dict] | None = None,
    workspace_id: uuid.UUID | None = None,
) -> PreparedContext:
    """Retrieve and prepare context chunks for the LLM.

    Rewrites follow-ups using conversation history (deterministic, no LLM call),
    expands broad questions into a few sub-queries, optionally reranks the fused hits,
    widens each surviving hit to its parent section, and (3.5) brings in what the
    product map knows about the products the question names.
    """
    timings: dict[str, float] = {}
    started = time.perf_counter()
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
    mark = time.perf_counter()
    for query in queries:
        search_result = run_search(
            db,
            principal=principal,
            query=query,
            filters=retrieval_filters,
            mode="hybrid",
            top_k=candidate_k,
            candidate_k=settings.generation_search_candidate_k,
        )
        for hit in search_result.hits:
            previous = merged.get(hit.chunk_id)
            score = float(getattr(hit, "rrf_score", 0) or 0)
            if previous is None or score > float(getattr(previous, "rrf_score", 0) or 0):
                merged[hit.chunk_id] = hit
    timings["search_ms"] = round((time.perf_counter() - mark) * 1000.0, 1)
    timings["search_queries"] = float(len(queries))

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

    # 3.5 The map. Its sentences go in the prompt; its neighbours bring their own best
    # passage so a pairing can be cited instead of asserted.
    mark = time.perf_counter()
    graph = map_lookup.expand(db, workspace_id=workspace_id, question=question)
    timings["graph_lookup_ms"] = round((time.perf_counter() - mark) * 1000.0, 1)
    relationships_block = build_relationships_block(graph.as_lines())
    covered = not hits_are_weak(hits, search_query)
    if graph.neighbour_names and not covered:
        _expand_neighbours(db, principal, list(graph.neighbour_names), hits, retrieval_filters, timings)

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

    timings["prepare_total_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
    logger.info("prepare_context timings %s", timings)

    return PreparedContext(
        chunks=context_chunks,
        sources=source_metadata,
        relationships_block=relationships_block,
        needs_web=hits_are_weak(hits, search_query),
        search_query=search_query,
        timings_ms=timings,
    )


def _attach_web(prepared: PreparedContext, web_search: bool | None = None) -> PreparedContext:
    """Fetch web passages and append them as fenced, labeled sources.

    If web_search is False, web search is disabled.
    If web_search is True, web search is forced.
    If web_search is None (default), web search runs automatically when context needs web.
    """
    should_search = (web_search is True) or (web_search is None and prepared.needs_web)
    if not should_search:
        return prepared
    fallback = gather_web_fallback(prepared.search_query)
    prepared.web_note = fallback.note
    start = len(prepared.chunks)
    for offset, passage in enumerate(fallback.passages, start=1):
        index = start + offset
        citation = passage.title or passage.url
        fenced = wrap_untrusted(passage.text, source=citation)
        metadata = {
            "chunk_id": f"web-{offset}",
            "document_id": "web",
            "document_title": passage.title,
            "page_number": None,
            "slide_number": None,
            "sheet_name": None,
            "cell_range": None,
            "heading_path": [],
            "vendor": None,
            "ownership": None,
            "approval_state": None,
            "sensitivity": None,
            "valid_until": None,
            "is_stale": False,
            "source_url": passage.url,
            "origin": "web",
        }
        prepared.chunks.append(
            {
                "index": index,
                "fenced_text": fenced,
                "citation": citation,
                "metadata": metadata,
            }
        )
        source = SourceMetadata(
            chunk_id=metadata["chunk_id"],
            document_id="web",
            document_title=passage.title,
            citation=citation,
            source_url=passage.url,
            origin="web",
        )
        prepared.sources.append(source)
        prepared.web_sources.append(source)
    return prepared


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
    strict_mode: bool | None = None,
    persist: bool = True,
    notebook_id: uuid.UUID | None = None,
    web_search: bool | None = None,
    attachment_document_ids: list[uuid.UUID] | None = None,
) -> GroundedAnswer:
    """Generate a grounded answer (synchronous).

    The full pipeline:
    1. Rate limit check
    2. Token budget check
    3. Retrieve permission-aware context
    4. Build prompt with injection containment
    5. Generate answer (optional single-turn tool loop)
    6. Score citation support, record usage, persist message
    """
    strict_mode = resolve_strict_mode(strict_mode)

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
            if conv.notebook_id != notebook_id:
                raise ValueError(f"Conversation {conversation_id} not found")
        history = get_history(db, conversation_id=conv_uuid)
    elif workspace_id:
        conv = create_conversation(
            db,
            workspace_id=workspace_id,
            title=question[:200],
            notebook_id=notebook_id,
            org_id=principal.org_id,
        )
        conv_uuid = conv.id

    # Retrieve and prepare context
    prepared = _attach_web(
        _prepare_context(
            db,
            principal,
            question,
            filters,
            exclude_document_ids,
            history,
            workspace_id=workspace_id,
        ),
        web_search=web_search,
    )
    context_chunks = prepared.chunks
    all_sources = prepared.sources
    relationships_block = prepared.relationships_block

    # Build the full prompt
    context_block = build_context_block(context_chunks, strict_mode=strict_mode)
    user_message = build_user_message(question, context_block, relationships_block)
    prompt = system_prompt_for(enable_tools=enable_tools, strict_mode=strict_mode)

    # Generate
    provider = get_llm_provider()
    use_tools = enable_tools
    if use_tools:
        if workspace_id is None:
            raise ValueError("enable_tools requires a workspace")
        from app.tools.loop import run_tool_loop
        from app.tools.registry import ToolContext, default_definitions, execute_tool

        ctx = ToolContext(db=db, principal=principal, workspace_id=workspace_id,
                          notebook_id=notebook_id, conversation_id=conv_uuid,
                          attachment_document_ids=attachment_document_ids)

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

    # Claim-level support and the unsourced-section rule.
    answer.text = sanitize_general_guidance(answer.text or "")
    answer.citations = annotate_citations(answer.text, list(answer.citations), context_chunks)

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

    answer.web_note = prepared.web_note
    answer.web_sources = list(prepared.web_sources)

    logger.info(
        "ask model=%s strict=%s refused=%s citations=%d weak=%d prompt_v=%s conv=%s",
        answer.model_id,
        strict_mode,
        answer.refused,
        len(answer.citations),
        weak_citation_count(answer.citations),
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
    strict_mode: bool | None = None,
    notebook_id: uuid.UUID | None = None,
    web_search: bool | None = None,
    attachment_document_ids: list[uuid.UUID] | None = None,
) -> Iterator[GroundedAnswerChunk]:
    """Generate a grounded answer with streaming.

    Tool-enabled answers are NOT streamed (audit finding 10): the tool loop has to
    finish before there is final prose, so the endpoint says so with a status chunk and
    sends the answer in one piece instead of replaying it word by word.
    """
    strict_mode = resolve_strict_mode(strict_mode)
    if enable_tools:
        yield GroundedAnswerChunk(delta="", status="running tools; this answer is not streamed")
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
            notebook_id=notebook_id,
            web_search=web_search,
            attachment_document_ids=attachment_document_ids,
        )
        if answer.text:
            yield GroundedAnswerChunk(delta=answer.text)
        done = GroundedAnswerChunk(
            delta="",
            done=True,
            citations=answer.citations,
            usage=answer.usage,
            refused=answer.refused,
            refusal_reason=answer.refusal_reason,
            conversation_id=answer.conversation_id,
            web_note=answer.web_note,
            web_sources=list(answer.web_sources),
            tool_calls=list(answer.tool_calls),
            tool_results=list(answer.tool_results),
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
            if conv.notebook_id != notebook_id:
                raise ValueError(f"Conversation {conversation_id} not found")
        history = get_history(db, conversation_id=conv_uuid)
    elif workspace_id:
        conv = create_conversation(
            db,
            workspace_id=workspace_id,
            title=question[:200],
            notebook_id=notebook_id,
            org_id=principal.org_id,
        )
        conv_uuid = conv.id

    prepared = _prepare_context(
        db,
        principal,
        question,
        filters,
        exclude_document_ids,
        history,
        workspace_id=workspace_id,
    )
    should_search = (web_search is True) or (web_search is None and prepared.needs_web)
    if should_search:
        yield GroundedAnswerChunk(delta="", status="searching the web")
        prepared = _attach_web(prepared, web_search=web_search)
    context_chunks = prepared.chunks
    all_sources = prepared.sources
    relationships_block = prepared.relationships_block

    # Build the full prompt
    context_block = build_context_block(context_chunks, strict_mode=strict_mode)
    user_message = build_user_message(question, context_block, relationships_block)
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
        if chunk.done:
            persisted_text = sanitize_general_guidance(accumulated_text)
            chunk.citations = annotate_citations(persisted_text, list(chunk.citations), context_chunks)
            chunk.web_note = prepared.web_note
            chunk.web_sources = list(prepared.web_sources)
            if chunk.usage:
                record_token_usage(
                    db,
                    principal.org_id,
                    chunk.usage.prompt_tokens,
                    chunk.usage.completion_tokens,
                )
            if conv_uuid:
                add_message(db, conversation_id=conv_uuid, role="user", content=question)
                assistant_msg = add_message(
                    db,
                    conversation_id=conv_uuid,
                    role="assistant",
                    content=persisted_text,
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
                "ask_stream done model=%s strict=%s refused=%s citations=%d weak=%d conv=%s",
                provider.model_id,
                strict_mode,
                chunk.refused,
                len(chunk.citations),
                weak_citation_count(chunk.citations),
                conv_uuid,
            )
        yield chunk


def _usage_with_tools(answer: GroundedAnswer) -> dict | None:
    usage = answer.usage.as_dict() if answer.usage else {}
    if answer.tool_results or answer.tool_calls:
        usage["tool_trace"] = {
            "calls": [c.as_dict() for c in answer.tool_calls],
            "results": [r.as_dict() for r in answer.tool_results],
        }
    return usage or None
