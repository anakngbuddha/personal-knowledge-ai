"""Seed the database with the Phase 4 product catalog and typed graph.

Usage:
    python scripts/seed_catalog.py
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.catalog.seeds import seed_phase4_catalog  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.documents.service import get_or_create_default_workspace  # noqa: E402
from app.security.deps import get_or_create_default_org  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        org = get_or_create_default_org(db)
        workspace = get_or_create_default_workspace(db, org.id)

        print(f"Seeding catalog for org '{org.name}' in workspace '{workspace.name}'...")
        results = seed_phase4_catalog(db, org.id, workspace.id)
        print("\nSeed completed successfully:")
        print(f" - Capabilities seeded : {results['capabilities']}")
        print(f" - Products seeded     : {results['products']}")
        print(f" - Typed edges seeded  : {results['edges']}")
        print(f" - Architectures seeded: {results['architectures']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
