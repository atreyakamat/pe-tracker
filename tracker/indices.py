"""The indices we track. Add one here and it flows through fetch, signal, compare, alerts and the UI.

`name` is the NSE allIndices name. niftyindices.com uses slightly different names for some
indices (Smallcap 250 is "NIFTY SMLCAP 250"); see ni_name / ni_long. All eight were verified
against the live endpoints on 2026-11-11. Sensex is intentionally absent: BSE has no stable PE-history
endpoint we can rely on, and it overlaps Nifty 50 heavily.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Index:
    key: str          # file name / URL-safe id
    name: str         # source index name
    label: str        # human label
    group: str        # "broad" | "segment" | "sector"
    core: bool = False  # core indices send a daily reminder while in BUY zone
    # niftyindices.com uses its own names (from its IndexMapping.json); NSE allIndices uses `name`.
    ni_name: str | None = None   # "trading" name sent as `name`
    ni_long: str | None = None   # long name sent as `indexName`

    @property
    def ni_trading(self) -> str:
        return (self.ni_name or self.name).upper()

    @property
    def ni_index_name(self) -> str:
        return self.ni_long or self.label


INDICES: list[Index] = [
    Index("nifty50", "NIFTY 50", "Nifty 50", "broad", core=True),
    Index("niftynext50", "NIFTY NEXT 50", "Nifty Next 50", "broad"),
    Index("nifty100", "NIFTY 100", "Nifty 100", "broad"),
    Index("nifty500", "NIFTY 500", "Nifty 500", "broad", core=True),
    Index("midcap150", "NIFTY MIDCAP 150", "Nifty Midcap 150", "segment"),
    Index("smallcap250", "NIFTY SMALLCAP 250", "Nifty Smallcap 250", "segment",
          ni_name="NIFTY SMLCAP 250", ni_long="NIFTY Smallcap 250"),
    Index("niftybank", "NIFTY BANK", "Nifty Bank", "sector"),
    Index("niftyit", "NIFTY IT", "Nifty IT", "sector"),
]

BY_KEY = {i.key: i for i in INDICES}

# Relative-valuation pairs: (numerator, denominator). "Do mid/small caps trade at a premium to large caps?"
PAIRS: list[tuple[str, str]] = [
    ("midcap150", "nifty50"),
    ("smallcap250", "nifty50"),
    ("nifty500", "nifty50"),
    ("niftybank", "nifty50"),
    ("niftyit", "nifty50"),
]
