"""Juvenile Justice Act s.74: never process an FIR that involves anyone under 18.

We are deliberately strict: if ANY person in the FIR (accused, complainant,
victim, witness, family member mentioned in the story) looks under 18, the
whole FIR is dropped.
"""
import re

from .config import MINOR_AGE


def minor_reason(fields: dict) -> str | None:
    year = int(fields.get("year") or (fields.get("fir_date") or "0000")[-4:] or 0)
    if not year:
        return "cannot read FIR year, so cannot rule out minors"

    births = [fields["complainant"].get("birth_year")] + [a.get("birth_year") for a in fields["accused"]]
    for by in births:
        if by and year - int(by) < MINOR_AGE:
            return f"person born {by} is under {MINOR_AGE} in {year}"

    # ages written in the story: 'वय 17 वर्षे', 'वय - 16 वर्ष'
    for age in re.findall(r"वय\s*[-:]?\s*(\d{1,2})\s*वर्ष", fields.get("narrative", "")):
        if int(age) < MINOR_AGE:
            return f"narrative mentions a {age}-year-old"

    if re.search(r"अल्पवयीन|अज्ञान\s*(मुलगा|मुलगी|बालक)|विधीसंघर्षग्रस्त|minor", fields.get("narrative", ""), re.I):
        return "narrative mentions a minor / child in conflict with law"
    return None
