"""Python handler registry. Playbook YAML names handlers; it cannot define them."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import TaskExecution, WorkflowRun
from app.security.principal import Principal


@dataclass
class HandlerContext:
    db: Session
    run: WorkflowRun
    task: TaskExecution
    principal: Principal
    upstream: dict[str, Any]


Handler = Callable[[HandlerContext, dict[str, Any]], dict[str, Any]]

_HANDLERS: dict[str, Handler] = {}


def register(name: str):
    def decorator(fn: Handler) -> Handler:
        _HANDLERS[name] = fn
        return fn

    return decorator


def get_handler(name: str) -> Handler:
    handler = _HANDLERS.get(name)
    if handler is None:
        raise AppError(
            status_code=500,
            code="unknown_handler",
            message=f"no Python handler registered for {name!r}",
        )
    return handler


@register("fixture.alpha")
def fixture_alpha(ctx: HandlerContext, payload: dict[str, Any]) -> dict[str, Any]:
    return {"value": 1, "echo": payload}


@register("fixture.beta")
def fixture_beta(ctx: HandlerContext, payload: dict[str, Any]) -> dict[str, Any]:
    prior = (ctx.upstream.get("alpha") or {}).get("value", 0)
    return {"value": prior + 1}


@register("fixture.gamma")
def fixture_gamma(ctx: HandlerContext, payload: dict[str, Any]) -> dict[str, Any]:
    prior = (ctx.upstream.get("beta") or {}).get("value", 0)
    return {"value": prior + 1, "done": True}


@register("fixture.gate")
def fixture_gate(ctx: HandlerContext, payload: dict[str, Any]) -> dict[str, Any]:
    return {"draft": ctx.upstream, "needs_review": True}


import app.playbooks.rfp  # noqa: E402,F401 - register rfp.* handlers
import app.playbooks.phase8  # noqa: E402,F401 - register phase 8 handlers
