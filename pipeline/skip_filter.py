"""Decide which FIRs we are allowed to process, from the Sections column.

The CCTNS result table gives a clean Unicode string such as:
  'मोटरवाहन अधिनियम, १९८८ - 119,177 ; भारतीय न्याय संहिता (बी एन एस), 2023 - 281,324(4) ;'
so we can filter BEFORE downloading anything.
"""
import re
from .config import SKIP_ACT_KEYWORDS, BNS_SKIP_RANGES, BNS_SKIP_SINGLE
from .textutil import clean


def parse_sections(sections: str) -> list[dict]:
    """Split the portal's Sections string into [{'act': ..., 'section': ...}]."""
    out = []
    for chunk in clean(sections).split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        act, _, secs = chunk.rpartition(" - ")
        if not act:                      # no ' - ' separator, keep whole thing
            act, secs = chunk, ""
        for s in re.split(r",(?![^()]*\))", secs):   # split on commas outside brackets
            s = s.strip()
            if s:
                out.append({"act": act.strip(), "section": s})
    return out


def _is_bns(act: str) -> bool:
    return "न्याय संहिता" in act or "Nyaya Sanhita" in act or "BNS" in act


def skip_reason(sections: str) -> str | None:
    """Return why an FIR must be skipped, or None if it's OK to use."""
    for item in parse_sections(sections):
        act, sec = item["act"], item["section"]
        for kw in SKIP_ACT_KEYWORDS:
            if kw.lower() in act.lower():
                return f"sensitive act: {act}"
        if _is_bns(act):
            m = re.match(r"(\d+)", sec)
            if m:
                n = int(m.group(1))
                if n in BNS_SKIP_SINGLE or any(lo <= n <= hi for lo, hi in BNS_SKIP_RANGES):
                    return f"sensitive BNS section {sec}"
    return None
