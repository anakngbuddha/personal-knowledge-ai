"""Phase 7 workflow UI API: playbook gallery, slim run list, typed HITL edits."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.workflows import safe_download_filename
from app.db.models import (
    AuditLog,
    Base,
    Organization,
    TaskExecution,
    TaskStatus,
    WorkflowRun,
    Workspace,
)
from app.db.session import get_db
from app.main import app
from app.security.jwt import mint_token
from app.security.labels import Role
from app.workflows.loader import list_playbooks, load_playbook
from app.workflows.queue import claim, start_run, succeed, waiting_approval

client = TestClient(app)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


def _session():
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
            AuditLog.__table__,
        ],
    )
    SessionClass = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = SessionClass()
    org = Organization(id=uuid.uuid4(), slug="acme", name="Acme")
    db.add(org)
    db.commit()
    ws = Workspace(id=uuid.uuid4(), org_id=org.id, name="Default")
    db.add(ws)
    db.commit()

    def _get_db():
        inner = SessionClass()
        try:
            yield inner
        finally:
            inner.close()

    app.dependency_overrides[get_db] = _get_db
    db.org_id = org.id
    db.workspace_id = ws.id
    db.SessionClass = SessionClass
    return db


def test_list_playbooks_skips_fixtures_and_marks_rfp_runnable():
    playbooks = list_playbooks()
    slugs = {p.slug for p in playbooks}
    assert "rfp-response" in slugs
    assert "gated-fixture" not in slugs
    assert "linear-fixture" not in slugs
    rfp = next(p for p in playbooks if p.slug == "rfp-response")
    assert rfp.name == "RFP Responder"
    assert len(rfp.tasks) == 6

    token = mint_token(org_id=uuid.uuid4(), role=Role.SOLUTIONS_ENGINEER)
    db = _session()
    try:
        resp = client.get("/playbooks", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        listed = {item["slug"] for item in body["playbooks"]}
        assert "rfp-response" in listed
        assert "gated-fixture" not in listed
        rfp_item = next(item for item in body["playbooks"] if item["slug"] == "rfp-response")
        assert rfp_item["runnable"] is True
        assert rfp_item["task_count"] == 6
        assert all("workflow.yaml" not in item["slug"] for item in body["playbooks"])
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_run_list_is_slim_without_output_payloads():
    db = _session()
    try:
        playbook = load_playbook("gated-fixture")
        run = start_run(
            db,
            org_id=db.org_id,
            workspace_id=db.workspace_id,
            playbook=playbook,
            input_payload={"secret": "should-not-appear-in-list"},
            created_by=None,
            principal_snapshot={"role": "owner"},
        )
        alpha = claim(db, "w")
        succeed(db, alpha, {"answers": [{"id": "R1", "response": "huge payload"}]})
        token = mint_token(org_id=db.org_id, role=Role.SOLUTIONS_ENGINEER)
        resp = client.get("/workflows/runs", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] >= 1
        row = next(r for r in body["runs"] if r["id"] == str(run.id))
        assert "tasks" not in row
        assert "output_payload" not in row
        assert "input_payload" not in row
        assert row["task_counts"]["succeeded"] == 1
        assert row["task_counts"]["pending"] >= 1

        detail = client.get(
            f"/workflows/runs/{run.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert detail.status_code == 200
        gate = next(t for t in detail.json()["tasks"] if t["slug"] == "alpha")
        assert gate["output_payload"]["answers"][0]["id"] == "R1"
        assert gate["log_line"]
        assert "updated_at" in gate
        assert "max_attempts" in gate
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_approve_typed_answer_edits_merge_by_id():
    db = _session()
    try:
        playbook = load_playbook("gated-fixture")
        run = start_run(
            db,
            org_id=db.org_id,
            workspace_id=db.workspace_id,
            playbook=playbook,
            input_payload={},
            created_by=None,
            principal_snapshot={"role": "owner"},
        )
        alpha = claim(db, "w")
        succeed(db, alpha, {"value": 1})
        gate = claim(db, "w")
        waiting_approval(
            db,
            gate,
            {
                "needs_review": True,
                "answers": [
                    {
                        "id": "R1",
                        "text": "SSO?",
                        "response": "draft",
                        "status": "Partially",
                    }
                ],
            },
        )
        token = mint_token(org_id=db.org_id, role=Role.SOLUTIONS_ENGINEER)
        resp = client.post(
            f"/workflows/runs/{run.id}/tasks/gate/approve",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "answers": [
                    {"id": "R1", "response": "Yes, Apex Identity Broker.", "status": "Compliant"}
                ]
            },
        )
        assert resp.status_code == 200, resp.text
        gate_out = next(t for t in resp.json()["tasks"] if t["slug"] == "gate")
        assert gate_out["status"] == TaskStatus.SUCCEEDED
        answers = gate_out["output_payload"]["answers"]
        assert answers[0]["response"] == "Yes, Apex Identity Broker."
        assert answers[0]["status"] == "Compliant"
        assert answers[0]["text"] == "SSO?"
        assert gate_out["output_payload"]["needs_review"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_safe_download_filename_strips_injection():
    assert safe_download_filename("evil.docx\r\nX-Injected: yes") == "evil.docxX-Injected yes"
    assert safe_download_filename("../../etc/passwd") == "passwd"
    assert safe_download_filename('quote"name.docx') == "quotename.docx"
    assert safe_download_filename("") == "rfp-response.docx"
    assert safe_download_filename("normal-file.docx") == "normal-file.docx"
