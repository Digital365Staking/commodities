"""Print the theory-vs-practice comparison.   python -m app.report"""
import psycopg

from .config import database_url


def show(title: str, cols: list[str], rows: list[tuple]) -> None:
    print(f"\n== {title} ==")
    if not rows:
        print("(no rows)")
        return
    widths = [max(len(c), *(len(str(r[i])) for r in rows)) for i, c in enumerate(cols)]
    print("  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    for r in rows:
        print("  ".join(str(v if v is not None else "-").ljust(w) for v, w in zip(r, widths)))


def main() -> None:
    with psycopg.connect(database_url()) as conn:
        cols = ["service", "port", "inbound", "in_status", "outbound", "out_status"]
        show("Nominal days from the Nansha page (check statuses before trusting a value)", cols,
             conn.execute("SELECT row_key, port, inbound_days, inbound_status, outbound_days, outbound_status"
                          " FROM current_nominal ORDER BY service_id, seq").fetchall())
        cols = ["origin", "destination", "carrier", "code", "vessel", "voyage", "route", "basis",
                "nominal", "observed", "gap", "gap_pct", "over_10pct"]
        show("Theory vs practice", cols, conn.execute(
            "SELECT origin, destination, carrier_code, carrier_service_code, vessel, voyage, route_variant,"
            " arrival_basis, nominal_days, observed_days, gap_days, gap_pct, over_threshold"
            " FROM theory_vs_practice ORDER BY observed_at DESC").fetchall())


if __name__ == "__main__":
    main()
