"""Apply backend/migrations/*.sql in order. Safe to run on every deploy."""
from pathlib import Path

import psycopg

from .config import database_url

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def main() -> None:
    with psycopg.connect(database_url()) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        done = {r[0] for r in conn.execute("SELECT filename FROM schema_migrations")}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if path.name in done:
                continue
            conn.execute(path.read_text())
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
            print(f"applied {path.name}")
    print("migrations up to date")


if __name__ == "__main__":
    main()
