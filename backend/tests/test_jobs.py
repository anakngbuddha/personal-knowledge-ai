"""Retry schedule and the worker's failure classification."""

import pytest

from app.core.errors import ExtractionError, MalwareDetected, ProviderRateLimited, UnsafeFile
from app.jobs.backoff import backoff_seconds
from app.jobs.worker import PERMANENT_FAILURES


def test_backoff_grows_exponentially_and_is_capped():
    delays = [backoff_seconds(n, base=15, maximum=900) for n in range(1, 8)]
    assert delays[:4] == [15, 30, 60, 120]
    assert all(later >= earlier for earlier, later in zip(delays, delays[1:], strict=False))
    assert max(delays) == 900


def test_jitter_is_deterministic_so_a_retry_schedule_is_reproducible():
    first = backoff_seconds(3, base=15, maximum=900, jitter_key="job-abc")
    second = backoff_seconds(3, base=15, maximum=900, jitter_key="job-abc")
    assert first == second


def test_jitter_spreads_different_jobs_apart():
    values = {backoff_seconds(1, base=60, maximum=900, jitter_key=f"job-{n}") for n in range(20)}
    assert len(values) > 5, "jitter should spread jobs, not collapse them"


def test_jitter_never_exceeds_the_nominal_delay():
    for attempt in range(1, 6):
        nominal = backoff_seconds(attempt, base=15, maximum=900)
        jittered = backoff_seconds(attempt, base=15, maximum=900, jitter_key="x")
        assert 0.7 * nominal <= jittered <= nominal


def test_attempts_are_one_based():
    with pytest.raises(ValueError):
        backoff_seconds(0, base=15, maximum=900)


def test_bad_files_are_never_retried_but_provider_failures_are():
    """Retrying a corrupt PDF four times just burns the single worker."""
    for error in (ExtractionError, UnsafeFile, MalwareDetected):
        assert issubclass(error, PERMANENT_FAILURES)
    assert not issubclass(ProviderRateLimited, PERMANENT_FAILURES)
