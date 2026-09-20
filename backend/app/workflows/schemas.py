"""Pydantic schemas for workflow runs and HITL gates."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskOut(BaseModel):
    id: str
    slug: str
    status: str
    depends_on_slugs: list[str] = Field(default_factory=list)
    output_payload: dict[str, Any] | None = None
    error_message: str | None = None
    retry_count: int = 0
    max_attempts: int = 4
    worker_id: str | None = None
    updated_at: str | None = None
    log_line: str | None = None


class TaskCounts(BaseModel):
    pending: int = 0
    running: int = 0
    waiting_approval: int = 0
    succeeded: int = 0
    failed: int = 0


class WorkflowRunOut(BaseModel):
    id: str
    playbook_slug: str
    status: str
    org_id: str
    workspace_id: str
    input_payload: dict[str, Any] | None = None
    error_message: str | None = None
    tasks: list[TaskOut] = Field(default_factory=list)
    created_at: str
    updated_at: str


class WorkflowRunSummaryOut(BaseModel):
    """Index row without task output payloads."""

    id: str
    playbook_slug: str
    status: str
    created_at: str
    updated_at: str
    error_message: str | None = None
    task_counts: TaskCounts = Field(default_factory=TaskCounts)


class WorkflowRunListOut(BaseModel):
    runs: list[WorkflowRunSummaryOut]
    total: int
    limit: int
    offset: int


class PlaybookOut(BaseModel):
    slug: str
    name: str
    version: str
    task_count: int
    runnable: bool


class PlaybookListOut(BaseModel):
    playbooks: list[PlaybookOut]


class RfpAnswerEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    response: str | None = Field(default=None, max_length=8000)
    status: str | None = Field(default=None, max_length=32)


class TaskApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edits: dict[str, Any] = Field(default_factory=dict)
    answers: list[RfpAnswerEdit] | None = Field(default=None, max_length=200)


class TaskRejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="", max_length=2000)
