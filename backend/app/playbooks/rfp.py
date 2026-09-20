"""RFP Responder playbook: parse spreadsheet → graph → retrieve → draft → HITL → DOCX."""

from __future__ import annotations

import csv
import io
import re
from typing import Any

from app.catalog.service import CatalogService
from app.core.errors import AppError
from app.documents.injection import wrap_untrusted
from app.storage.factory import get_storage
from app.tools.catalog_tools import catalog_impact
from app.tools.registry import ToolContext
from app.tools.search_tools import hybrid_search_tool
from app.workflows.handlers import HandlerContext, register

_HEADER_ALIASES = {
    "question": "text",
    "requirement": "text",
    "requirement text": "text",
    "req": "text",
    "section": "section",
    "category": "section",
    "must_have": "must_have",
    "must have": "must_have",
    "mandatory": "must_have",
}


def parse_spreadsheet(data: bytes, filename: str = "") -> list[dict[str, Any]]:
    """Extract requirement rows from CSV or XLSX bytes."""
    name = filename.lower()
    if name.endswith(".csv") or _looks_like_csv(data):
        return _parse_csv(data)
    return _parse_xlsx(data)


def _looks_like_csv(data: bytes) -> bool:
    if data[:2] == b"PK":
        return False
    sample = data[:2048].decode("utf-8", errors="replace")
    return "," in sample or ";" in sample or "\t" in sample


def _normalize_header(value: str) -> str:
    return _HEADER_ALIASES.get(value.strip().lower(), value.strip().lower())


def _parse_csv(data: bytes) -> list[dict[str, Any]]:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for i, raw in enumerate(reader, start=1):
        mapped = {_normalize_header(k or ""): (v or "").strip() for k, v in raw.items()}
        requirement = mapped.get("text") or next((v for v in mapped.values() if v), "")
        if not requirement:
            continue
        rows.append(
            {
                "id": f"R{i}",
                "text": requirement,
                "section": mapped.get("section") or "",
                "must_have": _truthy(mapped.get("must_have")),
            }
        )
    return rows


def _parse_xlsx(data: bytes) -> list[dict[str, Any]]:
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        sheet = workbook.active
        rows_iter = sheet.iter_rows(values_only=True)
        header_row = next(rows_iter, None)
        if not header_row:
            return []
        headers = [_normalize_header(str(h or "")) for h in header_row]
        rows: list[dict[str, Any]] = []
        for i, values in enumerate(rows_iter, start=1):
            mapped = {
                headers[idx]: ("" if val is None else str(val).strip())
                for idx, val in enumerate(values)
                if idx < len(headers)
            }
            requirement = mapped.get("text") or next((v for v in mapped.values() if v), "")
            if not requirement:
                continue
            rows.append(
                {
                    "id": f"R{i}",
                    "text": requirement,
                    "section": mapped.get("section") or "",
                    "must_have": _truthy(mapped.get("must_have")),
                }
            )
        return rows
    finally:
        workbook.close()


def _truthy(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "must", "required"}


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", text.lower()) if t}


@register("rfp.parse")
def parse_rfp(ctx: HandlerContext, payload: dict[str, Any]) -> dict[str, Any]:
    storage_key = (payload.get("storage_key") or (ctx.run.input_payload or {}).get("storage_key"))
    filename = payload.get("filename") or (ctx.run.input_payload or {}).get("filename") or "rfp.xlsx"
    if not storage_key:
        raise AppError(status_code=400, code="missing_rfp", message="RFP file storage_key is required")
    data = get_storage().get(storage_key)
    requirements = parse_spreadsheet(data, filename)
    return {"requirements": requirements, "filename": filename}


@register("rfp.evaluate")
def evaluate_capabilities(ctx: HandlerContext, payload: dict[str, Any]) -> dict[str, Any]:
    parsed = ctx.upstream.get("parse_rfp") or {}
    requirements = list(parsed.get("requirements") or [])
    service = CatalogService(ctx.db)
    products = service.list_products(ctx.run.workspace_id, limit=500)
    capabilities = service.list_capabilities(ctx.run.org_id)
    tool_ctx = ToolContext(ctx.db, ctx.principal, ctx.run.workspace_id)

    evaluated = []
    for req in requirements:
        tokens = _tokenize(req.get("text") or "")
        matched_caps = []
        for cap in capabilities:
            hay = _tokenize(f"{cap.name} {cap.slug} {cap.description or ''}")
            if tokens & hay:
                matched_caps.append({"name": cap.name, "slug": cap.slug})
        matched_products = []
        for product in products:
            hay = _tokenize(
                f"{product.name} {product.slug} {product.vendor} {product.description or ''} {product.category or ''}"
            )
            if tokens & hay:
                impact = catalog_impact(tool_ctx, product.name)
                matched_products.append(
                    {
                        "name": product.name,
                        "slug": product.slug,
                        "vendor": product.vendor,
                        "ownership": product.ownership,
                        "deployment_model": product.deployment_model,
                        "impact": impact if impact.get("error") != "unknown_product" else {},
                    }
                )
        evaluated.append(
            {
                **req,
                "candidate_capabilities": matched_caps[:8],
                "candidate_products": matched_products[:8],
            }
        )
    return {"requirements": evaluated}


@register("rfp.retrieve")
def retrieve_evidence(ctx: HandlerContext, payload: dict[str, Any]) -> dict[str, Any]:
    evaluated = (ctx.upstream.get("evaluate_capabilities") or {}).get("requirements") or []
    tool_ctx = ToolContext(ctx.db, ctx.principal, ctx.run.workspace_id)
    rows = []
    for req in evaluated:
        hits: list[dict[str, Any]] = []
        try:
            result = hybrid_search_tool(tool_ctx, req.get("text") or "")
            hits = result.get("hits") or []
        except Exception:  # noqa: BLE001 - sqlite/unit tests have no pgvector
            hits = []
        rows.append({**req, "evidence": hits[:6]})
    return {"requirements": rows}


def _conflict_pairs(products: list[dict[str, Any]]) -> set[frozenset[str]]:
    pairs: set[frozenset[str]] = set()
    for product in products:
        impact = product.get("impact") or {}
        name = product.get("name")
        for item in impact.get("all_incompatibilities") or []:
            other = item.get("conflicted_product_name")
            if name and other:
                pairs.add(frozenset({name, other}))
    return pairs


def _draft_one(req: dict[str, Any], forbidden: set[frozenset[str]]) -> dict[str, Any]:
    evidence = list(req.get("evidence") or [])
    products = list(req.get("candidate_products") or [])
    citations = [h.get("citation") for h in evidence if h.get("citation")]
    chosen: list[str] = []
    for product in products:
        name = product.get("name")
        if not name:
            continue
        if any(frozenset({name, existing}) in forbidden for existing in chosen):
            continue
        chosen.append(name)
    if not evidence and not chosen:
        return {
            **req,
            "status": "Non-Compliant",
            "confidence": 0.2,
            "response": "The available sources do not contain sufficient information to answer this question.",
            "citations": [],
            "products": [],
            "unmet_prerequisites": True,
        }
    status = "Compliant" if (evidence and chosen) else "Partially"
    confidence = 0.9 if evidence and chosen else 0.7
    if not citations:
        status = "Non-Compliant"
        confidence = 0.4
    response = (
        f"Mapped to {', '.join(chosen) or 'catalog capabilities'}."
        if chosen
        else "Capability is only partially evidenced in approved collateral."
    )
    if evidence:
        response += f" See {citations[0]}."
    prereqs = []
    for product in products:
        for item in (product.get("impact") or {}).get("all_prerequisites") or []:
            prereqs.append(item.get("name"))
    return {
        **req,
        "status": status,
        "confidence": confidence,
        "response": response,
        "citations": citations,
        "products": chosen,
        "unmet_prerequisites": bool(prereqs) and not evidence,
    }


@register("rfp.draft")
def draft_responses(ctx: HandlerContext, payload: dict[str, Any]) -> dict[str, Any]:
    from app.generation.rate_limit import check_rate_limit, check_token_budget

    check_rate_limit(ctx.principal.user_id)
    check_token_budget(ctx.db, ctx.principal.org_id)
    retrieved = (ctx.upstream.get("retrieve_evidence") or {}).get("requirements") or []
    constraints = (ctx.run.input_payload or {}).get("constraints") or payload.get("constraints") or {}
    forbidden_vendors = {v.lower() for v in constraints.get("forbidden_vendors") or []}
    on_prem_only = bool(constraints.get("on_prem_only"))

    def allowed(product: dict[str, Any]) -> bool:
        vendor = str(product.get("vendor") or "").lower()
        deployment = str(product.get("deployment_model") or "").lower()
        if vendor and vendor in forbidden_vendors:
            return False
        if on_prem_only and deployment == "cloud":
            return False
        return True

    filtered = []
    for req in retrieved:
        products = [p for p in (req.get("candidate_products") or []) if allowed(p)]
        filtered.append({**req, "candidate_products": products})
    all_products = [p for req in filtered for p in (req.get("candidate_products") or [])]
    forbidden = _conflict_pairs(all_products)
    answers = [_draft_one(req, forbidden) for req in filtered]
    chosen_compliant: list[str] = []
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
                answer["confidence"] = 0.3
                kept = []
                break
            kept.append(name)
            chosen_compliant.append(name)
        answer["products"] = kept
    return {"answers": answers}


@register("rfp.gate")
def human_gate(ctx: HandlerContext, payload: dict[str, Any]) -> dict[str, Any]:
    answers = list((ctx.upstream.get("draft_responses") or {}).get("answers") or [])
    flagged = []
    for answer in answers:
        needs = answer.get("confidence", 1) < 0.85 or answer.get("unmet_prerequisites")
        flagged.append({**answer, "needs_review": bool(needs)})
    return {"answers": flagged, "needs_review": True}


def render_docx(answers: list[dict[str, Any]], title: str = "RFP Response") -> bytes:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    document = Document()
    heading = document.add_heading(title, level=1)
    heading.alignment = WD_ALIGN_PARAGRAPH.LEFT
    table = document.add_table(rows=1, cols=4)
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    hdr[0].text = "Requirement"
    hdr[1].text = "Response"
    hdr[2].text = "Status"
    hdr[3].text = "Citations"
    appendix: list[str] = []
    for answer in answers:
        row = table.add_row().cells
        row[0].text = str(answer.get("text") or "")
        row[1].text = str(answer.get("response") or "")
        row[2].text = str(answer.get("status") or "")
        cites = answer.get("citations") or []
        row[3].text = "; ".join(str(c) for c in cites)
        appendix.extend(str(c) for c in cites)
    document.add_heading("Citation appendix", level=2)
    if appendix:
        for cite in dict.fromkeys(appendix):
            para = document.add_paragraph(cite)
            para.style.font.size = Pt(10)
    else:
        document.add_paragraph("No citations.")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@register("rfp.export")
def export_deliverable(ctx: HandlerContext, payload: dict[str, Any]) -> dict[str, Any]:
    approved = ctx.upstream.get("human_gate") or {}
    answers = list(approved.get("answers") or [])
    # Only export rows present in the approved gate payload (HITL contract).
    data = render_docx(answers, title="RFP Response")
    key = f"rfp/{ctx.run.org_id}/{ctx.run.id}/response.docx"
    get_storage().put(
        key,
        data,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    return {
        "storage_key": key,
        "filename": "rfp-response.docx",
        "row_count": len(answers),
        "bytes": len(data),
    }
