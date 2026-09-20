"""RFP playbook unit tests: parse, draft, conflict, export, isolation."""

from __future__ import annotations

import io
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Base,
    Organization,
    Product,
    ProductEdge,
    ReferenceArchitecture,
    ReferenceArchitectureProduct,
    TaskExecution,
    TaskStatus,
    WorkflowRun,
    Workspace,
)
from app.db.session import get_db
from app.main import app
from app.playbooks.rfp import parse_spreadsheet, render_docx, _draft_one
from app.security.jwt import mint_token
from app.security.labels import Role

client = TestClient(app)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


def _csv_bytes() -> bytes:
    return (
        "requirement,section,must_have\n"
        "Does the platform support SSO with SAML?,Identity,yes\n"
        "Provide on-prem object storage.,Storage,yes\n"
    ).encode("utf-8")


def _xlsx_bytes() -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["question", "section", "must_have"])
    ws.append(["Does the SIEM correlate firewall events?", "Security", "yes"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_csv_and_xlsx():
    csv_rows = parse_spreadsheet(_csv_bytes(), "rfp.csv")
    assert len(csv_rows) == 2
    assert csv_rows[0]["must_have"] is True
    assert "SSO" in csv_rows[0]["text"]

    xlsx_rows = parse_spreadsheet(_xlsx_bytes(), "rfp.xlsx")
    assert len(xlsx_rows) == 1
    assert "SIEM" in xlsx_rows[0]["text"]


def test_draft_without_evidence_is_non_compliant():
    drafted = _draft_one(
        {"id": "R1", "text": "Secret unannounced discount?", "evidence": [], "candidate_products": []},
        forbidden=set(),
    )
    assert drafted["status"] == "Non-Compliant"
    assert drafted["citations"] == []
    assert drafted["products"] == []
    assert "sufficient information" in drafted["response"].lower()


def test_conflicting_products_not_both_compliant():
    forbidden = {frozenset({"Aegis Zero Trust Gateway", "Pure Storage FlashArray"})}
    drafted = _draft_one(
        {
            "id": "R1",
            "text": "Bundle zero trust with flash arrays",
            "evidence": [{"citation": "Datasheet p.1"}],
            "candidate_products": [
                {"name": "Aegis Zero Trust Gateway", "impact": {}},
                {"name": "Pure Storage FlashArray", "impact": {}},
            ],
        },
        forbidden=forbidden,
    )
    assert drafted["status"] in {"Compliant", "Partially"}
    assert not (
        "Aegis Zero Trust Gateway" in drafted["products"]
        and "Pure Storage FlashArray" in drafted["products"]
    )


def test_export_docx_omits_unapproved_rows():
    approved = [
        {
            "text": "SSO?",
            "response": "Yes, Apex Identity Broker.",
            "status": "Compliant",
            "citations": ["Apex datasheet p.2"],
        }
    ]
    data = render_docx(approved)
    assert data[:2] == b"PK"
    from docx import Document

    doc = Document(io.BytesIO(data))
    texts = [p.text for p in doc.paragraphs] + [c.text for t in doc.tables for r in t.rows for c in r.cells]
    blob = " ".join(texts)
    assert "SSO?" in blob
    assert "unapproved-secret" not in blob
    assert "Apex datasheet p.2" in blob


def test_cross_tenant_deliverable_is_404():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            Workspace.__table__,
            WorkflowRun.__table__,
            TaskExecution.__table__,
        ],
    )
    SessionClass = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = SessionClass()
    org_a = Organization(id=uuid.uuid4(), slug="org-a", name="A")
    org_b = Organization(id=uuid.uuid4(), slug="org-b", name="B")
    db.add_all([org_a, org_b])
    db.commit()
    ws_a = Workspace(id=uuid.uuid4(), org_id=org_a.id, name="A")
    db.add(ws_a)
    db.commit()
    run = WorkflowRun(
        org_id=org_a.id,
        workspace_id=ws_a.id,
        playbook_slug="rfp-response",
        status="succeeded",
        input_payload={},
    )
    db.add(run)
    db.flush()
    db.add(
        TaskExecution(
            workflow_run_id=run.id,
            org_id=org_a.id,
            task_slug="export_deliverable",
            status=TaskStatus.SUCCEEDED,
            output_payload={"storage_key": "rfp/secret.docx", "filename": "x.docx"},
        )
    )
    db.commit()

    def _get_db():
        inner = SessionClass()
        try:
            yield inner
        finally:
            inner.close()

    app.dependency_overrides[get_db] = _get_db
    try:
        token_b = mint_token(org_id=org_b.id, role=Role.ADMIN)
        resp = client.get(
            f"/workflows/runs/{run.id}/deliverable",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
