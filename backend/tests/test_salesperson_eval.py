"""PART2 6.1 — salesperson generation eval gate (fake provider)."""

from __future__ import annotations

import json
from pathlib import Path

from app.eval.salesperson import score_prose, score_salesperson_case
from app.llm.fake import FakeLLMProvider
from app.llm.prompts import SYSTEM_PROMPT_EXPERT, SYSTEM_PROMPT_STRICT

ROOT = Path(__file__).resolve().parents[2]
SALESPERSON_SET = ROOT / "docs" / "eval" / "salesperson_set.json"


def _load_set() -> dict:
    return json.loads(SALESPERSON_SET.read_text(encoding="utf-8"))


def test_salesperson_set_has_reference_and_ten_plus_cases():
    payload = _load_set()
    cases = payload["cases"]
    assert len(cases) >= 11
    assert any(c["id"] == "sp-ref-e" for c in cases)
    assert "catalog_products" in payload
    assert len(payload["catalog_products"]) >= 4


def test_salesperson_suite_passes_with_fake_provider():
    payload = _load_set()
    catalog = list(payload["catalog_products"])
    provider = FakeLLMProvider()
    failures: list[str] = []

    for case in payload["cases"]:
        mode = case.get("mode") or "expert"
        system = SYSTEM_PROMPT_STRICT if mode == "strict" else SYSTEM_PROMPT_EXPERT
        answer = provider.generate_grounded_answer(
            case["question"],
            list(case.get("context") or []),
            system_prompt=system,
        )
        case_for_score = dict(case)
        if "allowed_products" not in case_for_score:
            case_for_score["allowed_products"] = catalog
        score = score_salesperson_case(
            case_for_score,
            text=answer.text or "",
            refused=bool(answer.refused),
        )
        if not score.passed:
            failures.append(f"{score.case_id}: {score.failures}")

    assert not failures, failures


def test_prose_scorer_flags_jargon():
    assert score_prose("This answer mentions a chunk and ingest pipeline.") == [
        "jargon: chunk",
        "jargon: ingest",
    ]


def test_empty_expert_vs_strict_behavior():
    provider = FakeLLMProvider()
    expert = provider.generate_grounded_answer(
        "What is QuantumBook pricing?",
        [],
        system_prompt=SYSTEM_PROMPT_EXPERT,
    )
    strict = provider.generate_grounded_answer(
        "What is QuantumBook pricing?",
        [],
        system_prompt=SYSTEM_PROMPT_STRICT,
    )
    expert_score = score_salesperson_case(
        {
            "id": "e",
            "checks": {"prose": True, "empty_retrieval": "expert"},
            "allowed_products": [],
        },
        text=expert.text,
        refused=expert.refused,
    )
    strict_score = score_salesperson_case(
        {
            "id": "s",
            "checks": {"prose": True, "empty_retrieval": "strict"},
        },
        text=strict.text,
        refused=strict.refused,
    )
    assert expert_score.passed
    assert strict_score.passed
