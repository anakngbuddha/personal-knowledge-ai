"""Run schema migrations with an administrator DATABASE_URL before app deployment.

The web service connects with a restricted NOBYPASSRLS role and never performs DDL.
"""

from app.db.bootstrap import ensure_schema


def main() -> None:
    ensure_schema()


if __name__ == "__main__":
    main()
