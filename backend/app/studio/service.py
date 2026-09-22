"""Briefing, FAQ, compare, and suggested questions from stored summaries.

The file is not read again. Helpers use the title, vendor, summary, and key facts
already saved by the understand step.
"""

from __future__ import annotations

import json
import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Document
from app.llm.factory import get_llm_provider
from app.notes import service as notes_service
from app.studio.prompts import STUDIO_PROMPT_VERSION, STUDIO_SYSTEM_PROMPT

KINDS = ("briefing", "faq", "compare")
_SENTENCE = re.compile(r"[^.!?]+[.!?]?")


def _title(document: Document) -> str:
    return (document.title or document.original_filename or "Untitled source").strip()


def _summary(document: Document) -> str:
    text = (document.summary or "").strip()
    return text or "No summary has been written for this source yet."


def _facts(document: Document) -> list[str]:
    lines: list[str] = []
    for fact in document.key_facts or []:
        if isinstance(fact, dict) and fact.get("label") and fact.get("value"):
            lines.append(f"{fact['label']}: {fact['value']}")
    return lines


def load_sources(
    db: Session, *, org_id: uuid.UUID, workspace_id: uuid.UUID, document_ids: list[uuid.UUID]
) -> list[Document]:
    if not document_ids:
        raise AppError(status_code=400, code="studio_no_sources", message="Pick at least one source.")
    if len(document_ids) > 12:
        raise AppError(status_code=400, code="studio_too_many", message="Pick at most 12 sources.")
    rows = list(
        db.scalars(
            select(Document).where(
                Document.id.in_(document_ids),
                Document.org_id == org_id,
                Document.workspace_id == workspace_id,
                Document.is_current.is_(True),
                Document.is_demo.is_(False),
            )
        )
    )
    by_id = {row.id: row for row in rows}
    ordered = [by_id[item] for item in document_ids if item in by_id]
    if len(ordered) != len(set(document_ids)):
        raise AppError(status_code=404, code="studio_source_missing", message="One of those sources was not found.")
    return ordered


def heuristic_questions(document: Document) -> list[str]:
    title = _title(document)
    questions: list[str] = []
    for match in _SENTENCE.findall(document.summary or ""):
        sentence = " ".join(match.split()).strip(" .")
        if len(sentence) < 12:
            continue
        questions.append(f"What should I tell a customer about this: {sentence[:160]}?")
        if len(questions) == 3:
            break
    for line in _facts(document)[:3]:
        label = line.split(":", 1)[0].strip()
        if label:
            questions.append(f"What is the {label.lower()} on {title}?")
    if not questions:
        questions.append(f"What does {title} say that I can use in a proposal?")
    return questions[:5]


def _parse_question_list(text: str) -> list[str] | None:
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    questions = [str(item).strip() for item in payload if str(item).strip()]
    return questions[:5] or None


def suggested_questions(db: Session, document: Document, *, provider=None) -> list[str]:
    meta = dict(document.doc_metadata or {})
    cached = meta.get("suggested_questions")
    if isinstance(cached, list) and cached:
        return [str(item) for item in cached]
    provider = provider or get_llm_provider()
    questions = heuristic_questions(document)
    try:
        answer = provider.generate_grounded_answer(
            f"Suggest questions for {_title(document)}",
            [{"text": _summary(document), "citation": _title(document)}],
            system_prompt=(
                f"{STUDIO_SYSTEM_PROMPT}\nReply with a JSON array of up to 5 short questions. "
                f"Prompt version {STUDIO_PROMPT_VERSION}."
            ),
        )
        parsed = _parse_question_list(getattr(answer, "text", "") or "")
        if parsed and not str(getattr(provider, "model_id", "")).startswith("fake"):
            questions = parsed
    except Exception:
        pass
    meta["suggested_questions"] = questions
    document.doc_metadata = meta
    db.commit()
    db.refresh(document)
    return questions


def heuristic_markdown(kind: str, documents: list[Document]) -> str:
    blocks: list[str] = []
    if kind == "briefing":
        blocks.append("# Briefing")
        for document in documents:
            title = _title(document)
            facts = _facts(document)
            body = _summary(document)
            if facts:
                body = body + " " + " ".join(facts)
            blocks.append(f"## {title}\n\nFrom your documents ({title}): {body}")
    elif kind == "faq":
        blocks.append("# FAQ")
        for document in documents:
            title = _title(document)
            blocks.append(
                f"**What should I know about {title}?**\n\nFrom your documents ({title}): {_summary(document)}"
            )
    else:
        blocks.append("# Compare")
        names = ", ".join(_title(document) for document in documents)
        blocks.append(f"Agreements, differences, and conflicts across {names}.")
        for document in documents:
            title = _title(document)
            blocks.append(f"## {title}\n\nFrom your documents ({title}): {_summary(document)}")
        blocks.append(
            "From general product knowledge: confirm compatibility with the vendor before you promise it."
        )
    return "\n\n".join(blocks).strip() + "\n"


def run_studio(
    db: Session,
    *,
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    kind: str,
    document_ids: list[uuid.UUID],
    notebook_id: uuid.UUID | None = None,
    save_as_note: bool = False,
    created_by: uuid.UUID | None = None,
    provider=None,
) -> dict:
    if kind not in KINDS:
        raise AppError(status_code=400, code="studio_kind", message="Choose a briefing, an FAQ, or a comparison.")
    documents = load_sources(db, org_id=org_id, workspace_id=workspace_id, document_ids=document_ids)
    if kind == "compare" and len(documents) < 2:
        raise AppError(
            status_code=400,
            code="studio_compare_needs_two",
            message="Pick at least two sources to compare.",
        )
    provider = provider or get_llm_provider()
    context = [
        {
            "text": f"{_title(document)}\n{_summary(document)}\n" + "\n".join(_facts(document)),
            "citation": _title(document),
            "document_id": str(document.id),
        }
        for document in documents
    ]
    drafted = ""
    try:
        answer = provider.generate_grounded_answer(
            f"Write a {kind} for a salesperson.",
            context,
            system_prompt=f"{STUDIO_SYSTEM_PROMPT}\nPrompt version {STUDIO_PROMPT_VERSION}.",
        )
        drafted = (getattr(answer, "text", "") or "").strip()
    except Exception:
        drafted = ""
    # The offline provider cites chunks; it does not write a briefing. Keep the
    # summary-based piece for that provider so tests stay deterministic.
    if drafted and not str(getattr(provider, "model_id", "")).startswith("fake"):
        markdown = drafted if drafted.endswith("\n") else drafted + "\n"
    else:
        markdown = heuristic_markdown(kind, documents)
    titles = [_title(document) for document in documents]
    note_id = None
    if save_as_note:
        label = {"briefing": "Briefing", "faq": "FAQ", "compare": "Comparison"}[kind]
        note = notes_service.create_note(
            db,
            org_id=org_id,
            workspace_id=workspace_id,
            title=f"{label}: {titles[0]}"[:512],
            body=markdown,
            created_by=created_by,
            notebook_id=notebook_id,
        )
        note_id = str(note.id)
    return {"markdown": markdown, "source_titles": titles, "note_id": note_id}
