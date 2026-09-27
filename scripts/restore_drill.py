"""Run a disaster-recovery restore drill for the default organization.

Usage (from repo root, with DATABASE_URL set):

    python scripts/restore_drill.py
    python scripts/restore_drill.py --sla-seconds 120
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.db.models import Organization  # noqa: E402
from app.db.session import system_session  # noqa: E402
from app.ops.restore import run_restore_drill  # noqa: E402
from app.security.deps import get_or_create_default_org  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a logical restore drill within SLA")
    parser.add_argument("--org-slug", default=None, help="Organization slug (default org if omitted)")
    parser.add_argument("--sla-seconds", type=float, default=None)
    args = parser.parse_args()

    db = system_session()
    try:
        if args.org_slug:
            org = db.scalars(select(Organization).where(Organization.slug == args.org_slug)).first()
            if org is None:
                print(f"organization {args.org_slug!r} not found", file=sys.stderr)
                return 2
        else:
            org = get_or_create_default_org(db)
        drill = run_restore_drill(
            db,
            org_id=org.id,
            triggered_by=None,
            sla_seconds=args.sla_seconds,
        )
        print(
            f"restore drill {drill.id}: status={drill.status} "
            f"duration={drill.duration_seconds:.3f}s sla={drill.sla_seconds:.1f}s "
            f"within_sla={drill.within_sla}"
        )
        if drill.error_message:
            print(drill.error_message, file=sys.stderr)
        if drill.row_counts_after:
            print("restored counts:", drill.row_counts_after)
        return 0 if drill.status == "succeeded" and drill.within_sla else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
