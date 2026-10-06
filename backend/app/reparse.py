"""Re-run the parser on stored raw payloads (after fixing a parser bug).

  python -m app.reparse          # only payloads whose parse failed
  python -m app.reparse --all    # every payload (replaces its parsed rows)
"""
import sys

import psycopg

from .collect import insert_snapshots
from .config import database_url
from .parsers import nansha


def main() -> None:
    redo_all = "--all" in sys.argv
    with psycopg.connect(database_url()) as conn:
        where = "" if redo_all else "WHERE parse_ok IS NOT TRUE"
        for raw_id, source, fetched_at, content in conn.execute(
            f"SELECT id, source, fetched_at, content FROM raw_payloads {where} ORDER BY id"
        ).fetchall():
            try:
                rows = nansha.parse(content)
            except Exception as exc:
                conn.execute("UPDATE raw_payloads SET parse_ok=FALSE, parse_error=%s WHERE id=%s",
                             (str(exc), raw_id))
                conn.commit()
                print(f"raw {raw_id}: still failing: {exc}")
                continue
            conn.execute("DELETE FROM schedule_snapshots WHERE raw_id=%s", (raw_id,))
            insert_snapshots(conn, raw_id, source, fetched_at, rows)
            conn.execute("UPDATE raw_payloads SET parse_ok=TRUE, parse_error=NULL WHERE id=%s", (raw_id,))
            conn.commit()
            print(f"raw {raw_id}: {len(rows)} rows")


if __name__ == "__main__":
    main()
