from app.normalize import canonical_port, plan_row, to_int
from app.parsers import nansha
from pathlib import Path

HTML = (Path(__file__).parent / "fixtures" / "nansha_eastbound.html").read_text()


def snapshot(row):
    return {"service_codes": row["service_codes"], "liners": row["liners"], "ports": row["ports"],
            "inbound_days": row["inbound"], "outbound_days": row["outbound"]}


def test_to_int_and_alias():
    assert to_int("23") == 23 and to_int("–") is None and to_int("") is None
    assert canonical_port("Southhampton") == "Southampton"


def test_count_mismatch_is_flagged_suspect_never_silently_trusted():
    # fixture rows: row 0 has 9 ports and 9 values per side; row 1 has no outbound at all
    plans = [plan_row(snapshot(r)) for r in nansha.parse(HTML)]
    assert all(c["out_status"] == "missing" and c["out_days"] is None for c in plans[1]["calls"])
    assert plans[0]["row_key"] == "AE11|JADE|SERA2|AM2"
    assert plans[0]["carriers"][1] == ("MSC", "JADE")


def test_short_value_list_marks_whole_side_suspect():
    row = {"service_codes": ["X1"], "liners": ["AAA"], "ports": ["A", "B", "C"],
           "inbound_days": ["5", "6"], "outbound_days": ["1", "2", "3"]}
    calls = plan_row(row)["calls"]
    assert [c["in_status"] for c in calls] == ["suspect", "suspect", "missing"]
    assert [c["out_status"] for c in calls] == ["by_position"] * 3
    row["inbound_days"] = ["5", "6", "7", "8"]  # more values than ports
    assert {c["in_status"] for c in plan_row(row)["calls"]} == {"suspect"}
