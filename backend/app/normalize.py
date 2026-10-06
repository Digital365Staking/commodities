"""Turn the latest parsed Nansha snapshot into reference tables (ports, services, rotations).

Idempotent: a raw payload is normalized once. Values are mapped to ports BY POSITION,
so each direction is flagged 'by_position' (counts match) or 'suspect' (counts differ).
Fix a value after checking the carrier by inserting a row in port_call_overrides.
"""
import re

import psycopg

from .config import database_url

PORT_ALIASES = {"southhampton": "Southampton"}  # extend as you meet new spellings


def to_int(token: str) -> int | None:
    return int(token) if re.fullmatch(r"\d+", token.strip()) else None


def canonical_port(name: str) -> str:
    return PORT_ALIASES.get(name.strip().lower(), name.strip())


def plan_row(row: dict) -> dict:
    """Pure function: one schedule_snapshots row -> what to store. Unit-tested without a DB."""
    ports = row["ports"]

    def side(values: list[str]) -> list[tuple[int | None, str]]:
        status = "by_position" if len(values) == len(ports) else "suspect"
        out = []
        for i in range(len(ports)):
            if i < len(values):
                v = to_int(values[i])
                out.append((v, status if v is not None else "missing"))
            else:
                out.append((None, "missing"))
        return out

    inbound, outbound = side(row["inbound_days"] or []), side(row["outbound_days"] or [])
    calls = [
        {"seq": i, "port": ports[i], "port_canonical": canonical_port(ports[i]),
         "in_days": inbound[i][0], "in_status": inbound[i][1],
         "out_days": outbound[i][0], "out_status": outbound[i][1]}
        for i in range(len(ports))
    ]
    liners, codes = row["liners"] or [], row["service_codes"] or []
    carriers = list(zip(liners, codes)) if len(liners) == len(codes) else []
    return {"row_key": "|".join(codes), "carriers": carriers, "calls": calls}


def port_id(conn, name: str) -> int:
    got = conn.execute(
        "SELECT id FROM ports WHERE lower(name)=lower(%s) OR lower(%s) = ANY (SELECT lower(a) FROM unnest(aliases) a)",
        (name, name),
    ).fetchone()
    if got:
        return got[0]
    return conn.execute("INSERT INTO ports (name) VALUES (%s) RETURNING id", (name,)).fetchone()[0]


def normalize_raw(conn, raw_id: int) -> int:
    rows = conn.execute(
        "SELECT service_codes, liners, ports, inbound_days, outbound_days FROM schedule_snapshots"
        " WHERE raw_id=%s ORDER BY row_index", (raw_id,)).fetchall()
    n = 0
    for codes, liners, ports, inb, outb in rows:
        plan = plan_row({"service_codes": codes, "liners": liners, "ports": ports,
                         "inbound_days": inb, "outbound_days": outb})
        if not plan["row_key"]:
            continue
        sid = conn.execute(
            "INSERT INTO services (row_key) VALUES (%s) ON CONFLICT (row_key) DO UPDATE SET row_key=EXCLUDED.row_key RETURNING id",
            (plan["row_key"],)).fetchone()[0]
        for carrier, code in plan["carriers"]:
            conn.execute(
                "INSERT INTO service_carriers (service_id, carrier_code, carrier_service_code) VALUES (%s,%s,%s)"
                " ON CONFLICT DO NOTHING", (sid, carrier, code))
        for c in plan["calls"]:
            conn.execute(
                "INSERT INTO service_port_calls (raw_id, service_id, seq, port_id, port_as_published,"
                " nominal_inbound_days, nominal_outbound_days, inbound_status, outbound_status)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (raw_id, sid, c["seq"], port_id(conn, c["port_canonical"]), c["port"],
                 c["in_days"], c["out_days"], c["in_status"], c["out_status"]))
            n += 1
    return n


def main() -> None:
    with psycopg.connect(database_url()) as conn:
        todo = conn.execute(
            "SELECT DISTINCT s.raw_id FROM schedule_snapshots s WHERE NOT EXISTS"
            " (SELECT 1 FROM service_port_calls c WHERE c.raw_id = s.raw_id) ORDER BY 1").fetchall()
        for (raw_id,) in todo:
            print(f"raw {raw_id}: {normalize_raw(conn, raw_id)} port calls")
            conn.commit()
        if not todo:
            print("nothing to normalize")


if __name__ == "__main__":
    main()
