"""Google Sheets customer export preserves quote amounts and hides commercial cost."""

import json
from datetime import datetime, timezone

import httpx
import pytest

from app.sales.sheets import GoogleSheetsExporter, SheetExportError, customer_sheet_rows, service_account_access_token


def snapshot():
    return {
        "result": {
            "currency": "USD", "subtotal": "22.50", "tax_total": "1.13", "total": "23.63",
            "lines": [{"provider": "azure", "sku": "vm-4-16", "assumption": "2 servers for 10h",
                       "source_ref": "https://prices.azure.com/api/retail/prices",
                       "expires_at": "2026-10-01T00:00:00Z", "sell_amount": "22.50",
                       "tax_amount": "1.13", "total_amount": "23.63",
                       "cost_amount": "14.00", "margin_percent": "37.7"}],
        },
        "lines": [{"observation_id": "obs-1", "cost_per_unit": "0.7",
                   "input": {"resource_quantity": "2", "usage_per_resource": "10"}}],
        "observations": [{"region": "eastus"}],
    }


def test_sheet_rows_match_issued_quote_and_redact_cost():
    rows = customer_sheet_rows(snapshot(), quote_id="quote-1", version=2,
                               issued_at=datetime(2026, 9, 30, tzinfo=timezone.utc))
    assert rows[4][0:5] == ["azure", "vm-4-16", "eastus", "2", "10"]
    assert rows[-1] == ["Total", "23.63"]
    assert "cost" not in json.dumps(rows).lower()
    assert "margin" not in json.dumps(rows).lower()
    assert "obs-1" in rows[4]


@pytest.mark.anyio
async def test_sheet_export_creates_writes_and_formats_with_raw_values():
    calls = []

    def respond(request):
        calls.append(request)
        if request.url.path == "/v4/spreadsheets":
            return httpx.Response(200, json={"spreadsheetId": "sheet_id_123456789",
                                             "sheets": [{"properties": {"sheetId": 0}}]})
        if request.url.path.endswith("/values:batchUpdate"):
            return httpx.Response(200, json={"totalUpdatedRows": 7})
        return httpx.Response(200, json={"replies": [{}, {}]})

    rows = customer_sheet_rows(snapshot(), quote_id="quote-1", version=2,
                               issued_at=datetime(2026, 9, 30, tzinfo=timezone.utc))
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        spreadsheet_id = await GoogleSheetsExporter("token", client).export(rows, title="Quote 1 v2")
    assert spreadsheet_id == "sheet_id_123456789"
    assert len(calls) == 3
    assert all(call.headers["Authorization"] == "Bearer token" for call in calls)
    written = json.loads(calls[1].content)
    assert written["valueInputOption"] == "RAW"
    assert written["data"][0]["values"] == rows


def test_invalid_service_account_configuration_fails_closed():
    with pytest.raises(SheetExportError):
        service_account_access_token('{"type":"service_account","token_uri":"https://evil.invalid"}')


def test_service_account_authorization_has_a_bounded_timeout(monkeypatch):
    from google.auth.transport import requests
    from google.oauth2 import service_account
    calls = []

    class Credentials:
        token = "issued-token"

        def refresh(self, request):
            request(url="https://oauth2.googleapis.com/token", timeout=120)

    monkeypatch.setattr(service_account.Credentials, "from_service_account_info", lambda *args, **kwargs: Credentials())
    monkeypatch.setattr(requests, "Request", lambda: lambda **kwargs: calls.append(kwargs))
    secret = json.dumps({"type": "service_account", "token_uri": "https://oauth2.googleapis.com/token",
                         "client_email": "test@example.com", "private_key": "fixture"})
    assert service_account_access_token(secret) == "issued-token"
    assert calls[0]["timeout"] == 15.0
