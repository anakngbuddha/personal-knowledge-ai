"""Claim-level citation support and the general-guidance rule (audit finding 5)."""

from __future__ import annotations

from app.generation.claim_support import (
    GENERAL_GUIDANCE_HEADING,
    annotate_citations,
    citation_support,
    sanitize_general_guidance,
)
from app.llm.base import SourceMetadata
from app.llm.prompts import SYSTEM_PROMPT_EXPERT, system_prompt_for

CHUNKS = [
    {
        "index": 1,
        "fenced_text": "The Acme Router X200 supports SAML 2.0 single sign-on and OIDC.",
        "citation": "X200 datasheet p. 2",
        "metadata": {"chunk_id": "c1"},
    },
    {
        "index": 2,
        "fenced_text": "Warranty coverage is three years for hardware defects.",
        "citation": "Warranty p. 1",
        "metadata": {"chunk_id": "c2"},
    },
]


def test_supported_claim_scores_high_and_mismatched_claim_scores_low():
    text = (
        "The X200 supports SAML 2.0 single sign-on [source_1].\n\n"
        "The X200 ships with a lifetime 24/7 onsite support contract [source_2]."
    )
    scores = citation_support(text, CHUNKS)
    assert scores[1] >= 0.6
    assert scores[2] < 0.25


def test_annotate_marks_weak_citations():
    text = "The X200 ships with a lifetime onsite support contract [source_2]."
    cites = [SourceMetadata(chunk_id="c2", document_id="d2", document_title="W", citation="Warranty p. 1")]
    out = annotate_citations(text, cites, CHUNKS)
    assert out[0].weakly_supported is True
    assert out[0].support_score is not None
    assert out[0].as_dict()["weakly_supported"] is True


def test_general_guidance_section_is_never_cited():
    text = f"From your documents: SSO is supported [source_1].\n\n{GENERAL_GUIDANCE_HEADING}\nMost routers also do X [source_2]."
    cleaned = sanitize_general_guidance(text)
    head, tail = cleaned.split(GENERAL_GUIDANCE_HEADING)
    assert "[source_1]" in head
    assert "[source_" not in tail
    # and it is excluded from support scoring
    assert 2 not in citation_support(text, CHUNKS)


def test_strict_is_the_default_prompt_and_expert_confines_general_knowledge():
    assert system_prompt_for(enable_tools=False).startswith("You write for a salesperson. Answer using ONLY")
    assert GENERAL_GUIDANCE_HEADING in SYSTEM_PROMPT_EXPERT
    assert "Never refuse to answer simply because internal retrieval is empty" not in SYSTEM_PROMPT_EXPERT


def test_api_and_service_default_to_strict():
    import inspect

    from app.generation import service
    from app.generation.schemas import AskIn

    assert AskIn(question="q").strict_mode is True
    assert service.resolve_strict_mode(None) is True
    assert inspect.signature(service.ask).parameters["strict_mode"].default is None
