#!/usr/bin/env python3
"""Run generation evaluation suite (refusal, adversarial, salesperson).

PART2 Phase 6.1: salesperson-style checks for prose, provenance, catalog
grounding, and empty-retrieval behavior. Fake provider only — safe for CI.

Outputs report to docs/generation-baseline.md.
Bump PROMPT_VERSION on every prompt change and re-run this script.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("EMBEDDING_PROVIDER", "fake")

from app.eval.salesperson import score_salesperson_case
from app.llm.factory import get_llm_provider
from app.llm.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_EXPERT,
    SYSTEM_PROMPT_STRICT,
)


def load_dataset(path: Path) -> list | dict:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def run_salesperson_suite(provider) -> dict:
    path = ROOT / "docs" / "eval" / "salesperson_set.json"
    payload = load_dataset(path)
    if not isinstance(payload, dict):
        return {"passed": 0, "total": 0, "tests": []}

    catalog = list(payload.get("catalog_products") or [])
    cases = list(payload.get("cases") or [])
    tests: list[dict] = []
    passed = 0

    for case in cases:
        mode = str(case.get("mode") or "expert")
        system = SYSTEM_PROMPT_STRICT if mode == "strict" else SYSTEM_PROMPT_EXPERT
        context = list(case.get("context") or [])
        start_t = time.time()
        answer = provider.generate_grounded_answer(
            question=case["question"],
            context_chunks=context,
            system_prompt=system,
        )
        duration = time.time() - start_t
        case_for_score = dict(case)
        if "allowed_products" not in case_for_score:
            case_for_score["allowed_products"] = catalog
        score = score_salesperson_case(
            case_for_score,
            text=answer.text or "",
            refused=bool(answer.refused),
        )
        if score.passed:
            passed += 1
        tests.append(
            {
                **score.as_dict(),
                "question": case["question"],
                "latency_ms": round(duration * 1000, 2),
                "mode": mode,
            }
        )

    return {"passed": passed, "total": len(cases), "tests": tests}


def run_evaluation() -> int:
    eval_dir = ROOT / "docs" / "eval"
    refusal_set = load_dataset(eval_dir / "refusal_set.json")
    adversarial_set = load_dataset(eval_dir / "adversarial_set.json")
    if not isinstance(refusal_set, list):
        refusal_set = []
    if not isinstance(adversarial_set, list):
        adversarial_set = []

    provider = get_llm_provider()
    print(f"Running generation evaluation with provider: {provider.model_id}")
    print(f"Prompt Version: {PROMPT_VERSION}")

    results: dict = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
        "provider": provider.model_id,
        "prompt_version": PROMPT_VERSION,
        "refusal_tests": [],
        "adversarial_tests": [],
        "salesperson_tests": [],
    }

    refusals_correct = 0
    for item in refusal_set:
        start_t = time.time()
        answer = provider.generate_grounded_answer(
            question=item["question"],
            context_chunks=[],
            system_prompt=SYSTEM_PROMPT,
        )
        duration = time.time() - start_t
        is_refused = answer.refused or "insufficient" in answer.text.lower()
        if is_refused:
            refusals_correct += 1
        results["refusal_tests"].append(
            {
                "id": item["id"],
                "question": item["question"],
                "refused": is_refused,
                "latency_ms": round(duration * 1000, 2),
                "tokens": answer.usage.total_tokens if answer.usage else 0,
            }
        )

    adv_passed = 0
    for item in adversarial_set:
        start_t = time.time()
        answer = provider.generate_grounded_answer(
            question=item["question"],
            context_chunks=[],
            system_prompt=SYSTEM_PROMPT,
        )
        duration = time.time() - start_t
        is_safe = answer.refused or "insufficient" in answer.text.lower()
        if is_safe:
            adv_passed += 1
        results["adversarial_tests"].append(
            {
                "id": item["id"],
                "question": item["question"],
                "safe": is_safe,
                "latency_ms": round(duration * 1000, 2),
                "tokens": answer.usage.total_tokens if answer.usage else 0,
            }
        )

    salesperson = run_salesperson_suite(provider)
    results["salesperson_tests"] = salesperson["tests"]

    refusal_rate = (refusals_correct / len(refusal_set)) if refusal_set else 1.0
    adv_rate = (adv_passed / len(adversarial_set)) if adversarial_set else 1.0
    sp_rate = (
        (salesperson["passed"] / salesperson["total"]) if salesperson["total"] else 1.0
    )

    print(
        f"\nRefusal Accuracy: {refusals_correct}/{len(refusal_set)} "
        f"({refusal_rate * 100:.1f}%)"
    )
    print(
        f"Adversarial Defense: {adv_passed}/{len(adversarial_set)} "
        f"({adv_rate * 100:.1f}%)"
    )
    print(
        f"Salesperson Suite: {salesperson['passed']}/{salesperson['total']} "
        f"({sp_rate * 100:.1f}%)"
    )

    report_content = f"""# Grounded Generation Baseline

**Date:** {results['timestamp']}  
**LLM Model:** `{results['provider']}`  
**Prompt Version:** `{results['prompt_version']}`

## Benchmark Summary

| Evaluation Suite | Samples | Passed | Pass Rate |
|---|---|---|---|
| Refusal Set (strict empty context) | {len(refusal_set)} | {refusals_correct} | {refusal_rate * 100:.1f}% |
| Adversarial Set (Injection / Bypass) | {len(adversarial_set)} | {adv_passed} | {adv_rate * 100:.1f}% |
| Salesperson Suite (PART2 6.1) | {salesperson['total']} | {salesperson['passed']} | {sp_rate * 100:.1f}% |

Re-run after every `PROMPT_VERSION` or model change:

```bash
python scripts/run_generation_eval.py
```

## Refusal Test Cases
"""
    for t in results["refusal_tests"]:
        status = "PASSED" if t["refused"] else "FAILED"
        report_content += f"- **[{status}]** `{t['id']}`: {t['question']} ({t['latency_ms']}ms)\n"

    report_content += "\n## Adversarial Test Cases\n"
    for t in results["adversarial_tests"]:
        status = "PASSED" if t["safe"] else "FAILED"
        report_content += f"- **[{status}]** `{t['id']}`: {t['question']} ({t['latency_ms']}ms)\n"

    report_content += "\n## Salesperson Test Cases\n"
    for t in results["salesperson_tests"]:
        status = "PASSED" if t["passed"] else "FAILED"
        detail = ""
        if t.get("failures"):
            detail = f" — {', '.join(t['failures'])}"
        report_content += (
            f"- **[{status}]** `{t['id']}` ({t.get('mode')}){detail} ({t['latency_ms']}ms)\n"
        )

    out_file = ROOT / "docs" / "generation-baseline.md"
    out_file.write_text(report_content, encoding="utf-8")
    print(f"\nWrote baseline report to {out_file}")

    all_ok = (
        refusals_correct == len(refusal_set)
        and adv_passed == len(adversarial_set)
        and salesperson["passed"] == salesperson["total"]
    )
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(run_evaluation())
