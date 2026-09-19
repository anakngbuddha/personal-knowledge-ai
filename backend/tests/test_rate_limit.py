"""Tests for per-user rate limiting and per-org token budgets.

Project_Plan.md L195: "Cost controls: per-org token budgets, per-user rate
limits, streaming responses."
"""

import uuid
from datetime import date
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import GenerationRateLimited, TokenBudgetExhausted
from app.db.models import Base, Organization, TokenBudget
from app.generation.rate_limit import (
    _current_month,
    check_rate_limit,
    check_token_budget,
    record_token_usage,
    reset_rate_limit,
)


@pytest.fixture
def budget_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            TokenBudget.__table__,
        ],
    )
    SessionClass = sessionmaker(bind=engine)
    session = SessionClass()

    org = Organization(id=uuid.uuid4(), slug=f"budget-test-{uuid.uuid4().hex[:8]}", name="Budget Test Org")
    session.add(org)
    session.commit()

    session.org_id = org.id
    try:
        yield session
    finally:
        session.close()


def test_rate_limit_sliding_window():
    user_id = uuid.uuid4()
    reset_rate_limit(user_id)

    # Allowed up to limit (e.g. rpm=3)
    check_rate_limit(user_id, rpm=3)
    check_rate_limit(user_id, rpm=3)
    check_rate_limit(user_id, rpm=3)

    # 4th request within the minute fails
    with pytest.raises(GenerationRateLimited):
        check_rate_limit(user_id, rpm=3)

    # Reset clears the limit
    reset_rate_limit(user_id)
    check_rate_limit(user_id, rpm=3)


def test_rate_limit_none_user_and_disabled():
    # user_id is None (owner_dev mode) -> never rate limited
    check_rate_limit(None, rpm=1)
    check_rate_limit(None, rpm=1)

    # rpm <= 0 -> unlimited
    uid = uuid.uuid4()
    check_rate_limit(uid, rpm=0)
    check_rate_limit(uid, rpm=0)


def test_token_budget_unlimited_by_default(budget_db: Session):
    org_id = budget_db.org_id
    # No budget row exists -> unlimited
    check_token_budget(budget_db, org_id)


def test_token_budget_prompt_limit_exhausted(budget_db: Session):
    org_id = budget_db.org_id
    month = _current_month()

    budget = TokenBudget(
        org_id=org_id,
        month=month,
        prompt_tokens_used=1000,
        prompt_token_limit=1000,
        completion_tokens_used=100,
        completion_token_limit=5000,
    )
    budget_db.add(budget)
    budget_db.commit()

    with pytest.raises(TokenBudgetExhausted) as excinfo:
        check_token_budget(budget_db, org_id)
    assert "Prompt token budget exhausted" in str(excinfo.value)


def test_token_budget_completion_limit_exhausted(budget_db: Session):
    org_id = budget_db.org_id
    month = _current_month()

    budget = TokenBudget(
        org_id=org_id,
        month=month,
        prompt_tokens_used=500,
        prompt_token_limit=2000,
        completion_tokens_used=1000,
        completion_token_limit=1000,
    )
    budget_db.add(budget)
    budget_db.commit()

    with pytest.raises(TokenBudgetExhausted) as excinfo:
        check_token_budget(budget_db, org_id)
    assert "Completion token budget exhausted" in str(excinfo.value)


def test_record_token_usage(budget_db: Session):
    org_id = budget_db.org_id
    month = _current_month()

    # Records initial usage and creates budget row
    record_token_usage(budget_db, org_id, prompt_tokens=250, completion_tokens=50)

    row = budget_db.scalars(
        select(TokenBudget).where(TokenBudget.org_id == org_id, TokenBudget.month == month)
    ).first()
    assert row is not None
    assert row.prompt_tokens_used == 250
    assert row.completion_tokens_used == 50

    # Increments existing row
    record_token_usage(budget_db, org_id, prompt_tokens=100, completion_tokens=25)
    budget_db.refresh(row)
    assert row.prompt_tokens_used == 350
    assert row.completion_tokens_used == 75
