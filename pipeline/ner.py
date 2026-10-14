"""Stage 1b: a local LLM finds person names the rules missed.

Why: the manual audit found real names in 6 of 8 rule-redacted FIRs (roommates,
neighbours, staff, relatives, officers named only in the story). Rules can't know
those names; a language model can recognise them from context.

    python -m pipeline.ner          # check every RULES_PASSED FIR in data/processed/

For each FIR:
  1. split the (already rule-redacted) narrative into short chunks
  2. ask the local LLM: "list every person's name in this text"
  3. keep only names that really occur in the text (stops the model inventing names)
  4. give each a pseudonym from the same vault, replace it, absorb leftover name words
  5. leak check against ALL names (rules + LLM) -> LLM_CHECKED or QUARANTINED
The status is written into the JSON and into data/ner_report.csv.
"""
import csv
import json
import re
import sys
import time

from .config import DATA, OUT
from .llm import MODEL, chat_json
from .redact import LOCALITIES, NON_NAME, NOT_DEV, STOP, Vault, leak_check

QUARANTINE = DATA / "quarantine"
REPORT = DATA / "ner_report.csv"

SYSTEM = """You find PEOPLE'S NAMES in Marathi police complaint text (Devanagari, sometimes English).
Return JSON: {"names": ["...", "..."]}
Rules:
- Copy each name EXACTLY as written in the text, including middle name and surname if present.
- Include every person: complainants, accused, family members, friends, neighbours, workers,
  doctors, police officers, anyone named.
- Do NOT include: tags in square brackets like [P_0003] or [PHONE]; places, roads, colonies,
  societies, hospitals, companies, banks, police stations; job titles or ranks on their own.
- If there are no names, return {"names": []}."""

TITLES = r"^(श्री\.?|श्रीमती|सौ\.?|कु\.?|डॉ\.?|डॉक्टर|सपोनि|पोनि|पोउनि|पोहवा|पो\.?ह\.?|मा\.?)\s*"


def chunks(text: str, size: int = 900):
    """Split on sentence ends so a name is never cut in half."""
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.।\n])", text):
        if len(cur) + len(sent) > size and cur:
            parts.append(cur)
            cur = ""
        cur += sent
    if cur.strip():
        parts.append(cur)
    return parts


def clean_name(n: str, text: str):
    n = re.sub(TITLES, "", str(n).strip()).strip(" ,.;:-")
    if len(n.replace(" ", "")) < 3 or "[" in n or re.search(r"\d", n):
        return None
    words = n.split()
    if all(w in NON_NAME or w in STOP for w in words):
        return None
    # places the model may mistake for people: known Pune areas, or place-shaped words
    if any(w in LOCALITIES or re.search(r"(नगर|पेठ|वाडी|गाव|वस्ती|चौक|रोड|कॉलनी)$", w) for w in words):
        return None
    return n if n in text else None          # must really be in the text: no invented names


def find_names(text: str) -> list[str]:
    found = set()
    for c in chunks(text):
        out = chat_json(SYSTEM, c)
        for n in out.get("names", []) if isinstance(out, dict) else []:
            n = clean_name(n, c)
            if n:
                found.add(n)
    return sorted(found, key=len, reverse=True)


def apply_names(text: str, names: list[str], vault: Vault) -> tuple[str, dict]:
    name_to_id = {n: vault.person(n) for n in names}
    for n in names:                                         # longest first
        text = re.sub(NOT_DEV + re.escape(n) + r"(?![ऀ-ॿ])", f"[{name_to_id[n]}]", text)
    # leftover single words of these names next to / away from tags
    tokens = {}
    for n, pid in name_to_id.items():
        for t in n.split():
            if len(t) >= 3 and t not in STOP and t not in NON_NAME:
                tokens.setdefault(t, set()).add(pid)
    if tokens:
        alt = "|".join(sorted(map(re.escape, tokens), key=len, reverse=True))
        word = NOT_DEV + r"(?:" + alt + r")(?![ऀ-ॿ])"
        text = re.sub(r"(\[P_\d+\])((?:\s+" + word + r")+)", r"\1", text)
        text = re.sub(r"((?:" + word + r"\s+)+)(\[P_\d+\])", r"\2", text)
        text = re.sub(word, lambda m: f"[{next(iter(tokens[m.group(0)]))}]"
                      if len(tokens[m.group(0)]) == 1 else "[NAME]", text)
    return text, name_to_id


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    vault = Vault()
    real_names = set(vault.data["people"])                  # every name the rules already know (spaces removed)
    rows = []
    files = sorted(OUT.glob("*.json"))
    print(f"Model: {MODEL}  |  FIRs to check: {len(files)}\n")
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("status") == "LLM_CHECKED" and "--redo" not in sys.argv:
            continue
        t0 = time.time()
        names = find_names(d["narrative_redacted"])
        text, new_ids = apply_names(d["narrative_redacted"], names, vault)
        vault.save()
        d["narrative_redacted"] = text
        d["other_persons"] = sorted(set(d.get("other_persons", [])) | set(new_ids.values()))
        # leak check against every known real name; vault keys have spaces removed, so check
        # the compact text too
        d["leaks"] = leak_check(d, names, [])
        compact = re.sub(r"\s+", "", d["narrative_redacted"])
        d["leaks"] += [k for k in real_names | set(n.replace(" ", "") for n in names)
                       if len(k) >= 6 and k in compact]
        d["leaks"] = sorted(set(d["leaks"]))
        d["status"] = "QUARANTINED" if d["leaks"] else "LLM_CHECKED"
        if d["leaks"]:
            QUARANTINE.mkdir(parents=True, exist_ok=True)
            (QUARANTINE / f.name).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            f.unlink()
        else:
            f.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        secs = time.time() - t0
        rows.append({"file": f.name, "status": d["status"], "llm_new_names": len(names),
                     "leaks": len(d["leaks"]), "seconds": round(secs)})
        print(f"{f.stem:<22} {d['status']:<12} new names found: {len(names):<3} ({secs:.0f}s)")
    if rows:
        with REPORT.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(f"\nDone. {sum(r['status'] == 'LLM_CHECKED' for r in rows)} checked, "
          f"{sum(r['status'] == 'QUARANTINED' for r in rows)} quarantined.  Report: {REPORT}")
    print("Now READ a few outputs in data/processed/ yourself: the manual audit is the real test.")


if __name__ == "__main__":
    main()
