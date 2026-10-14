"""Rule-based parsing of the fixed FIR form fields (no LLM needed here).

Input: dict of form parts from sections.split_sections().
Output: a plain dict of fields. Names are still REAL at this stage;
redact.py swaps them for pseudonyms before anything leaves the laptop.
"""
import re
from .textutil import clean, similar

DEV = r"[ऀ-ॿ]+"
DATE = r"(\d{2}/\d{2}/\d{4})"


def _first(pat, text, group=1, flags=0):
    m = re.search(pat, text or "", flags)
    return m.group(group).strip() if m else None


def _norm_spaces(s):
    return re.sub(r"\s+", " ", s or "").strip()


def parse_header(h: str) -> dict:
    return {
        "fir_no": _first(r"FIR No\.?.*?(\d{3,4})\b", h),
        "year": _first(r"Year.*?(\d{4})", h),
        "police_station": _first(r"ठाणे\)\s*:\s*(" + DEV + ")", h),
        "fir_date": _first(DATE, h),
        "fir_time": _first(r"\d{2}/\d{2}/\d{4}\s+(\d{2}:\d{2})", h),
    }


def parse_occurrence(t: str) -> dict:
    dates = re.findall(DATE, t or "")
    times = re.findall(r"(\d{2}:\d{2})\s*तास", t or "")
    return {
        "occurred_from": dates[0] if dates else None,
        "occurred_to": dates[1] if len(dates) > 1 else None,
        "occurred_time": times[0] if times else None,
    }


def parse_place(t: str) -> dict:
    return {
        "direction_distance": _first(r"अंतर\)\s*:\s*([^\n]+)", t),
        "address": _first(r"Address\s*\(पत्ता\)\s*:\s*([^\n]+)", t),
    }


def parse_complainant(t: str) -> dict:
    name = _first(r"Name\s*\(नाव\)\s*:\s*(" + DEV + r"(?:\s+" + DEV + "){0,3})", t)
    by = _first(r"Birth.*?\b((?:19|20)\d{2})\b", t, flags=re.S)
    addr = _first(r"वर्तमान\s+पता\s+(.+?)(?:\n\s*2\s|\n\s*\(|$)", t, flags=re.S)
    phone = _first(r"(?:\+?91[-\s]?)?([6-9]\d{9})", t)
    return {"name": _norm_spaces(name), "birth_year": by,
            "address": _norm_spaces(addr), "phone": phone}


def _narrative_has_name(first: str, last: str, narr: str) -> bool:
    """Is there a 2-3 word phrase in the story that starts like `first`
    (allowing OCR typos) and ends with `last`? e.g. first='रमेश', last='जाधव'
    matches 'रमेस सुनील जाधव' (OCR typo in the first name). Stops address words like 'सात' being glued on."""
    words = re.findall(DEV, narr)
    for i, w in enumerate(words):
        for n in (1, 2):
            if i + n < len(words) and words[i + n] == last and similar(w, first) >= 0.7:
                return True
    return False


def parse_accused(t: str, narrative: str) -> list[dict]:
    """Each accused row contains its address starting with '1.', e.g.
    '1 रमेश सुनील 1. <address>,...' and the surname is often wrapped onto the
    next line. OCR sometimes loses the row number, so rows are found by the
    '1.' address marker and numbered in order."""
    lines = (t or "").splitlines()
    narr = _norm_spaces(narrative)
    out = []
    for i, line in enumerate(lines):
        m = re.match(r"^\s*(\d{1,2})?\s*(.*?)\s1\.\s*(.*)$", line)
        if not m or "No." in line or "Direction" in line:
            continue
        tokens = re.findall(DEV, m.group(2))            # drop OCR junk like '= Wel'
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        lead = re.match(r"^\s*(" + DEV + r")(?=\s|$)", nxt)   # bare wrapped word, no comma
        if tokens and lead and _narrative_has_name(tokens[0], lead.group(1), narr):
            tokens.append(lead.group(1))
        sr = int(m.group(1)) if m.group(1) else (out[-1]["sr"] + 1 if out else 1)
        row = {"sr": sr, "name": " ".join(tokens), "address": _norm_spaces(m.group(3))}
        if len(tokens) < 2:
            row["needs_review"] = "name may be incomplete (OCR)"
        out.append(row)
    return out


def parse_accused_physical(t: str) -> list[dict]:
    """Rows like '2 पुरुष 2010 -'. A missing row number means 'previous + 1'."""
    out = []
    for m in re.finditer(r"^\s*(\S*)\s*(पुरुष|पुरूष|महिला|स्त्री|इतर)\s+(\d{4})", t or "", re.M):
        num, sex, by = m.groups()
        sr = int(num) if num.isdigit() else (out[-1]["sr"] + 1 if out else 1)
        out.append({"sr": sr,
                    "sex": "M" if sex.startswith("पुर") else ("F" if sex in ("महिला", "स्त्री") else "O"),
                    "birth_year": by})
    return out


def parse_action(t: str) -> dict:
    """Investigating officer. Rank can wrap onto the name line:
    'Rank (हुद्दा): पोलीस' / 'Firstname Middlename Surname उपनिरीक्षक'."""
    m = re.search(r"Directed.*?Rank\s*\(हुद्दा\)\s*:\s*([^\n]*)\n\s*"
                  r"([A-Z][A-Za-z]+(?:[ \t]+[A-Z][A-Za-z]+){1,3})[ \t]*(" + DEV + r")?", t or "", re.S)
    if not m:
        return {"io_name": None, "io_rank": None}
    rank = _norm_spaces(m.group(1) + " " + (m.group(3) or ""))
    return {"io_name": m.group(2).upper(), "io_rank": rank}


def parse_signature(t: str) -> dict:
    ranks = re.findall(r"Rank\s*\(हुद्दा\)\s*:\s*([^\n]+)", t or "")
    return {"registered_by": _norm_spaces(_first(r"Name\s*\(नाव\)\s*:\s*([A-Z][A-Z .]+)", t)),
            "registered_rank": _norm_spaces(ranks[-1]) if ranks else None}


def parse_all(parts: dict) -> dict:
    parts = {k: clean(v) for k, v in parts.items()}
    narrative = parts.get("narrative", "")
    # the officer block sometimes lands under 'signature' instead of 'action'
    tail = parts.get("action", "") + "\n" + parts.get("signature", "")
    accused = parse_accused(parts.get("accused", ""), narrative)
    phys = {r["sr"]: r for r in parse_accused_physical(parts.get("accused_physical", ""))}
    for a in accused:
        a.update({k: v for k, v in phys.get(a["sr"], {}).items() if k != "sr"})
    return {
        **parse_header(parts.get("header", "")),
        **parse_occurrence(parts.get("occurrence", "")),
        "place": parse_place(parts.get("place", "")),
        "complainant": parse_complainant(parts.get("complainant", "")),
        "accused": accused,
        # an accidental-death / inquest number looks like '12/2026'
        "inquest_filled": bool(re.search(r"\b\d{1,5}/\d{4}\b", parts.get("inquest", ""))),
        **parse_action(tail),
        **parse_signature(tail),
        "narrative": narrative,
    }
