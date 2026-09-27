"""Renewable queue leases (audit finding 13)."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.jobs.lease import LeaseKeeper


def test_lease_keeper_renews_until_stopped():
    calls: list[float] = []

    def renew() -> bool:
        calls.append(time.monotonic())
        return True

    with LeaseKeeper(renew, interval=0.05) as keeper:
        time.sleep(0.3)
    count = len(calls)
    time.sleep(0.15)
    assert count >= 3
    assert len(calls) == count  # stopped on exit
    assert keeper.lost is False


def test_lease_keeper_stops_when_the_lease_is_lost():
    calls: list[int] = []

    def renew() -> bool:
        calls.append(1)
        return False

    with LeaseKeeper(renew, interval=0.05) as keeper:
        time.sleep(0.3)
    assert keeper.lost is True
    assert len(calls) == 1


@pytest.mark.requires_db
def test_long_job_is_not_reclaimed_while_renewing_and_late_finish_does_not_clobber(db, monkeypatch):
    from app.db.models import IngestionJob, JobStatus, Organization
    from app.db.session import system_session
    from app.jobs import queue

    org = Organization(id=uuid.uuid4(), slug=f"lease-{uuid.uuid4().hex[:8]}", name="Lease")
    db.add(org)
    db.commit()
    job = queue.enqueue_freshness_crawl(db, vendor_source_id=uuid.uuid4(), org_id=org.id)
    job.run_after = datetime(2000, 1, 1, tzinfo=timezone.utc)
    db.commit()

    claimed = queue.claim(db, "worker-a")
    assert claimed is not None and claimed.id == job.id
    monkeypatch.setattr(settings, "job_stale_seconds", 1.0)

    def renew() -> bool:
        s = system_session()
        try:
            return queue.heartbeat(s, job.id, "worker-a")
        finally:
            s.close()

    def state():
        s = system_session()
        try:
            return s.execute(
                select(IngestionJob.status, IngestionJob.locked_by).where(IngestionJob.id == job.id)
            ).one()
        finally:
            s.close()

    def reap():
        s = system_session()
        try:
            queue.reap_stale(s)  # what worker B runs before every claim
        finally:
            s.close()

    try:
        with LeaseKeeper(renew, interval=0.2) as keeper:
            time.sleep(1.6)
            reap()
            assert tuple(state()) == (JobStatus.RUNNING, "worker-a")
            assert keeper.renewals >= 3

        time.sleep(1.3)  # stop renewing: the lease must now expire
        reap()
        assert state()[0] == JobStatus.FAILED

        # Worker B takes the job; worker A's late result must not overwrite it.
        s = system_session()
        try:
            s.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job.id)
                .values(status=JobStatus.RUNNING, locked_by="worker-b", locked_at=datetime.now(timezone.utc))
            )
            s.commit()
        finally:
            s.close()
        queue.succeed(db, claimed)
        assert tuple(state()) == (JobStatus.RUNNING, "worker-b")
    finally:
        s = system_session()
        try:
            s.execute(update(IngestionJob).where(IngestionJob.id == job.id).values(status=JobStatus.DEAD, locked_by=None))
            s.commit()
        finally:
            s.close()
