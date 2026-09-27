"""Workspace-only agent tools. Model arguments never supply tenant or user identity."""

from __future__ import annotations

import io
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select

from app.core.errors import AppError
from app.db.models import AgentAction, Document, Note, Product, ProductEdge, WorkflowRun
from app.security.audit import record_audit
from app.security.principal import MCP_WRITE_SCOPE
from app.tools.registry import RegisteredTool, ToolContext


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListArgs(_Args):
    query: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=20, ge=1, le=50)


class DraftArgs(_Args):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=100_000)


class RequirementsArgs(_Args):
    title: str = Field(min_length=1, max_length=200)
    requirements: list[str] = Field(min_length=1, max_length=100)
    source_document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)


class RfpArgs(_Args):
    document_id: uuid.UUID | None = None
    pasted_requirements: str | None = Field(default=None, max_length=50_000)
    account_ref: str | None = Field(default=None, max_length=128)


class StudioArgs(_Args):
    kind: str = Field(pattern="^(briefing|faq|compare)$")
    document_ids: list[uuid.UUID] = Field(min_length=1, max_length=12)


class NotebookArgs(_Args):
    name: str = Field(min_length=1, max_length=200)


class WorkflowArgs(_Args):
    kind: str = Field(pattern="^(solution-composer|incident-triage|upgrade-impact)$")
    text: str = Field(min_length=1, max_length=50_000)
    install_base: list[str] = Field(default_factory=list, max_length=100)
    account_ref: str | None = Field(default=None, max_length=128)
    proposed_version: str | None = Field(default=None, max_length=128)


class AdvisorBriefArgs(_Args):
    requirements: str = Field(min_length=1, max_length=50_000)
    account_ref: str | None = Field(default=None, max_length=128)


class DeleteNoteArgs(_Args):
    note_id: uuid.UUID


class PublishProductArgs(_Args):
    name: str = Field(min_length=2, max_length=512)
    vendor: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=2, max_length=128)
    description: str | None = Field(default=None, max_length=4000)


class ApproveWorkflowArgs(_Args):
    run_id: uuid.UUID
    task_slug: str = Field(min_length=1, max_length=128)


class MapSuggestionArgs(_Args):
    source_product_id: uuid.UUID
    target_product_id: uuid.UUID
    relation_type: str = Field(min_length=1, max_length=64)
    evidence: str = Field(min_length=3, max_length=4000)
    document_id: uuid.UUID


def _write(ctx: ToolContext) -> None:
    if not ctx.principal.can_write_catalog or not ctx.principal.has_scope(MCP_WRITE_SCOPE):
        raise PermissionError("solutions engineer write permission required")


def _notebook(ctx: ToolContext) -> uuid.UUID | None:
    if ctx.notebook_id is None:
        return None
    from app.notebooks.service import get_notebook

    notebook = get_notebook(ctx.db, org_id=ctx.principal.org_id, notebook_id=ctx.notebook_id)
    if notebook.workspace_id != ctx.workspace_id:
        raise PermissionError("notebook is outside this workspace")
    return notebook.id


def _account(ctx: ToolContext, account_ref: str | None) -> None:
    if account_ref and not ctx.principal.sees_all_accounts and account_ref not in (ctx.principal.account_refs or ()):
        raise PermissionError("account is outside your grants")


def _document(ctx: ToolContext, document_id: uuid.UUID) -> Document:
    predicates = [
        Document.id == document_id,
        Document.org_id == ctx.principal.org_id,
        Document.workspace_id == ctx.workspace_id,
        Document.sensitivity.in_(ctx.principal.readable_sensitivities()),
    ]
    if not ctx.principal.sees_all_accounts:
        predicates.append(or_(Document.account_ref.is_(None), Document.account_ref.in_(ctx.principal.account_refs or ())))
    if not ctx.principal.include_unapproved:
        from app.security.labels import ApprovalState
        predicates.append(Document.approval_state == str(ApprovalState.APPROVED))
    if ctx.notebook_id is not None:
        from app.notebooks.service import enabled_document_ids, get_notebook
        notebook = get_notebook(ctx.db, org_id=ctx.principal.org_id, notebook_id=ctx.notebook_id)
        if notebook.workspace_id != ctx.workspace_id:
            raise PermissionError("notebook is outside this workspace")
        predicates.append(Document.id.in_(enabled_document_ids(ctx.db, notebook=notebook)))
    row = ctx.db.scalar(select(Document).where(*predicates))
    if row is None:
        raise AppError(status_code=404, code="document_not_found", message="Document not found")
    return row


def _list_sources(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, ListArgs)
    from app.notebooks.service import enabled_document_ids

    query = select(Document).where(Document.org_id == ctx.principal.org_id,
        Document.workspace_id == ctx.workspace_id, Document.is_demo.is_(False), Document.is_current.is_(True))
    if ctx.notebook_id:
        from app.notebooks.service import get_notebook
        notebook = get_notebook(ctx.db, org_id=ctx.principal.org_id, notebook_id=ctx.notebook_id)
        if notebook.workspace_id != ctx.workspace_id:
            raise PermissionError("notebook is outside this workspace")
        query = query.where(Document.id.in_(enabled_document_ids(ctx.db, notebook=notebook)))
    if args.query:
        query = query.where(or_(Document.title.ilike(f"%{args.query}%"),
                                Document.original_filename.ilike(f"%{args.query}%")))
    rows = list(ctx.db.scalars(query.order_by(Document.uploaded_at.desc()).limit(args.limit)))
    visible = []
    for row in rows:
        try:
            _document(ctx, row.id)
        except AppError:
            continue
        visible.append({"id": str(row.id), "title": row.title or row.original_filename, "status": row.status})
    return {"sources": visible}


def _list_notes(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, ListArgs)
    from app.notes.service import list_notes
    rows, total = list_notes(ctx.db, org_id=ctx.principal.org_id, workspace_id=ctx.workspace_id,
                             notebook_id=_notebook(ctx), search=args.query, limit=args.limit)
    return {"notes": [{"id": str(row.id), "title": row.title, "body": row.body[:4000]} for row in rows], "total": total}


def _list_catalog(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, ListArgs)
    query = select(Product).where(Product.org_id == ctx.principal.org_id, Product.workspace_id == ctx.workspace_id)
    if args.query:
        query = query.where(Product.name.ilike(f"%{args.query}%"))
    rows = list(ctx.db.scalars(query.limit(args.limit)))
    return {"products": [{"id": str(row.id), "name": row.name} for row in rows]}


def _list_workflows(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, ListArgs)
    rows = list(ctx.db.scalars(select(WorkflowRun).where(WorkflowRun.org_id == ctx.principal.org_id,
        WorkflowRun.workspace_id == ctx.workspace_id).order_by(WorkflowRun.created_at.desc()).limit(args.limit)))
    return {"runs": [{"id": str(row.id), "playbook": row.playbook_slug, "status": row.status} for row in rows]}


def _create_note(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, DraftArgs)
    _write(ctx)
    from app.notes.service import create_note
    row = create_note(ctx.db, org_id=ctx.principal.org_id, workspace_id=ctx.workspace_id,
                      title=args.title, body=args.body, created_by=ctx.principal.user_id, notebook_id=_notebook(ctx))
    record_audit(ctx.db, ctx.principal, "agent_create", "note", str(row.id))
    return {"artifact": {"kind": "note", "id": str(row.id), "title": row.title, "url": f"/notes/{row.id}"}}


def _create_notebook(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, NotebookArgs)
    _write(ctx)
    from app.notebooks.service import create_notebook
    row = create_notebook(ctx.db, org_id=ctx.principal.org_id, workspace_id=ctx.workspace_id, name=args.name)
    record_audit(ctx.db, ctx.principal, "agent_create", "notebook", str(row.id))
    return {"artifact": {"kind": "notebook", "id": str(row.id), "title": row.name}}


def _create_requirements(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, RequirementsArgs)
    for doc_id in args.source_document_ids:
        _document(ctx, doc_id)
    body = "# Procurement requirements (draft)\n\n" + "\n".join(
        f"- [ ] {item.strip()}" for item in args.requirements if item.strip())
    if args.source_document_ids:
        body += "\n\nSource document IDs: " + ", ".join(map(str, args.source_document_ids))
    return _create_note(ctx, DraftArgs(title=args.title, body=body))


def _create_proposal(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, DraftArgs)
    if re.search(r"(?:[$€£₱]\s*\d|\b(?:USD|EUR|GBP|PHP)\s*\d|\b\d+(?:[.,]\d+)?\s*(?:USD|EUR|GBP|PHP)\b|\b(?:unit price|subtotal|grand total|total price)\s*[:=]?\s*\d)",
                 f"{args.title}\n{args.body}", re.I):
        raise ValueError("Proposal drafts must be unpriced. Remove amounts and totals.")
    body = "# Unpriced proposal (draft)\n\nNo prices or totals are included. Verify all commitments before sending.\n\n" + args.body
    return _create_note(ctx, DraftArgs(title=args.title, body=body))


def _draft_workflow(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, DraftArgs)
    return _create_note(ctx, DraftArgs(title=f"Workflow draft: {args.title}", body=args.body))


def _start_rfp(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, RfpArgs)
    _write(ctx)
    _account(ctx, args.account_ref)
    from app.api.routes.workflows import start_playbook_run
    from app.storage.factory import get_storage
    selected_id = args.document_id or (ctx.attachment_document_ids[0] if ctx.attachment_document_ids else None)
    if selected_id is not None:
        document = _document(ctx, selected_id)
        if document.file_type.lower() not in {"csv", "xlsx", "pdf", "docx"}:
            raise ValueError("RFP source must be CSV, XLSX, PDF, or DOCX")
        data = get_storage().get(document.storage_key)
        filename = document.original_filename
    elif args.pasted_requirements:
        from docx import Document as WordDocument
        doc = WordDocument()
        for line in args.pasted_requirements.splitlines():
            doc.add_paragraph(line)
        buffer = io.BytesIO()
        doc.save(buffer)
        data, filename = buffer.getvalue(), "pasted-requirements.docx"
    else:
        raise ValueError("Provide pasted requirements or a readable source document ID")
    from app.playbooks.rfp import classify_rfp_bytes
    kind = classify_rfp_bytes(filename, data)
    key = f"rfp/{ctx.principal.org_id}/{uuid.uuid4()}/source.{kind}"
    get_storage().put(key, data)
    run = start_playbook_run(ctx.db, ctx.principal, "rfp-response", {
        "storage_key": key, "filename": filename, "account_ref": args.account_ref})
    record_audit(ctx.db, ctx.principal, "agent_start", "workflow_run", str(run.id))
    return {"artifact": {"kind": "rfp_workflow", "id": str(run.id), "title": "RFP response draft", "url": f"/workflows/runs/{run.id}"}, "status": run.status}


def _start_workflow(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, WorkflowArgs)
    _write(ctx)
    _account(ctx, args.account_ref)
    from app.api.routes.workflows import start_playbook_run
    if args.kind == "solution-composer":
        payload = {"notes": args.text, "account_ref": args.account_ref}
    elif args.kind == "incident-triage":
        if not args.install_base:
            raise ValueError("incident triage requires at least one installed product")
        payload = {"logs": args.text, "install_base": args.install_base, "account_ref": args.account_ref}
    else:
        payload = {"product": args.text, "proposed_version": args.proposed_version}
    run = start_playbook_run(ctx.db, ctx.principal, args.kind, payload)
    record_audit(ctx.db, ctx.principal, "agent_start", "workflow_run", str(run.id))
    return {"artifact": {"kind": "workflow", "id": str(run.id), "title": args.kind, "url": f"/workflows/runs/{run.id}"}, "status": run.status}


def _advisor_brief(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, AdvisorBriefArgs)
    _account(ctx, args.account_ref)
    from app.advisor.brief import extract_customer_brief
    brief = extract_customer_brief(args.requirements)
    return {"brief": brief.as_dict()}


def _run_studio(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, StudioArgs)
    _write(ctx)
    for doc_id in args.document_ids:
        _document(ctx, doc_id)
    from app.studio.service import run_studio
    result = run_studio(ctx.db, org_id=ctx.principal.org_id, workspace_id=ctx.workspace_id,
                        kind=args.kind, document_ids=args.document_ids, notebook_id=_notebook(ctx),
                        save_as_note=True, created_by=ctx.principal.user_id)
    record_audit(ctx.db, ctx.principal, "agent_create", "studio", details={"kind": args.kind})
    return result


def _pending(ctx: ToolContext, kind: str, arguments: dict[str, str], label: str) -> dict[str, Any]:
    _write(ctx)
    now = datetime.now(timezone.utc)
    existing = list(ctx.db.scalars(select(AgentAction).where(
        AgentAction.org_id == ctx.principal.org_id, AgentAction.workspace_id == ctx.workspace_id,
        AgentAction.user_id == ctx.principal.user_id, AgentAction.kind == kind,
        AgentAction.status == "pending").order_by(AgentAction.created_at.desc()).limit(20)))
    for candidate in existing:
        expiry = candidate.expires_at.replace(tzinfo=candidate.expires_at.tzinfo or timezone.utc)
        if candidate.arguments == arguments and expiry > now:
            return {"pending_action": {"id": str(candidate.id), "kind": candidate.kind,
                                       "label": label, "expires_at": expiry.isoformat()}}
    action = AgentAction(org_id=ctx.principal.org_id, workspace_id=ctx.workspace_id,
                         user_id=ctx.principal.user_id, conversation_id=ctx.conversation_id,
                         kind=kind, arguments=arguments, status="pending",
                         idempotency_key=uuid.uuid4().hex,
                         expires_at=now + timedelta(minutes=15))
    ctx.db.add(action)
    ctx.db.commit()
    record_audit(ctx.db, ctx.principal, "agent_propose", kind, str(action.id))
    return {"pending_action": {"id": str(action.id), "kind": action.kind, "label": label,
                                "expires_at": action.expires_at.isoformat()}}


def _propose_delete_note(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, DeleteNoteArgs)
    note = ctx.db.scalar(select(Note).where(Note.id == args.note_id, Note.org_id == ctx.principal.org_id,
                                            Note.workspace_id == ctx.workspace_id))
    if note is None:
        raise ValueError("Note not found")
    return _pending(ctx, "delete_note", {"note_id": str(note.id)}, f"Delete note: {note.title}")


def _propose_publish_product(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, PublishProductArgs)
    return _pending(ctx, "publish_product", args.model_dump(exclude_none=True), f"Add product to catalog: {args.name}")


def _propose_workflow_approval(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, ApproveWorkflowArgs)
    from app.db.models import TaskExecution, TaskStatus
    run = ctx.db.scalar(select(WorkflowRun).where(WorkflowRun.id == args.run_id,
        WorkflowRun.org_id == ctx.principal.org_id, WorkflowRun.workspace_id == ctx.workspace_id))
    if run is None:
        raise ValueError("Workflow run not found")
    task = ctx.db.scalar(select(TaskExecution).where(TaskExecution.workflow_run_id == run.id,
        TaskExecution.task_slug == args.task_slug, TaskExecution.status == TaskStatus.WAITING_APPROVAL))
    if task is None:
        raise ValueError("Workflow task is not waiting for approval")
    return _pending(ctx, "approve_workflow_task", {"run_id": str(run.id), "task_slug": args.task_slug},
                    f"Approve workflow step: {args.task_slug}")


def _suggest_map_relationship(ctx: ToolContext, args: BaseModel) -> dict[str, Any]:
    assert isinstance(args, MapSuggestionArgs)
    _write(ctx)
    _document(ctx, args.document_id)
    for product_id in (args.source_product_id, args.target_product_id):
        if ctx.db.scalar(select(Product.id).where(Product.id == product_id,
            Product.org_id == ctx.principal.org_id, Product.workspace_id == ctx.workspace_id)) is None:
            raise ValueError("Product not found")
    if ctx.db.scalar(select(ProductEdge.id).where(ProductEdge.workspace_id == ctx.workspace_id,
        ProductEdge.source_product_id == args.source_product_id,
        ProductEdge.target_product_id == args.target_product_id,
        ProductEdge.relation_type == args.relation_type)):
        raise ValueError("Relationship already exists; review it in the map")
    from app.catalog.models import ProductEdgeIn
    from app.catalog.service import CatalogService
    from app.db.models import EdgeStatus
    edge = CatalogService(ctx.db).create_edge(ctx.principal.org_id, ctx.workspace_id,
        ProductEdgeIn(source_product_id=args.source_product_id, target_product_id=args.target_product_id,
                      relation_type=args.relation_type, evidence=args.evidence,
                      document_id=args.document_id, status=EdgeStatus.PENDING_REVIEW, is_ai_suggested=True))
    record_audit(ctx.db, ctx.principal, "agent_suggest", "product_edge", str(edge.id))
    return {"artifact": {"kind": "map_suggestion", "id": str(edge.id), "title": args.relation_type},
            "status": EdgeStatus.PENDING_REVIEW}


WORKSPACE_TOOLS = {
    "tool_list_sources": RegisteredTool("tool_list_sources", "List accessible workspace sources, optionally in this notebook.", ListArgs, _list_sources),
    "tool_list_notes": RegisteredTool("tool_list_notes", "List or search notes in this workspace and notebook.", ListArgs, _list_notes),
    "tool_list_catalog": RegisteredTool("tool_list_catalog", "List workspace products. Use for proposals and requirements.", ListArgs, _list_catalog),
    "tool_list_workflows": RegisteredTool("tool_list_workflows", "List recent workspace workflow runs and statuses.", ListArgs, _list_workflows),
    "tool_create_note": RegisteredTool("tool_create_note", "Create a note in the current notebook when the user asks. Draft content only.", DraftArgs, _create_note),
    "tool_create_notebook": RegisteredTool("tool_create_notebook", "Create a new workspace notebook when asked.", NotebookArgs, _create_notebook),
    "tool_create_requirements": RegisteredTool("tool_create_requirements", "Create a procurement requirements checklist as a draft note.", RequirementsArgs, _create_requirements),
    "tool_create_unpriced_proposal": RegisteredTool("tool_create_unpriced_proposal", "Create an unpriced quotation or proposal draft as a note. Never include invented prices or totals.", DraftArgs, _create_proposal),
    "tool_draft_workflow": RegisteredTool("tool_draft_workflow", "Create an editable workflow plan draft as a note; do not approve or publish it.", DraftArgs, _draft_workflow),
    "tool_start_rfp": RegisteredTool("tool_start_rfp", "Start the RFP response workflow from pasted requirements or a permitted CSV, XLSX, PDF, or DOCX source document. Returns a draft run; approval steps remain gated.", RfpArgs, _start_rfp),
    "tool_start_workflow": RegisteredTool("tool_start_workflow", "Start a solution composer, incident triage, or upgrade impact draft workflow. Approval tasks remain gated.", WorkflowArgs, _start_workflow),
    "tool_advisor_brief": RegisteredTool("tool_advisor_brief", "Extract a structured procurement brief from pasted requirements without changing data.", AdvisorBriefArgs, _advisor_brief),
    "tool_run_studio": RegisteredTool("tool_run_studio", "Create a briefing, FAQ, or comparison from permitted sources and save it as a note.", StudioArgs, _run_studio),
    "tool_propose_delete_note": RegisteredTool("tool_propose_delete_note", "Request explicit in-chat approval before deleting a note. Does not delete it now.", DeleteNoteArgs, _propose_delete_note),
    "tool_propose_publish_product": RegisteredTool("tool_propose_publish_product", "Request explicit in-chat approval before adding a product to the live catalog.", PublishProductArgs, _propose_publish_product),
    "tool_propose_workflow_approval": RegisteredTool("tool_propose_workflow_approval", "Request explicit in-chat approval before approving a waiting workflow step.", ApproveWorkflowArgs, _propose_workflow_approval),
    "tool_suggest_map_relationship": RegisteredTool("tool_suggest_map_relationship", "Suggest an evidence-backed product map relationship for human review; it is not published.", MapSuggestionArgs, _suggest_map_relationship),
}
