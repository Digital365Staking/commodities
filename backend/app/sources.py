from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    name: str
    url: str


# Add a source here, plus a parser in app/parsers/. Only the eastbound page has been
# inspected; add the westbound page once you have looked at its table.
SOURCES = [
    Source("nansha-europe-med-eastbound", "https://www.portofnansha.com/europe-med-eastbound"),
    # Source("nansha-europe-med-westbound", "https://www.portofnansha.com/europe-med-westbound"),
]
