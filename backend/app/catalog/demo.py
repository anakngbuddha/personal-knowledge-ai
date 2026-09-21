"""3.3 The sample catalog is a demo, not a default.

The previous build seeded the same two sample vendors into every workspace. That is
wrong twice over: a new account opens the map and finds products it does not sell, and
an answer can quote sample collateral as if it were the customer's own material. So:

* the sample catalog only loads when ``DEMO_SEED_CATALOG`` is on;
* everything it creates is stamped ``is_demo``, including any collateral it writes;
* retrieval drops demo sources, so a sample document can never reach an answer.

The stamping is done by diffing the tables around the seed instead of threading a flag
through every row the seed builds. That keeps ``seed_phase4_catalog`` untouched, which
matters: the golden and eval suites call it directly, in process, and were written
against exactly those fixtures.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models import Document, Product, SellingContext

logger = get_logger(__name__)

#: Plain words for the switch, so no screen has to invent its own.
DISABLED_MESSAGE = (
    "The sample product list is switched off. Import your own product list instead, "
    "or ask an admin to turn the sample on."
)

#: Every table the sample catalog writes into that someone could later mistake for
#: their own work. Each one carries an ``is_demo`` column.
DEMO_MODELS = (Product, SellingContext, Document)


def demo_catalog_enabled() -> bool:
    return bool(settings.demo_seed_catalog)


def seed_demo_catalog(db: Session, org_id: uuid.UUID, workspace_id: uuid.UUID) -> dict:
    """Load the sample catalog and stamp everything it created as demo material."""
    if not demo_catalog_enabled():
        raise AppError(DISABLED_MESSAGE, status_code=404, code="demo_catalog_disabled")

    from app.catalog.seeds import seed_phase4_catalog

    before = {model: _existing_ids(db, model, workspace_id) for model in DEMO_MODELS}
    counts = seed_phase4_catalog(db, org_id, workspace_id)

    stamped: dict[str, int] = {}
    for model in DEMO_MODELS:
        stamped[model.__tablename__] = stamp_new_rows(db, model, workspace_id, before[model])
    db.commit()

    logger.info("sample catalog loaded for workspace %s; stamped %s", workspace_id, stamped)
    result = dict(counts or {})
    result["marked_as_demo"] = stamped
    return result


def stamp_new_rows(db: Session, model, workspace_id: uuid.UUID, before: set) -> int:
    """Mark every row of ``model`` in this workspace that did not exist in ``before``.

    Rows a person created are identified by having been there already, which is why the
    caller has to take the snapshot first. Anything already stamped is left alone.
    """
    marked = 0
    for row in db.scalars(select(model).where(model.workspace_id == workspace_id)).all():
        if row.id in before or getattr(row, "is_demo", False):
            continue
        row.is_demo = True
        marked += 1
    return marked


def _existing_ids(db: Session, model, workspace_id: uuid.UUID) -> set:
    return set(db.scalars(select(model.id).where(model.workspace_id == workspace_id)).all())
