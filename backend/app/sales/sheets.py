"""Customer-safe Google Sheets export of an issued, immutable quote version."""

from __future__ import annotations

import re
from datetime import datetime

import httpx

SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetExportError(RuntimeError):
    pass


def validate_service_account_config(secret: str) -> dict:
    import json
    try:
        info = json.loads(secret)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid Google service account JSON") from exc
    if (not isinstance(info, dict) or info.get("type") != "service_account"
            or info.get("token_uri") != "https://oauth2.googleapis.com/token"
            or not isinstance(info.get("client_email"), str)
            or not isinstance(info.get("private_key"), str)):
        raise ValueError("invalid Google service account configuration")
    return info


def service_account_access_token(secret: str) -> str:
    """Exchange a tenant service account assertion for a short-lived Sheets token."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
        info = validate_service_account_config(secret)
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=[SHEETS_SCOPE]
        )
        request = Request()

        def bounded_request(**kwargs):
            kwargs["timeout"] = 15.0
            return request(**kwargs)

        credentials.refresh(bounded_request)
        if not credentials.token:
            raise ValueError("Google did not issue an access token")
        return str(credentials.token)
    except Exception as exc:
        raise SheetExportError("Google Sheets service account authorization failed") from exc


def customer_sheet_rows(snapshot: dict, *, quote_id: str, version: int, issued_at: datetime) -> list[list[str]]:
    """Only customer-facing prices and provenance; no internal cost or margin."""
    result = snapshot["result"]
    lines = result["lines"]
    references = snapshot["lines"]
    if not isinstance(lines, list) or not 1 <= len(lines) <= 100 or len(lines) != len(references):
        raise SheetExportError("quote snapshot has inconsistent lines")
    rows = [
        ["Quote ID", quote_id, "Version", str(version)],
        ["Currency", result["currency"], "Issued at", issued_at.isoformat()],
        [],
        ["Provider", "SKU", "Region", "Resources", "Usage/resource", "Assumption",
         "Price observation ID", "Source", "Price valid until", "Sell", "Tax", "Total"],
    ]
    for line, reference, observation in zip(lines, references, snapshot["observations"], strict=True):
        values = reference["input"]
        rows.append([
            str(line["provider"]), str(line["sku"]), str(observation["region"]),
            str(values["resource_quantity"]), str(values["usage_per_resource"]),
            str(line["assumption"]), str(reference["observation_id"]),
            str(line["source_ref"]), str(line["expires_at"]),
            str(line["sell_amount"]), str(line["tax_amount"]), str(line["total_amount"]),
        ])
    rows.extend([
        [], ["Subtotal", str(result["subtotal"])],
        ["Tax", str(result["tax_total"])], ["Total", str(result["total"])],
    ])
    return rows


class GoogleSheetsExporter:
    def __init__(self, access_token: str, client: httpx.AsyncClient | None = None):
        if not access_token:
            raise ValueError("Sheets access token required")
        self.access_token = access_token
        self.client = client

    async def _post(self, client: httpx.AsyncClient, url: str, payload: dict) -> dict:
        try:
            response = await client.post(
                url, json=payload, headers={"Authorization": f"Bearer {self.access_token}"}
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise SheetExportError("Google Sheets API request failed") from exc
        if not isinstance(body, dict):
            raise SheetExportError("Google Sheets API response is malformed")
        return body

    async def export(self, rows: list[list[str]], *, title: str) -> str:
        if not rows or len(rows) > 110 or not 1 <= len(title) <= 100:
            raise ValueError("invalid Sheets export size or title")
        own_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=20.0, follow_redirects=False)
        try:
            created = await self._post(client, SHEETS_API, {
                "properties": {"title": title}, "sheets": [{"properties": {"title": "Quote"}}],
            })
            spreadsheet_id = created.get("spreadsheetId")
            try:
                sheet_id = created["sheets"][0]["properties"]["sheetId"]
            except (KeyError, IndexError, TypeError) as exc:
                raise SheetExportError("Google Sheets create response has no sheet ID") from exc
            if (not isinstance(spreadsheet_id, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{10,255}", spreadsheet_id)
                    or type(sheet_id) is not int):
                raise SheetExportError("Google Sheets create response has invalid IDs")
            written = await self._post(
                client, f"{SHEETS_API}/{spreadsheet_id}/values:batchUpdate", {
                    "valueInputOption": "RAW",
                    "data": [{"range": "Quote!A1", "majorDimension": "ROWS", "values": rows}],
                },
            )
            if written.get("totalUpdatedRows", 0) < len([row for row in rows if row]):
                raise SheetExportError("Google Sheets did not confirm every quote row")
            await self._post(client, f"{SHEETS_API}/{spreadsheet_id}:batchUpdate", {
                "requests": [
                    {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 3, "endRowIndex": 4},
                                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                                    "fields": "userEnteredFormat.textFormat.bold"}},
                    {"updateSheetProperties": {"properties": {"sheetId": sheet_id,
                                                                 "gridProperties": {"frozenRowCount": 4}},
                                               "fields": "gridProperties.frozenRowCount"}},
                ],
            })
            return spreadsheet_id
        finally:
            if own_client:
                await client.aclose()
