"""Create or upgrade the schema: extensions, tables, recorded migrations, indexes.

    cd backend && python ../scripts/init_db.py

Production (ENVIRONMENT=production) already runs this on API boot via
`app.db.bootstrap.ensure_schema`. This script is for local/Aiven setup and for
re-running by hand.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import settings  # noqa: E402
from app.db.bootstrap import ensure_schema  # noqa: E402


def main() -> None:
    ran = ensure_schema()
    print(f"embedding dimensions : {settings.gemini_embedding_dimensions}")
    print(f"fts configuration    : {settings.fts_config}")
    print(f"migrations applied   : {', '.join(ran) if ran else '(already up to date)'}")


if __name__ == "__main__":
    main()
