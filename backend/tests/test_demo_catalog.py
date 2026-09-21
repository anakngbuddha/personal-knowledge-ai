"""3.3 The sample catalog is off by default, and anything it writes is marked.

No database needed: the switch is checked before the session is touched, and the
stamping rule is a pure function of "what was here before".
"""

import uuid

import pytest

from app.catalog import demo
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Document, Product, SellingContext


class _Row:
    def __init__(self, is_demo: bool = False):
        self.id = uuid.uuid4()
        self.is_demo = is_demo


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _StubSession:
    """Just enough Session to exercise the stamping rule."""

    def __init__(self, rows):
        self._rows = rows

    def scalars(self, statement):  # noqa: ARG002 - the statement is not the point here
        return _Scalars(self._rows)


def test_sample_catalog_is_off_unless_asked_for():
    assert settings.demo_seed_catalog is False
    assert demo.demo_catalog_enabled() is False


def test_seeding_refuses_in_plain_words_when_the_switch_is_off():
    with pytest.raises(AppError) as excinfo:
        demo.seed_demo_catalog(None, uuid.uuid4(), uuid.uuid4())
    assert excinfo.value.status_code == 404
    assert "Import your own product list" in excinfo.value.message
    # The wording is what a salesperson sees, so it stays free of jargon.
    for word in ("seed", "flag", "env"):
        assert word not in excinfo.value.message.lower()


def test_only_rows_the_seed_created_are_marked_as_sample_material():
    mine = _Row()
    theirs = _Row()
    session = _StubSession([mine, theirs])

    marked = demo.stamp_new_rows(session, Product, uuid.uuid4(), before={mine.id})

    assert marked == 1
    assert mine.is_demo is False, "a product a person added must never be called sample material"
    assert theirs.is_demo is True


def test_stamping_is_idempotent():
    already = _Row(is_demo=True)
    session = _StubSession([already])
    assert demo.stamp_new_rows(session, Product, uuid.uuid4(), before=set()) == 0


def test_every_table_the_sample_writes_can_be_marked():
    assert set(demo.DEMO_MODELS) == {Product, SellingContext, Document}
    for model in demo.DEMO_MODELS:
        assert hasattr(model, "is_demo"), f"{model.__tablename__} needs an is_demo column"
        assert hasattr(model, "workspace_id")
