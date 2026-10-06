"""End to end on a throwaway embedded Postgres: migrate, store, normalize, import, compare.
Skipped automatically if `pgserver` is not installed (pip install pgserver)."""
import csv
import os
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
import psycopg  # noqa: E402

HTML = (Path(__file__).parent / "fixtures" / "nansha_eastbound.html").read_text()


@pytest.fixture()
def db(tmp_path, monkeypatch):
    server = pgserver.get_server(tmp_path / "pg", cleanup_mode="stop")
    monkeypatch.setenv("DATABASE_URL", server.get_uri())
    monkeypatch.setenv("USER_AGENT", "test (contact: t@example.org)")
    yield server.get_uri()
    server.cleanup()


def test_full_flow(db, tmp_path):
    from app import collect, import_observations, migrate, normalize
    from app.parsers import nansha
    from app.sources import Source

    migrate.main()
    migrate.main()  # idempotent

    with psycopg.connect(db) as conn:
        raw_id, fetched = conn.execute(
            "INSERT INTO raw_payloads (source, content_hash, table_hash, content) VALUES ('t','h',%s,%s)"
            " RETURNING id, fetched_at", (nansha.table_hash(HTML), HTML)).fetchone()
        collect.insert_snapshots(conn, raw_id, "t", fetched, nansha.parse(HTML))
        conn.execute("UPDATE raw_payloads SET parse_ok=TRUE WHERE id=%s", (raw_id,))
        conn.commit()
        normalize.main()
        normalize.main()  # nothing new the second time
        assert conn.execute("SELECT count(*) FROM services").fetchone()[0] == 4
        assert conn.execute("SELECT name FROM ports WHERE name='Southampton'").fetchone()
        assert not conn.execute("SELECT 1 FROM ports WHERE name='Southhampton'").fetchone()
        nominal = conn.execute(
            "SELECT outbound_days FROM current_nominal WHERE port='Barcelona' AND row_key LIKE 'AE11%'").fetchone()[0]

    path = tmp_path / "obs.csv"
    cols = ["source", "carrier_code", "carrier_service_code", "vessel", "imo", "voyage", "origin_port",
            "dest_port", "cutoff_at", "scheduled_departure", "estimated_departure", "actual_departure",
            "scheduled_arrival", "estimated_arrival", "actual_arrival", "route_variant", "note"]
    row = dict.fromkeys(cols, "")
    row.update(source="manual-maersk", carrier_code="MSK", carrier_service_code="AE11", vessel="TEST",
               origin_port="Nansha", dest_port="Barcelona", actual_departure="2026-09-01T12:00+08:00",
               actual_arrival="2026-10-10T12:00+02:00", route_variant="cape")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        w.writerow(row)
    import_observations.main(str(path))

    with psycopg.connect(db) as conn:
        d = conn.execute("SELECT direction, nominal_days, observed_days, gap_days, route_variant, over_threshold"
                         " FROM theory_vs_practice").fetchone()
    assert d[0] == "outbound" and d[1] == nominal and d[2] == 39 and d[3] == 39 - nominal
    assert d[4] == "cape" and d[5] is True

    bad = tmp_path / "bad.csv"
    bad.write_text(path.read_text().replace("Barcelona", "Barcelnoa"))
    with pytest.raises(SystemExit):
        import_observations.main(str(bad))
