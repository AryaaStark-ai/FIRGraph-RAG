"""Split OCR text of an NCRB IIF-I FIR form into its numbered parts.

Every FIR uses the same form, so we split on the English heading labels
(OCR reads English labels more reliably than the item numbers).
"""
import re

# (key, regex that marks the start of that part), in form order
HEADINGS = [
    ("header",       r"District\s*\("),
    ("acts",         r"Acts\s*\("),
    ("occurrence",   r"(?<!Place of )Occurrence of"),
    ("info_type",    r"Type of Information"),
    ("place",        r"Place of Occurrence"),
    ("complainant",  r"Complainant\s*/\s*Informant"),
    ("accused",      r"Details of known"),
    ("delay",        r"Reasons for delay"),
    ("property",     r"Particulars of propert"),
    ("property_value", r"Total value of property"),
    ("inquest",      r"Inquest Report"),
    ("narrative",    r"First Information contents"),
    ("action",       r"Action taken"),
    ("signature",    r"Signature\s*/\s*Thumb"),
    ("accused_physical", r"Attachment to item 7|Physical features"),
]


def split_sections(text: str) -> dict[str, str]:
    hits = []
    for key, pat in HEADINGS:
        m = re.search(pat, text, flags=re.I)
        if m:
            hits.append((m.start(), key))
    hits.sort()
    parts = {}
    for i, (start, key) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        parts[key] = text[start:end].strip()
    # the narrative ends where the "Action taken" block begins; OCR sometimes puts
    # the inquest table after the narrative heading, so trim it off the front
    if "narrative" in parts:
        parts["narrative"] = re.sub(r"^First Information contents[^\n]*\n", "",
                                    parts["narrative"], flags=re.I).strip()
    return parts
