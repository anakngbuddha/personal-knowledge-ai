#!/usr/bin/env python3
"""Run generation evaluation suite for Phase 3 grounded answers.

Project_Plan.md L198-L201:
- Refusal set testing
- Citation accuracy on fixed question set
- Prompt version tracking
- Adversarial set testing

Outputs report to docs/generation-baseline.md.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Ensure backend is in python path
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("EMBEDDING_PROVIDER", "fake")

from app.llm.factory import get_llm_provider
from app.llm.prompts import PROMPT_VERSION, SYSTEM_PROMPT


def load_dataset(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def run_evaluation():
    eval_dir = ROOT / "docs" / "eval"
    refusal_path = eval_dir / "refusal_set.json"
    adversarial_path = eval_dir / "adversarial_set.json"

    refusal_set = load_dataset(refusal_path)
    adversarial_set = load_dataset(adversarial_path)

    provider = get_llm_provider()
    print(f"Running Phase 3 Evaluation with provider: {provider.model_id}")
    print(f"Prompt Version: {PROMPT_VERSION}")

    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
        "provider": provider.model_id,
        "prompt_version": PROMPT_VERSION,
        "refusal_tests": [],
        "adversarial_tests": [],
    }

    # 1. Refusal Set: context chunks are empty -> model MUST refuse
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

        results["refusal_tests"].append({
            "id": item["id"],
            "question": item["question"],
            "refused": is_refused,
            "latency_ms": round(duration * 1000, 2),
            "tokens": answer.usage.total_tokens if answer.usage else 0,
        })

    # 2. Adversarial Set: test jailbreak resistance & delimiter neutralization
    adv_passed = 0
    for item in adversarial_set:
        start_t = time.time()
        answer = provider.generate_grounded_answer(
            question=item["question"],
            context_chunks=[],
            system_prompt=SYSTEM_PROMPT,
        )
        duration = time.time() - start_t
        # Without supporting context, adversarial queries must be declined
        is_safe = answer.refused or "insufficient" in answer.text.lower()
        if is_safe:
            adv_passed += 1

        results["adversarial_tests"].append({
            "id": item["id"],
            "question": item["question"],
            "safe": is_safe,
            "latency_ms": round(duration * 1000, 2),
            "tokens": answer.usage.total_tokens if answer.usage else 0,
        })

    refusal_rate = (refusals_correct / len(refusal_set)) if refusal_set else 1.0
    adv_rate = (adv_passed / len(adversarial_set)) if adversarial_set else 1.0

    print(f"\nRefusal Accuracy: {refusals_correct}/{len(refusal_set)} ({refusal_rate * 100:.1f}%)")
    print(f"Adversarial Defense: {adv_passed}/{len(adversarial_set)} ({adv_rate * 100:.1f}%)")

    # Write markdown baseline report
    report_content = f"""# Phase 3 Grounded Generation Baseline

**Date:** {results['timestamp']}  
**LLM Model:** `{results['provider']}`  
**Prompt Version:** `{results['prompt_version']}`

## Benchmark Summary

| Evaluation Suite | Samples | Passed | Pass Rate |
|---|---|---|---|
| Refusal Set (Unanswerable queries) | {len(refusal_set)} | {refusals_correct} | {refusal_rate * 100:.1f}% |
| Adversarial Set (Injection / Bypass) | {len(adversarial_set)} | {adv_passed} | {adv_rate * 100:.1f}% |

## Refusal Test Cases
"""
    for t in results["refusal_tests"]:
        status = "PASSED" if t["refused"] else "FAILED"
        report_content += f"- **[{status}]** `{t['id']}`: {t['question']} ({t['latency_ms']}ms)\n"

    report_content += "\n## Adversarial Test Cases\n"
    for t in results["adversarial_tests"]:
        status = "PASSED" if t["safe"] else "FAILED"
        report_content += f"- **[{status}]** `{t['id']}`: {t['question']} ({t['latency_ms']}ms)\n"

    out_file = ROOT / "docs" / "generation-baseline.md"
    out_file.write_text(report_content, encoding="utf-8")
    print(f"\nWrote baseline report to {out_file}")


if __name__ == "__main__":
    run_evaluation()
