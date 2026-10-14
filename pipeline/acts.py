"""Read the Acts & Sections table (item 2 of the FIR form) reliably.

Finding: OCR garbles the section numbers ('324(4)' -> '3244)', '303(2)' -> '320392)')
because the act name wraps across lines inside the table cell. But the PDF's own
text layer, whose Marathi letters are broken by the old font, keeps the DIGITS clean.
So: section numbers come from the text layer, act names are recognised from both layers,
and the sensitive-Act keyword check runs on BOTH the text layer and the clean OCR Marathi.
"""
import re

import pymupdf

from .textutil import to_ascii_digits

# act name recognisers: (canonical name, short code, patterns that work on garbled OR clean text)
ACTS = [
    ("Bharatiya Nyaya Sanhita, 2023", "BNS", [r"न्याय", r"Ûयाय", r"संहिता", r"संदहता"]),
    ("Motor Vehicles Act, 1988", "MVA", [r"मोटर\s*वाहन", r"मोटरवाहन"]),
    ("Maharashtra Police Act, 1951", "MPA", [r"पोलीस\s*अधि", r"महारा.{0,3}\s*पोलीस"]),
    ("Information Technology Act, 2000", "IT", [r"माहिती\s*तंत्र", r"Information Technology"]),
    ("Arms Act, 1959", "ARMS", [r"शस्त्र", r"Arms"]),
    ("NDPS Act, 1985", "NDPS", [r"अंमली", r"Narcotic", r"NDPS"]),
    ("Maharashtra Prohibition Act, 1949", "MPROH", [r"दारूबंदी", r"दारुबंदी", r"Prohibition"]),
]

ROW = re.compile(r"(?:^|\s)(\d{1,2})\s+(.+?),?\s*([0-9०-९]{4})\s*(\d{1,4}(?:\([0-9A-Za-z]{1,4}\))*)(?=\s|$)")


def text_layer_acts_block(pdf_path) -> str:
    t = pymupdf.open(pdf_path)[0].get_text()
    i, j = t.find("Acts"), t.find("FIRST INFORMATION REPORT", t.find("Acts") + 1)
    if i < 0:
        return ""
    if j < 0:
        j = t.find("Occurrence", i)
    block = re.sub(r"\s+", " ", t[i:j])
    return re.sub(r"^Acts\s*\(\S*\)\s*Sections\s*\(\S*\)\s*", "", block)


def classify(name: str):
    for canon, code, pats in ACTS:
        if any(re.search(p, name) for p in pats):
            return canon, code
    return None, None


def read_acts(pdf_path) -> list[dict]:
    """[{'act': 'Bharatiya Nyaya Sanhita, 2023', 'code': 'BNS', 'section': '324(4)', 'raw': ...}]"""
    out = []
    for m in ROW.finditer(text_layer_acts_block(pdf_path)):
        raw_name, sec = m.group(2), m.group(4)
        canon, code = classify(raw_name)
        out.append({"act": canon or f"UNRECOGNISED: {raw_name}", "code": code or "?",
                    "section": sec, "year": to_ascii_digits(m.group(3)),
                    "offence": offence_name(code, sec)})
    return out


# Offence names for common BNS sections (base section number -> label)
BNS_OFFENCE = {
    3: "common intention (with others)", 62: "attempt to commit offence",
    115: "voluntarily causing hurt", 117: "voluntarily causing grievous hurt",
    118: "hurt by dangerous weapon or means", 125: "endangering life or personal safety",
    189: "unlawful assembly", 190: "unlawful assembly (common object)", 191: "rioting",
    281: "rash driving on a public way", 303: "theft", 304: "snatching",
    305: "theft in a dwelling / of vehicle", 309: "robbery", 316: "criminal breach of trust",
    318: "cheating", 324: "mischief (property damage)", 329: "criminal trespass",
    333: "house-trespass to cause hurt", 351: "criminal intimidation", 352: "intentional insult",
}


OTHER_OFFENCE = {
    ("MVA", 119): "disobeying traffic signs/signals", ("MVA", 177): "traffic rule violation",
    ("MVA", 184): "dangerous driving", ("MVA", 185): "drunk driving",
    ("MPA", 142): "breach of externment order", ("MPA", 135): "breach of police prohibitory order",
    ("MPA", 37): "police prohibitory order",
}


def offence_name(code: str, section: str):
    m = re.match(r"(\d+)", section)
    if not m:
        return None
    n = int(m.group(1))
    return BNS_OFFENCE.get(n) if code == "BNS" else OTHER_OFFENCE.get((code, n))


def portal_style(acts: list[dict]) -> str:
    """Same 'Act - sec ; Act - sec' shape the CCTNS result table uses, for skip_filter."""
    names = {"BNS": "भारतीय न्याय संहिता (बी एन एस), 2023"}
    return " ; ".join(f"{names.get(a['code'], a['act'])} - {a['section']}" for a in acts)
