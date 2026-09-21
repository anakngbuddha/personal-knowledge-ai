"""3.3 Import my product list.

Two calls, both stateless. ``preview`` reads the file and guesses the columns;
``import`` takes the file back with the mapping the person confirmed. Uploading twice
is a deliberate trade: the alternative is holding a parsed spreadsheet in server memory
between two requests, and on a free-tier dyno that is how you lose an import to a
restart. Recorded in CHANGELOG.md.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.catalog import product_list
from app.catalog.importer import ProductListImporter
from app.core.config import settings
from app.db.session import get_db
from app.documents.service import get_or_create_default_workspace
from app.security.audit import record_audit
from app.security.deps import resolve_principal
from app.security.principal import Principal

router = APIRouter(prefix="/catalog/import", tags=["catalog"])


class FieldOut(BaseModel):
    key: str
    label: str
    required: bool = False
    note: str = ""


class PreviewOut(BaseModel):
    headers: list[str] = Field(default_factory=list)
    sample_rows: list[list[str]] = Field(default_factory=list)
    row_count: int = 0
    mapping: dict[str, str] = Field(default_factory=dict)
    fields: list[FieldOut] = Field(default_factory=list)
    sheet_name: str | None = None
    truncated: bool = False
    ready: int = 0
    problems: list[dict] = Field(default_factory=list)


class ImportOut(BaseModel):
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    total: int = 0
    problems: list[dict] = Field(default_factory=list)
    truncated: bool = False


def _require_writer(principal: Principal) -> None:
    if not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="you need edit rights to change the map")


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty.")
    if len(data) > settings.catalog_import_max_bytes:
        raise HTTPException(
            status_code=413,
            detail="That file is too big. Split the list or remove extra sheets and try again.",
        )
    return data


def _table(data: bytes, filename: str) -> product_list.Table:
    try:
        return product_list.read_table(
            data, filename=filename or "", max_rows=settings.catalog_import_max_rows
        )
    except product_list.UnsupportedProductList as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _mapping(raw: str | None, table: product_list.Table) -> dict:
    if not raw:
        return product_list.suggest_mapping(table.headers)
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="The column choices were unreadable.") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="The column choices were unreadable.")
    return {str(key): str(value or "") for key, value in parsed.items()}


@router.get("/fields", response_model=list[FieldOut])
def list_fields() -> list[FieldOut]:
    """What a column can be mapped to."""
    return [FieldOut(**item) for item in product_list.field_catalogue()]


@router.post("/preview", response_model=PreviewOut)
async def preview_import(
    file: UploadFile = File(...),
    principal: Principal = Depends(resolve_principal),
) -> PreviewOut:
    _require_writer(principal)
    data = await _read_upload(file)
    table = _table(data, file.filename or "")
    mapping = product_list.suggest_mapping(table.headers)
    plan = product_list.build_plan(table, mapping)
    return PreviewOut(
        headers=table.headers,
        sample_rows=table.rows[:8],
        row_count=table.row_count,
        mapping=mapping,
        fields=[FieldOut(**item) for item in product_list.field_catalogue()],
        sheet_name=table.sheet_name,
        truncated=table.truncated,
        ready=plan.count,
        problems=[problem.as_dict() for problem in plan.problems],
    )


@router.post("", response_model=ImportOut)
async def import_products(
    file: UploadFile = File(...),
    mapping: str | None = Form(None),
    overwrite: bool = Form(False),
    dry_run: bool = Form(False),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> ImportOut:
    _require_writer(principal)
    data = await _read_upload(file)
    table = _table(data, file.filename or "")
    plan = product_list.build_plan(table, _mapping(mapping, table))
    if not plan.drafts and plan.problems:
        raise HTTPException(status_code=400, detail=plan.problems[0].reason)

    workspace = get_or_create_default_workspace(db, principal.org_id)
    result = ProductListImporter(db).apply(
        org_id=principal.org_id,
        workspace_id=workspace.id,
        plan=plan,
        overwrite=overwrite,
        dry_run=dry_run,
    )
    if not dry_run:
        record_audit(
            db,
            principal,
            "import_product_list",
            "product",
            None,
            {"file": file.filename, **result.as_dict()},
        )
    return ImportOut(**result.as_dict())
