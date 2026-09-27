"""One document-authorization predicate for every path that reads a document.

Search has always filtered candidates through `build_predicate_set` (tenant,
sensitivity ceiling, account grants, approval state, corpus rules). Direct reads
(MCP `read_document`, `list_documents`, `resources/list`) used to check only
`org_id`, so a low-privilege caller who knew an id could read what search hides.
Everything that loads a document for a principal goes through here instead.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import Document
from app.retrieval.permissions import build_predicate_set
from app.retrieval.sql import compile_predicate_set
from app.security.principal import Principal


def document_access_clause(principal: Principal) -> ColumnElement:
    """The same WHERE clause search uses for its candidate set."""
    return compile_predicate_set(build_predicate_set(principal))


def readable_documents(principal: Principal) -> Select:
    return select(Document).where(document_access_clause(principal))


def get_readable_document(db: Session, principal: Principal, document_id: uuid.UUID) -> Document | None:
    return db.scalars(readable_documents(principal).where(Document.id == document_id)).first()
