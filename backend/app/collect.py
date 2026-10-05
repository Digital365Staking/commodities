"""Daily collector: fetch each source, store raw first, parse, log the run.

Raw HTML is stored only when the table content changed (or the last parse failed),
but every run writes a run_log row with the table hash, so gaps are provable.
Exit code is 1 if any source failed, so the GitHub Action turns red and emails you.
"""
import hashlib
import sys
import urllib.robotparser
from urllib.parse import urlparse

import psycopg
import requests
from psycopg.types.json import Jsonb

from .config import database_url, user_agent
from .parsers import nansha
from .sources import SOURCES, Source


def robots_allows(url: str, ua: str) -> bool:
    parts = urlparse(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        resp = requests.get(f"{parts.scheme}://{parts.netloc}/robots.txt",
                            headers={"User-Agent": ua}, timeout=15)
        if resp.status_code != 200:
            return True
        rp.parse(resp.text.splitlines())
    except requests.RequestException:
        return True
    return rp.can_fetch(ua, url)


def insert_snapshots(conn, raw_id: int, source: str, fetched_at, rows: list[dict]) -> None:
    for r in rows:
        conn.execute(
            "INSERT INTO schedule_snapshots (raw_id, source, fetched_at, row_index, liners,"
            " service_codes, yard_closing, ports, inbound_days, outbound_days, raw_cells)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (raw_id, source, fetched_at, r["row_index"], r["liners"], r["service_codes"],
             r["yard_closing"], r["ports"], r["inbound"], r["outbound"], Jsonb(r["raw_cells"])),
        )


def collect_one(conn, src: Source, ua: str) -> None:
    run_id = conn.execute(
        "INSERT INTO run_log (source) VALUES (%s) RETURNING id", (src.name,)
    ).fetchone()[0]
    conn.commit()
    status = thash = None
    changed = False
    rows_parsed = 0
    error = None
    try:
        if not robots_allows(src.url, ua):
            raise RuntimeError("robots.txt disallows fetching this URL")
        resp = requests.get(src.url, headers={"User-Agent": ua}, timeout=30)
        status = resp.status_code
        resp.raise_for_status()
        html = resp.text

        try:
            thash = nansha.table_hash(html)
        except Exception:
            thash = None  # unparseable page: still store the raw payload below

        last = conn.execute(
            "SELECT table_hash, parse_ok FROM raw_payloads WHERE source=%s ORDER BY id DESC LIMIT 1",
            (src.name,),
        ).fetchone()
        changed = last is None or thash is None or last[0] != thash or last[1] is not True

        if changed:
            raw_id, fetched_at = conn.execute(
                "INSERT INTO raw_payloads (source, http_status, content_hash, table_hash, headers, content)"
                " VALUES (%s,%s,%s,%s,%s,%s) RETURNING id, fetched_at",
                (src.name, status, hashlib.sha256(html.encode()).hexdigest(), thash,
                 Jsonb(dict(resp.headers)), html),
            ).fetchone()
            conn.commit()  # raw is safe before any parsing
            try:
                rows = nansha.parse(html)
                insert_snapshots(conn, raw_id, src.name, fetched_at, rows)
                conn.execute("UPDATE raw_payloads SET parse_ok=TRUE WHERE id=%s", (raw_id,))
                rows_parsed = len(rows)
            except Exception as exc:
                conn.rollback()
                conn.execute("UPDATE raw_payloads SET parse_ok=FALSE, parse_error=%s WHERE id=%s",
                             (str(exc), raw_id))
                raise
    except Exception as exc:
        conn.rollback()
        error = f"{type(exc).__name__}: {exc}"
    conn.execute(
        "UPDATE run_log SET finished_at=now(), ok=%s, changed=%s, http_status=%s, table_hash=%s,"
        " rows_parsed=%s, error=%s WHERE id=%s",
        (error is None, changed, status, thash, rows_parsed, error, run_id),
    )
    conn.commit()
    state = "OK" if error is None else f"FAILED ({error})"
    print(f"{src.name}: {state}; changed={changed}; rows={rows_parsed}")
    if error:
        raise RuntimeError(error)


def main() -> None:
    ua = user_agent()
    failures = 0
    with psycopg.connect(database_url()) as conn:
        for src in SOURCES:
            try:
                collect_one(conn, src, ua)
            except Exception:
                failures += 1
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
