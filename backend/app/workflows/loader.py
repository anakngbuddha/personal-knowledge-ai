"""Playbook YAML loader. YAML may describe graphs, never code."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from app.core.errors import AppError


@dataclass(frozen=True)
class PlaybookTask:
    slug: str
    handler: str
    depends_on: tuple[str, ...] = ()
    gate: str | None = None


@dataclass(frozen=True)
class Playbook:
    slug: str
    name: str
    version: str
    tasks: tuple[PlaybookTask, ...]
    path: str = ""

    def task_by_slug(self, slug: str) -> PlaybookTask:
        for task in self.tasks:
            if task.slug == slug:
                return task
        raise KeyError(slug)


def playbooks_root() -> Path:
    return Path(__file__).resolve().parents[3] / "playbooks"


def _detect_cycles(tasks: list[PlaybookTask]) -> list[str]:
    adj = {task.slug: list(task.depends_on) for task in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()
    cycles: list[str] = []

    def dfs(node: str, stack: list[str]) -> None:
        if node in visiting:
            cycles.append(" -> ".join(stack[stack.index(node):] + [node]))
            return
        if node in visited:
            return
        visiting.add(node)
        for dep in adj.get(node, []):
            dfs(dep, stack + [node])
        visiting.remove(node)
        visited.add(node)

    for slug in adj:
        dfs(slug, [])
    return cycles


def parse_playbook(raw: dict, *, path: str = "") -> Playbook:
    slug = str(raw.get("slug") or "").strip()
    if not slug:
        raise AppError(status_code=400, code="invalid_playbook", message="playbook slug is required")
    tasks_raw = raw.get("tasks") or []
    if not isinstance(tasks_raw, list) or not tasks_raw:
        raise AppError(status_code=400, code="invalid_playbook", message="playbook must declare tasks")
    tasks: list[PlaybookTask] = []
    seen: set[str] = set()
    for item in tasks_raw:
        task_slug = str(item.get("slug") or "").strip()
        handler = str(item.get("handler") or "").strip()
        if not task_slug or not handler:
            raise AppError(status_code=400, code="invalid_playbook", message="each task needs slug and handler")
        if task_slug in seen:
            raise AppError(status_code=400, code="invalid_playbook", message=f"duplicate task slug {task_slug}")
        seen.add(task_slug)
        depends = item.get("depends_on") or []
        if not isinstance(depends, list):
            raise AppError(status_code=400, code="invalid_playbook", message="depends_on must be a list")
        gate = item.get("gate")
        if gate is not None:
            gate = str(gate)
            if gate != "human_approval":
                raise AppError(status_code=400, code="invalid_playbook", message=f"unsupported gate {gate}")
        tasks.append(PlaybookTask(task_slug, handler, tuple(str(d) for d in depends), gate))
    unknown_deps = [dep for task in tasks for dep in task.depends_on if dep not in seen]
    if unknown_deps:
        raise AppError(status_code=400, code="invalid_playbook", message=f"unknown depends_on: {unknown_deps}")
    cycles = _detect_cycles(tasks)
    if cycles:
        raise AppError(status_code=400, code="invalid_playbook", message=f"depends_on cycle: {cycles[0]}")
    return Playbook(slug, str(raw.get("name") or slug), str(raw.get("version") or "1.0"), tuple(tasks), path)


@lru_cache
def load_playbook(slug: str) -> Playbook:
    root = playbooks_root()
    matches = list(root.rglob("workflow.yaml")) + list(root.rglob("*.yaml"))
    for path in matches:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise AppError(status_code=400, code="invalid_playbook", message=f"invalid YAML in {path}") from exc
        if isinstance(raw, dict) and str(raw.get("slug") or "") == slug:
            return parse_playbook(raw, path=str(path))
    raise AppError(status_code=404, code="playbook_not_found", message=f"playbook {slug} not found")


RUNNABLE_PLAYBOOKS = frozenset({"rfp-response", "solution-composer", "incident-triage", "upgrade-impact"})


def _is_fixture_path(path: Path) -> bool:
    return any(part == "_fixtures" for part in path.parts)


def list_playbooks() -> list[Playbook]:
    root = playbooks_root()
    if not root.is_dir():
        return []
    found: dict[str, Playbook] = {}
    for path in sorted(root.rglob("workflow.yaml")):
        if _is_fixture_path(path):
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(raw, dict):
            continue
        try:
            playbook = parse_playbook(raw, path=str(path))
        except AppError:
            continue
        found.setdefault(playbook.slug, playbook)
    return list(found.values())
