"""Run the golden RFP scorer against placeholder (seed catalog) scenarios.

Usage:
    python scripts/run_golden_scenarios.py --out docs/eval/golden-scenarios-report.md

Before a real Phase 6.5 sign-off:
1. Replace seed data with the real product line.
2. Human-approve graph edges via POST /graph/edges/{id}/approve.
3. Regenerate docs/eval/golden-scenarios.json from that graph.
4. Re-run this script — the scorer does not change.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.eval.golden import CatalogView, score_scenario  # noqa: E402
from app.playbooks.rfp import _conflict_pairs, _draft_one, _tokenize  # noqa: E402


def _load_scenarios(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return list(payload.get("scenarios") or [])


def _catalog_from_seeds() -> CatalogView:
    from app.catalog.seeds import SEED_PRODUCTS, SEED_CAPABILITIES, SEED_EDGES
    from app.db.models import RelationType

    products = {}
    names = set()
    for item in SEED_PRODUCTS:
        names.add(item["name"])
        products[item["name"].lower()] = {
            "vendor": item["vendor"],
            "deployment_model": str(item.get("deployment_model") or ""),
            "slug": item["slug"],
        }
    slugs = {item["slug"]: item["name"] for item in SEED_PRODUCTS}
    pairs: set[frozenset[str]] = set()
    for edge in SEED_EDGES:
        if edge.get("relation_type") == RelationType.CONFLICTS_WITH:
            left = slugs.get(edge["source"])
            right = slugs.get(edge["target"])
            if left and right:
                pairs.add(frozenset({left, right}))
    return CatalogView(
        product_names=names,
        capability_names={c["name"] for c in SEED_CAPABILITIES},
        products=products,
        conflict_pairs=pairs,
    )


def _answers_for(scenario: dict, catalog: CatalogView) -> list[dict]:
    """Deterministic placeholder drafts from seed catalog token overlap."""
    from app.catalog.seeds import SEED_CAPABILITIES, SEED_PRODUCTS

    cap_by_slug = {c["slug"]: c["name"] for c in SEED_CAPABILITIES}
    constraints = scenario.get("constraints") or {}
    forbidden_vendors = {v.lower() for v in constraints.get("forbidden_vendors") or []}
    on_prem_only = bool(constraints.get("on_prem_only"))
    answers = []
    for i, req in enumerate(scenario.get("requirements") or [], start=1):
        text = req.get("text") or ""
        tokens = _tokenize(text)
        matched = []
        for item in SEED_PRODUCTS:
            blob = f"{item['name']} {item['slug']} {item['vendor']} {item.get('description') or ''} {item.get('category') or ''}"
            for slug in item.get("capabilities") or []:
                blob += " " + cap_by_slug.get(slug, slug).replace("-", " ")
            hay = _tokenize(blob)
            if not (tokens & hay):
                continue
            vendor = str(item.get("vendor") or "").lower()
            deployment = str(item.get("deployment_model") or "").lower()
            if vendor in forbidden_vendors:
                continue
            if on_prem_only and deployment == "cloud":
                continue
            matched.append(
                {
                    "name": item["name"],
                    "vendor": item.get("vendor"),
                    "deployment_model": item.get("deployment_model"),
                    "impact": {"all_incompatibilities": [], "all_prerequisites": []},
                }
            )
        for product in matched:
            incompat = []
            for pair in catalog.conflict_pairs:
                if product["name"] in pair:
                    other = next(iter(pair - {product["name"]}))
                    incompat.append({"conflicted_product_name": other})
            product["impact"] = {"all_incompatibilities": incompat, "all_prerequisites": []}
        evidence = [{"citation": f"seed-catalog:{p['name']}"} for p in matched[:1]]
        drafted = _draft_one(
            {
                "id": f"R{i}",
                "text": text,
                "evidence": evidence,
                "candidate_products": matched,
            },
            _conflict_pairs(matched),
        )
        answers.append(drafted)
    chosen_compliant: list[str] = []
    forbidden = set()
    for pair in catalog.conflict_pairs:
        forbidden.add(pair)
    for answer in answers:
        if answer.get("status") != "Compliant":
            continue
        kept = []
        for name in answer.get("products") or []:
            if any(frozenset({name, existing}) in forbidden for existing in chosen_compliant):
                answer["status"] = "Non-Compliant"
                answer["response"] = (
                    f"Refused: {name} conflicts_with an already selected product."
                )
                kept = []
                break
            kept.append(name)
            chosen_compliant.append(name)
        answer["products"] = kept
    return answers


def render_report(results: list, *, catalog_source: str) -> str:
    passed = sum(1 for r in results if r.passed)
    lines = [
        "# Golden scenario report",
        "",
        f"- Generated: {datetime.now(timezone.utc).isoformat()}",
        f"- Catalog source: **{catalog_source}** (placeholder until real product graph is curated)",
        f"- Pass rate: **{passed}/{len(results)}**",
        "",
        "## Path to a real Phase 6.5 sign-off",
        "",
        "1. Replace seed data with the real product line (`POST /catalog/seed` or a new seed module).",
        "2. Run `POST /graph/suggest-edges` and **human-approve** edges (`POST /graph/edges/{id}/approve`).",
        "3. Generate a new `docs/eval/golden-scenarios.json` from the approved graph.",
        "4. Re-run this script. The scorer in `backend/app/eval/golden.py` does not change.",
        "",
        "## Results",
        "",
        "| ID | Passed | Coverage | Hallucinated | Ungrounded | Conflicts | Constraints |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in results:
        lines.append(
            f"| {result.scenario_id} | {result.passed} | {result.coverage:.2f} | "
            f"{len(result.hallucinated)} | {len(result.ungrounded)} | "
            f"{len(result.bundle_conflicts)} | {len(result.constraint_violations)} |"
        )
    lines.append("")
    failures = [r for r in results if not r.passed]
    if failures:
        lines.append("## Failures")
        lines.append("")
        for result in failures:
            lines.append(f"### {result.scenario_id}")
            lines.append("")
            for note in result.notes:
                lines.append(f"- {note}")
            for item in result.hallucinated:
                lines.append(f"- hallucinated: {item}")
            for item in result.ungrounded:
                lines.append(f"- ungrounded: {item}")
            for pair in result.bundle_conflicts:
                lines.append(f"- conflict: {pair}")
            for item in result.constraint_violations:
                lines.append(f"- constraint: {item}")
            lines.append("")
    else:
        lines.append("All placeholder scenarios passed the deterministic scorer.")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scenarios",
        default=str(ROOT / "docs/eval/golden-scenarios.json"),
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "docs/eval/golden-scenarios-report.md"),
    )
    args = parser.parse_args()
    scenarios = _load_scenarios(Path(args.scenarios))
    catalog = _catalog_from_seeds()
    results = []
    for scenario in scenarios:
        answers = _answers_for(scenario, catalog)
        results.append(score_scenario(scenario, answers, catalog))
    report = render_report(results, catalog_source="backend/app/catalog/seeds.py")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    passed = sum(1 for r in results if r.passed)
    print(f"wrote {out} ({passed}/{len(results)} passed)")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
