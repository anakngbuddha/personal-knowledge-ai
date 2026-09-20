"""Catalog-agnostic golden RFP scorer.

Scores an approved RFP payload against a catalog snapshot. The catalog source
(seed placeholder vs human-approved real graph) does not change these rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CatalogView:
    product_names: set[str]
    capability_names: set[str]
    products: dict[str, dict[str, Any]]  # lowercased name -> {vendor, deployment_model, slug}
    conflict_pairs: set[frozenset[str]]


@dataclass
class ScoreResult:
    scenario_id: str
    passed: bool
    coverage: float
    hallucinated: list[str] = field(default_factory=list)
    ungrounded: list[str] = field(default_factory=list)
    bundle_conflicts: list[list[str]] = field(default_factory=list)
    constraint_violations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "passed": self.passed,
            "coverage": round(self.coverage, 3),
            "hallucinated": self.hallucinated,
            "ungrounded": self.ungrounded,
            "bundle_conflicts": self.bundle_conflicts,
            "constraint_violations": self.constraint_violations,
            "notes": self.notes,
        }


def score_scenario(
    scenario: dict[str, Any],
    answers: list[dict[str, Any]],
    catalog: CatalogView,
) -> ScoreResult:
    expected = scenario.get("expected") or {}
    requirements = scenario.get("requirements") or []
    min_coverage = float(expected.get("min_coverage", 0.9))
    must_cite = bool(expected.get("must_cite", True))
    coverage = len(answers) / max(len(requirements), 1)

    catalog_lookup = {name.lower() for name in catalog.product_names}
    cap_lookup = {name.lower() for name in catalog.capability_names}

    hallucinated: list[str] = []
    for answer in answers:
        for name in answer.get("products") or []:
            if str(name).lower() not in catalog_lookup:
                hallucinated.append(str(name))
        for cap in answer.get("candidate_capabilities") or []:
            cap_name = cap.get("name") if isinstance(cap, dict) else cap
            if cap_name and str(cap_name).lower() not in cap_lookup:
                hallucinated.append(str(cap_name))

    ungrounded: list[str] = []
    if must_cite:
        for answer in answers:
            status = answer.get("status")
            if status in {"Compliant", "Partially"} and not (answer.get("citations") or []):
                ungrounded.append(str(answer.get("id") or answer.get("text") or ""))

    compliant_products: list[str] = []
    for answer in answers:
        if answer.get("status") == "Compliant":
            compliant_products.extend(str(n) for n in (answer.get("products") or []))

    bundle_conflicts: list[list[str]] = []
    if "conflicts_with" in (expected.get("forbidden_relations") or ["conflicts_with"]):
        seen: set[frozenset[str]] = set()
        for i, left in enumerate(compliant_products):
            for right in compliant_products[i + 1 :]:
                pair = frozenset({left, right})
                if left == right or pair in seen:
                    continue
                if pair in catalog.conflict_pairs:
                    seen.add(pair)
                    bundle_conflicts.append(sorted(pair))

    constraints = scenario.get("constraints") or {}
    forbidden_vendors = {v.lower() for v in constraints.get("forbidden_vendors") or []}
    on_prem_only = bool(constraints.get("on_prem_only"))
    violations: list[str] = []
    for answer in answers:
        if answer.get("status") != "Compliant":
            continue
        for name in answer.get("products") or []:
            meta = catalog.products.get(str(name).lower(), {})
            vendor = str(meta.get("vendor") or "").lower()
            deployment = str(meta.get("deployment_model") or "").lower()
            if vendor and vendor in forbidden_vendors:
                violations.append(f"{name} vendor {meta.get('vendor')} is forbidden")
            if on_prem_only and deployment == "cloud":
                violations.append(f"{name} is cloud-only under an on-prem constraint")

    for name in expected.get("forbidden_products") or []:
        if any(str(name).lower() == p.lower() for p in compliant_products):
            violations.append(f"forbidden product marked Compliant: {name}")

    notes: list[str] = []
    if coverage < min_coverage:
        notes.append(f"coverage {coverage:.2f} < {min_coverage:.2f}")

    passed = (
        coverage >= min_coverage
        and not hallucinated
        and not ungrounded
        and not bundle_conflicts
        and not violations
    )
    return ScoreResult(
        scenario_id=str(scenario.get("id") or ""),
        passed=passed,
        coverage=coverage,
        hallucinated=hallucinated,
        ungrounded=ungrounded,
        bundle_conflicts=bundle_conflicts,
        constraint_violations=violations,
        notes=notes,
    )
