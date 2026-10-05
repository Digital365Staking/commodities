"""Parser for the Port of Nansha Europe/Med timetable (a single HTML table).

The page has no dates or vessels: it publishes nominal transit times only.
Cells hold several values separated by runs of spaces, so values are mapped to
ports BY POSITION and counts do not always match (the source is inconsistent).
`raw_cells` keeps the untouched cell text so every mapping can be audited.
"""
import hashlib
import json
import re

from bs4 import BeautifulSoup

COLUMNS = {
    "liner": "liners",
    "service code": "service_codes",
    "yard closing": "yard_closing",
    "calling ports": "ports",
    "inbound transit": "inbound",
    "outbound transit": "outbound",
}


def _clean(text: str) -> str:
    return text.replace("\xa0", " ")


def _tokens(text: str, pattern: str) -> list[str]:
    return [t.strip() for t in re.split(pattern, _clean(text)) if t.strip()]


def _find_table(soup: BeautifulSoup):
    for table in soup.find_all("table"):
        text = table.get_text(" ").lower()
        if "calling ports" in text and "service code" in text:
            return table
    raise ValueError("Nansha schedule table not found in page")


def extract_cells(html: str) -> tuple[list[str], list[list[str]]]:
    table = _find_table(BeautifulSoup(html, "html.parser"))
    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text("\n") for c in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    if len(rows) < 2:
        raise ValueError("Nansha table has no data rows")
    return rows[0], rows[1:]


def table_hash(html: str) -> str:
    """Hash of the table content only, so Squarespace page noise never counts as a change."""
    header, body = extract_cells(html)
    payload = json.dumps([header, body], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def parse(html: str) -> list[dict]:
    header, body = extract_cells(html)
    idx: dict[str, int] = {}
    for i, name in enumerate(header):
        for needle, field in COLUMNS.items():
            if needle in name.lower():
                idx[field] = i
    missing = sorted(set(COLUMNS.values()) - set(idx))
    if missing:
        raise ValueError(f"Missing columns in Nansha table: {missing}")

    out = []
    for n, cells in enumerate(body):
        def cell(field: str) -> str:
            i = idx[field]
            return cells[i] if i < len(cells) else ""

        out.append({
            "row_index": n,
            "liners": _tokens(cell("liners"), r"\s+"),
            "service_codes": _tokens(cell("service_codes"), r"\s+"),
            "yard_closing": " ".join(_clean(cell("yard_closing")).split()) or None,
            "ports": _tokens(cell("ports"), r"\n|\s{2,}"),
            "inbound": _tokens(cell("inbound"), r"\s+"),
            "outbound": _tokens(cell("outbound"), r"\s+"),
            "raw_cells": cells,
        })
    return out
