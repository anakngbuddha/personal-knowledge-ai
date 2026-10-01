"""Restricted Sheets tools backed by the API, never an unrestricted MCP process."""

from __future__ import annotations

import uuid
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator
from sqlalchemy import select

from app.core.errors import AppError
from app.db.models import SalesQuoteExport, Workspace
from app.mcp.credentials import decrypt_secret
from app.mcp.servers import GOOGLE_SHEETS
from app.mcp.store import get_integration
from app.sales.sheets import SHEETS_API, service_account_access_token
from app.security.labels import Role, role_has_access


class SheetTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alias: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    workspace_id: uuid.UUID
    spreadsheet_id: str = Field(pattern=r"^[A-Za-z0-9_-]{10,255}$")
    tab: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9 _-]{0,63}$")
    draft: bool = False


class ReadSheetArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sheet_alias: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")


class WriteDraftArgs(ReadSheetArgs):
    values: list[list[StrictStr]] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def bounded_values(self):
        if any(not row or len(row) > 26 or any(len(cell) > 2000 for cell in row)
               for row in self.values):
            raise ValueError("draft rows require 1-26 cells of at most 2000 characters")
        if sum(len(cell.encode("utf-8")) for row in self.values for cell in row) > 32768:
            raise ValueError("draft exceeds 32 KiB")
        return self


def scoped_targets(ctx, row) -> list[SheetTarget]:
    if not ctx.principal.has_scope("mcp:read") or not role_has_access(ctx.principal.role, Role.SALES):
        return []
    workspace = ctx.db.scalars(select(Workspace).where(
        Workspace.id == ctx.workspace_id, Workspace.org_id == ctx.principal.org_id,
    )).first()
    if workspace is None:
        return []
    return [target for raw in (row.config or {}).get("sheet_targets", [])
            if (target := SheetTarget.model_validate(raw)).workspace_id == ctx.workspace_id]


def execute_sheets_tool(original: str, arguments: dict, ctx) -> dict:
    args = (WriteDraftArgs if original == "write_draft" else ReadSheetArgs).model_validate(arguments)
    row = get_integration(ctx.db, ctx.principal.org_id, GOOGLE_SHEETS)
    if row is None or not row.enabled or not row.secret_ciphertext:
        raise AppError("Sheets integration unavailable", status_code=403)
    target = next((item for item in scoped_targets(ctx, row) if item.alias == args.sheet_alias), None)
    if target is None:
        raise AppError("Sheet is outside the authorized workspace", status_code=403)
    writing = original == "write_draft"
    if writing:
        if not target.draft or not ctx.principal.has_scope("mcp:write") or ctx.principal.user_id is None:
            raise AppError("Draft write access required", status_code=403)
        # Export artifacts remain immutable even if an administrator mislabels one as a draft.
        exported = ctx.db.scalars(select(SalesQuoteExport.id).where(
            SalesQuoteExport.org_id == ctx.principal.org_id,
            SalesQuoteExport.external_id == target.spreadsheet_id,
        ).limit(1)).first()
        if exported is not None:
            raise AppError("Issued quote spreadsheets are immutable", status_code=403)
    token = service_account_access_token(decrypt_secret(row.secret_ciphertext))
    cell_range = f"'{target.tab}'!A1:Z100"
    url = f"{SHEETS_API}/{target.spreadsheet_id}/values/{quote(cell_range, safe='')}"
    with httpx.Client(timeout=15.0, follow_redirects=False) as client:
        with client.stream(
            "PUT" if writing else "GET", url,
            headers={"Authorization": f"Bearer {token}"},
            params={"valueInputOption": "RAW"} if writing else {"majorDimension": "ROWS"},
            json={"range": cell_range, "majorDimension": "ROWS", "values": args.values} if writing else None,
        ) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 65536:
                    raise AppError("Sheets response exceeds 64 KiB", status_code=502)
    import json
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise AppError("Malformed Sheets response", status_code=502)
    if writing:
        expected = sum(len(line) for line in args.values)
        if payload.get("updatedCells") != expected:
            raise AppError("Sheets did not confirm all draft cells", status_code=502)
        return {"sheet_alias": target.alias, "updated_cells": expected, "status": "draft"}
    values = payload.get("values", [])
    if not isinstance(values, list) or len(values) > 100 or any(
        not isinstance(line, list) or len(line) > 26 for line in values
    ):
        raise AppError("Malformed Sheets values", status_code=502)
    return {"sheet_alias": target.alias, "values": values, "source": "google_sheets"}
