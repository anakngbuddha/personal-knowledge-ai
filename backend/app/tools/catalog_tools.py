"""Catalog graph tools. Thin wrappers around CatalogService — no graph logic here."""

from __future__ import annotations

from typing import Any

from app.catalog.service import CatalogService
from app.db.models import Product
from app.tools.registry import ToolContext


def _resolve_product(service: CatalogService, workspace_id, name_or_slug: str) -> Product | None:
    needle = name_or_slug.strip().lower()
    if not needle:
        return None
    products = service.list_products(workspace_id, limit=500)
    exact = [
        p for p in products if p.name.lower() == needle or p.slug.lower() == needle
    ]
    if len(exact) == 1:
        return exact[0]
    if exact:
        return exact[0]
    partial = [
        p
        for p in products
        if needle in p.name.lower() or needle in p.slug.lower()
    ]
    if len(partial) == 1:
        return partial[0]
    return None


def catalog_impact(ctx: ToolContext, product: str) -> dict[str, Any]:
    service = CatalogService(ctx.db)
    found = _resolve_product(service, ctx.workspace_id, product)
    if found is None:
        return {"error": "unknown_product", "product": product}
    result = service.query_impact(found.id, ctx.workspace_id)
    return result.model_dump(mode="json")


def detect_contradictions_tool(ctx: ToolContext, product: str | None) -> dict[str, Any]:
    service = CatalogService(ctx.db)
    report = service.audit_integrity(ctx.workspace_id)
    payload = report.model_dump(mode="json")
    if product:
        needle = product.strip().lower()
        payload["contradictions"] = [
            c
            for c in payload.get("contradictions", [])
            if any(needle in str(name).lower() for name in c.get("products", []))
        ]
        payload["filtered_to"] = product
    return {
        "contradictions": payload.get("contradictions", []),
        "contradictions_detected": bool(payload.get("contradictions")),
        "filtered_to": payload.get("filtered_to"),
    }


def check_prerequisites(ctx: ToolContext, product: str) -> dict[str, Any]:
    service = CatalogService(ctx.db)
    report = service.audit_integrity(ctx.workspace_id)
    found = _resolve_product(service, ctx.workspace_id, product)
    out: dict[str, Any] = {
        "cycles": report.cycles,
        "cycle_detected": report.cycle_detected,
    }
    if found is None:
        out["error"] = "unknown_product"
        out["product"] = product
        return out
    impact = service.query_impact(found.id, ctx.workspace_id)
    out["product"] = impact.product_name
    out["all_prerequisites"] = [
        item.model_dump(mode="json") for item in impact.all_prerequisites
    ]
    out["all_incompatibilities"] = [
        item.model_dump(mode="json") for item in impact.all_incompatibilities
    ]
    return out
