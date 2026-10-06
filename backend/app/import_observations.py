"""Load manually checked carrier data (Maersk / MSC sites) from a CSV, all-or-nothing.

  python -m app.import_observations ../data/observations_template.csv

Ports must already exist (they come from the Nansha page); unknown names are rejected
so a typo never creates a phantom port. Timestamps are ISO 8601, e.g. 2026-10-14T12:00+02:00.
"""
import csv
import sys
from datetime import datetime

import psycopg

from .config import database_url

TS = ["cutoff_at", "scheduled_departure", "estimated_departure", "actual_departure",
      "scheduled_arrival", "estimated_arrival", "actual_arrival"]


def ts(value: str):
    value = (value or "").strip()
    return datetime.fromisoformat(value) if value else None


def find_port(conn, name: str) -> int:
    row = conn.execute(
        "SELECT id FROM ports WHERE lower(name)=lower(%s) OR lower(%s) = ANY (SELECT lower(a) FROM unnest(aliases) a)",
        (name, name)).fetchone()
    if not row:
        raise ValueError(f"unknown port '{name}' (run app.normalize first, or add it to ports)")
    return row[0]


def main(path: str) -> None:
    with open(path, newline="", encoding="utf-8") as f, psycopg.connect(database_url()) as conn:
        count = 0
        for line, r in enumerate(csv.DictReader(f), start=2):
            try:
                svc = conn.execute(
                    "SELECT service_id FROM service_carriers WHERE carrier_code=%s AND carrier_service_code=%s",
                    (r["carrier_code"].strip(), r["carrier_service_code"].strip())).fetchone()
                if not svc:
                    raise ValueError(f"unknown service {r['carrier_code']}/{r['carrier_service_code']}")
                conn.execute(
                    "INSERT INTO voyage_observations (source, service_id, carrier_code, carrier_service_code,"
                    " vessel, imo, voyage, origin_port_id, dest_port_id, cutoff_at, scheduled_departure,"
                    " estimated_departure, actual_departure, scheduled_arrival, estimated_arrival, actual_arrival,"
                    " route_variant, note) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (r["source"].strip() or "manual", svc[0], r["carrier_code"].strip(), r["carrier_service_code"].strip(),
                     r["vessel"].strip() or None, r["imo"].strip() or None, r["voyage"].strip() or None,
                     find_port(conn, r["origin_port"]), find_port(conn, r["dest_port"]),
                     *[ts(r[c]) for c in TS], (r["route_variant"].strip() or "unknown"), r["note"].strip() or None))
                count += 1
            except Exception as exc:
                conn.rollback()
                sys.exit(f"line {line}: {exc}. Nothing was imported.")
        conn.commit()
    print(f"imported {count} observation(s)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
