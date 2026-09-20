"""Unit tests for the catalog-agnostic golden RFP scorer."""

from app.eval.golden import CatalogView, score_scenario


def _catalog() -> CatalogView:
    return CatalogView(
        product_names={"Apex Identity Broker", "Aegis Zero Trust Gateway", "Pure Storage FlashArray"},
        capability_names={"Single Sign-On (SSO)", "Zero Trust Network Access (ZTNA)"},
        products={
            "apex identity broker": {"vendor": "Apex Platform", "deployment_model": "cloud"},
            "aegis zero trust gateway": {"vendor": "Apex Platform", "deployment_model": "hybrid"},
            "pure storage flasharray": {"vendor": "Pure Storage", "deployment_model": "on-prem"},
        },
        conflict_pairs={frozenset({"Aegis Zero Trust Gateway", "Pure Storage FlashArray"})},
    )


def _scenario(**overrides):
    base = {
        "id": "t-1",
        "requirements": [{"text": "SSO", "must_have": True}, {"text": "ZTNA", "must_have": True}],
        "constraints": {},
        "expected": {
            "min_coverage": 0.9,
            "must_cite": True,
            "forbidden_relations": ["conflicts_with"],
        },
    }
    base.update(overrides)
    return base


def test_coverage_below_threshold_fails():
    result = score_scenario(
        _scenario(),
        [{"id": "R1", "status": "Non-Compliant", "products": [], "citations": []}],
        _catalog(),
    )
    assert result.passed is False
    assert result.coverage < 0.9


def test_missing_citation_on_compliant_fails():
    answers = [
        {"id": "R1", "status": "Compliant", "products": ["Apex Identity Broker"], "citations": []},
        {"id": "R2", "status": "Non-Compliant", "products": [], "citations": []},
    ]
    result = score_scenario(_scenario(), answers, _catalog())
    assert result.passed is False
    assert "R1" in result.ungrounded


def test_bundle_conflict_fails():
    answers = [
        {
            "id": "R1",
            "status": "Compliant",
            "products": ["Aegis Zero Trust Gateway"],
            "citations": ["a"],
        },
        {
            "id": "R2",
            "status": "Compliant",
            "products": ["Pure Storage FlashArray"],
            "citations": ["b"],
        },
    ]
    result = score_scenario(_scenario(), answers, _catalog())
    assert result.passed is False
    assert result.bundle_conflicts


def test_forbidden_vendor_constraint_fails():
    scenario = _scenario(
        constraints={"forbidden_vendors": ["Apex Platform"]},
        requirements=[{"text": "SSO", "must_have": True}],
    )
    answers = [
        {
            "id": "R1",
            "status": "Compliant",
            "products": ["Apex Identity Broker"],
            "citations": ["a"],
        }
    ]
    result = score_scenario(scenario, answers, _catalog())
    assert result.passed is False
    assert result.constraint_violations


def test_clean_non_compliant_set_passes():
    answers = [
        {"id": "R1", "status": "Non-Compliant", "products": [], "citations": []},
        {"id": "R2", "status": "Non-Compliant", "products": [], "citations": []},
    ]
    result = score_scenario(_scenario(), answers, _catalog())
    assert result.passed is True
    assert result.coverage == 1.0
