"""Per-user rate limiting and per-org token budget enforcement.

Project_Plan.md L195: "Cost controls: per-org token budgets, per-user rate
limits, streaming responses."

Rate limiting: sliding window counter in memory. Sufficient at 50 users;
Redis upgrade path exists if needed.

Token budgets: checked before generation, incremented after. A limit of 0
means unlimited. Budget is per calendar month.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from threading import Lock

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import GenerationRateLimited, TokenBudgetExhausted
from app.core.logging import get_logger
from app.db.models import TokenBudget

logger = get_logger(__name__)

# ── in-memory sliding window rate limiter ───────────────────────────────

_rate_lock = Lock()
_request_times: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(user_id: uuid.UUID | None, rpm: int | None = None) -> None:
    """Enforce per-user requests-per-minute limit.

    Raises GenerationRateLimited if the user has exceeded the limit.
    """
    if user_id is None:
        return  # owner_dev mode — no user to rate limit

    rpm = rpm if rpm is not None else settings.generation_rate_limit_rpm
    if rpm <= 0:
        return  # unlimited

    key = str(user_id)
    now = time.monotonic()
    window = 60.0  # 1 minute

    with _rate_lock:
        times = _request_times[key]
        # Prune expired entries
        cutoff = now - window
        _request_times[key] = [t for t in times if t > cutoff]
        times = _request_times[key]

        if len(times) >= rpm:
            logger.warning("rate limit exceeded for user %s (%d/%d rpm)", user_id, len(times), rpm)
            raise GenerationRateLimited(
                f"Rate limit exceeded: {rpm} requests per minute. Please wait."
            )

        times.append(now)


def reset_rate_limit(user_id: uuid.UUID) -> None:
    """Reset rate limit for a user. Used in tests."""
    key = str(user_id)
    with _rate_lock:
        _request_times.pop(key, None)


# ── per-org token budget ────────────────────────────────────────────────

def _current_month() -> date:
    """First day of the current month."""
    today = datetime.now(timezone.utc).date()
    return today.replace(day=1)


def check_token_budget(db: Session, org_id: uuid.UUID) -> None:
    """Check if the org has remaining token budget. Raises if exhausted.

    A limit of 0 means unlimited. If no budget row exists, the org is unlimited.
    """
    tpd = settings.generation_rate_limit_tpd
    if tpd <= 0:
        return  # globally unlimited

    month = _current_month()
    budget = db.scalars(
        select(TokenBudget).where(
            TokenBudget.org_id == org_id,
            TokenBudget.month == month,
        )
    ).first()

    if budget is None:
        return  # no budget row = unlimited

    if budget.prompt_token_limit > 0:
        if budget.prompt_tokens_used >= budget.prompt_token_limit:
            raise TokenBudgetExhausted(
                f"Prompt token budget exhausted for this month "
                f"({budget.prompt_tokens_used:,}/{budget.prompt_token_limit:,})"
            )

    if budget.completion_token_limit > 0:
        if budget.completion_tokens_used >= budget.completion_token_limit:
            raise TokenBudgetExhausted(
                f"Completion token budget exhausted for this month "
                f"({budget.completion_tokens_used:,}/{budget.completion_token_limit:,})"
            )

    total_used = budget.prompt_tokens_used + budget.completion_tokens_used
    total_limit = budget.prompt_token_limit + budget.completion_token_limit
    if total_limit > 0 and total_used >= total_limit:
        raise TokenBudgetExhausted(
            f"Total token budget exhausted ({total_used:,}/{total_limit:,})"
        )


def record_token_usage(
    db: Session,
    org_id: uuid.UUID,
    prompt_tokens: int,
    completion_tokens: int,
) -> None:
    """Increment the org's token usage for the current month.

    Creates the budget row if it doesn't exist (with limit=0, meaning unlimited
    until an admin sets a limit).
    """
    month = _current_month()
    budget = db.scalars(
        select(TokenBudget).where(
            TokenBudget.org_id == org_id,
            TokenBudget.month == month,
        )
    ).first()

    if budget is None:
        budget = TokenBudget(
            org_id=org_id,
            month=month,
            prompt_tokens_used=prompt_tokens,
            completion_tokens_used=completion_tokens,
        )
        db.add(budget)
    else:
        budget.prompt_tokens_used += prompt_tokens
        budget.completion_tokens_used += completion_tokens

    db.commit()
    logger.debug(
        "token usage for org %s month %s: +%d prompt, +%d completion",
        org_id, month, prompt_tokens, completion_tokens,
    )
