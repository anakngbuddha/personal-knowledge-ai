"""Core generation unit tests for Phase 3.

Covers:
- GroundedAnswer and SourceMetadata representation
- FakeLLMProvider sync and streaming execution
- Refusal triggers on missing/empty context
- Provenance metadata propagation
- Provider factory resolution
- Retrieval filter mapping
"""

import uuid
from app.documents.injection import wrap_untrusted
from app.generation.service import _build_retrieval_filters
from app.llm.base import (
    GroundedAnswer,
    GroundedAnswerChunk,
    SourceMetadata,
    TokenUsage,
)
from app.llm.factory import get_llm_provider
from app.llm.fake import FakeLLMProvider
from app.llm.prompts import PROMPT_VERSION, SYSTEM_PROMPT


def test_source_metadata_serialization():
    meta = SourceMetadata(
        chunk_id="chk_1",
        document_id="doc_1",
        document_title="Architecture Overview",
        citation="Doc 1 p. 5",
        page_number=5,
        vendor="Acme",
        ownership="internal",
        approval_state="approved",
        sensitivity="internal",
        valid_until="2027-01-01",
        is_stale=False,
    )
    d = meta.as_dict()
    assert d["chunk_id"] == "chk_1"
    assert d["document_id"] == "doc_1"
    assert d["document_title"] == "Architecture Overview"
    assert d["citation"] == "Doc 1 p. 5"
    assert d["page_number"] == 5
    assert d["vendor"] == "Acme"
    assert d["approval_state"] == "approved"
    assert d["is_stale"] is False


def test_grounded_answer_serialization():
    meta = SourceMetadata(
        chunk_id="chk_1",
        document_id="doc_1",
        document_title="Test",
        citation="Doc 1",
    )
    usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    answer = GroundedAnswer(
        text="This is an answer [source_1].",
        citations=[meta],
        model_id="fake-llm-v1",
        prompt_version=PROMPT_VERSION,
        refused=False,
        usage=usage,
    )
    d = answer.as_dict()
    assert d["text"] == "This is an answer [source_1]."
    assert len(d["citations"]) == 1
    assert d["model_id"] == "fake-llm-v1"
    assert d["prompt_version"] == PROMPT_VERSION
    assert d["refused"] is False
    assert d["usage"]["total_tokens"] == 150


def test_fake_llm_provider_generation():
    provider = FakeLLMProvider()
    assert provider.model_id == "fake-llm-v1"

    chunk_meta = {
        "chunk_id": "c_100",
        "document_id": "d_200",
        "document_title": "Product Guide",
        "page_number": 3,
        "vendor": "Acme",
        "approval_state": "approved",
    }
    context_chunks = [
        {
            "index": 1,
            "fenced_text": "Product supports SAML 2.0 and OIDC.",
            "citation": "Product Guide p. 3",
            "metadata": chunk_meta,
        }
    ]

    answer = provider.generate_grounded_answer(
        question="What SSO protocols are supported?",
        context_chunks=context_chunks,
        system_prompt=SYSTEM_PROMPT,
    )

    assert not answer.refused
    assert "[source_1]" in answer.text
    assert len(answer.citations) == 1
    assert answer.citations[0].chunk_id == "c_100"
    assert answer.citations[0].citation == "Product Guide p. 3"
    assert answer.citations[0].vendor == "Acme"
    assert answer.usage is not None
    assert answer.usage.total_tokens > 0


def test_fake_llm_provider_refusal():
    provider = FakeLLMProvider()
    answer = provider.generate_grounded_answer(
        question="What is the price of product X?",
        context_chunks=[],
        system_prompt=SYSTEM_PROMPT,
    )
    assert answer.refused is True
    assert answer.refusal_reason == "insufficient_context"
    assert "do not contain sufficient information" in answer.text
    assert answer.citations == []


def test_fake_llm_provider_streaming():
    provider = FakeLLMProvider()
    context_chunks = [
        {
            "index": 1,
            "fenced_text": "Sample text",
            "citation": "Guide p. 1",
            "metadata": {"chunk_id": "chk_99"},
        }
    ]

    chunks = list(
        provider.stream_grounded_answer(
            question="Tell me about sample",
            context_chunks=context_chunks,
            system_prompt=SYSTEM_PROMPT,
        )
    )

    assert len(chunks) >= 2
    # Intermediate chunks have deltas
    text = "".join(c.delta for c in chunks)
    assert "[source_1]" in text

    # Final chunk has done=True, citations, and usage
    final_chunk = chunks[-1]
    assert final_chunk.done is True
    assert len(final_chunk.citations) == 1
    assert final_chunk.citations[0].chunk_id == "chk_99"
    assert final_chunk.usage is not None


def test_factory_returns_fake_provider():
    provider = get_llm_provider()
    assert isinstance(provider, FakeLLMProvider)


def test_build_retrieval_filters():
    rf = _build_retrieval_filters(
        {
            "products": ["Widget"],
            "vendor": "VendorA",
            "ownership": "internal",
            "account_ref": "ACC-123",
            "approved_only": True,
            "exclude_injection_flagged": True,
            "document_ids": ["doc-1"],
            "exclude_document_ids": ["doc-2"],
        }
    )
    assert rf.products == ["Widget"]
    assert rf.vendor == "VendorA"
    assert rf.ownership == "internal"
    assert rf.account_ref == "ACC-123"
    assert rf.approved_only is True
    assert rf.exclude_injection_flagged is True
    assert rf.document_ids == ["doc-1"]
    assert rf.exclude_document_ids == ["doc-2"]
    assert rf.exclude_source_types == ["rfp_intake"]
    assert all(predicate.field != "source_type" for predicate in rf.to_predicates())
    unscoped = _build_retrieval_filters({})
    assert any(
        predicate.field == "source_type" and "rfp_intake" in predicate.value
        for predicate in unscoped.to_predicates()
    )


def test_grounded_answer_includes_conversation_and_message_ids():
    answer = GroundedAnswer(
        text="Answer text",
        citations=[],
        model_id="fake-llm-v1",
        prompt_version=PROMPT_VERSION,
        conversation_id="conv-123",
        message_id="msg-456",
    )
    d = answer.as_dict()
    assert d["conversation_id"] == "conv-123"
    assert d["message_id"] == "msg-456"
