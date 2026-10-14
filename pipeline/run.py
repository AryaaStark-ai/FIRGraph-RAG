"""Run every FIR in data/raw_pdfs through the stage-1 pipeline.

    python -m pipeline.run            # process all PDFs
    python -m pipeline.run --redo-ocr # ignore cached OCR text

For each FIR:
  OCR -> split sections -> parse fields
  -> SKIP if a sensitive Act/section is charged   (skip_filter)
  -> SKIP if an inquest / accidental-death no. is filled
  -> SKIP if anyone is under 18                    (minors, JJ Act s.74)
  -> redact + pseudonymise -> leak check
  -> PASS: data/processed/<fir>.json      FAIL: data/quarantine/<fir>.json (manual review)

Writes data/report.csv (one row per FIR, no names) for the test-results slide.
"""
import csv
import json
import re
import sys
import warnings

from .acts import portal_style, read_acts
from .config import DATA, OCR, OUT, RAW_PDF, SKIP_ACT_KEYWORDS
from .fields import parse_all
from .minors import minor_reason
from .redact import Vault, redact_fir
from .sections import split_sections
from .skip_filter import skip_reason
from .textutil import clean

QUARANTINE = DATA / "quarantine"
REPORT = DATA / "report.csv"


def process(pdf, vault, redo_ocr=False):
    from .ocr import ocr_pdf                       # imported here so tests can run without Tesseract
    stem = pdf.stem
    txt_path = OCR / f"{stem}.txt"
    if redo_ocr or not txt_path.exists():
        txt_path.write_text(ocr_pdf(pdf), encoding="utf-8")
    parts = split_sections(txt_path.read_text(encoding="utf-8"))
    fields = parse_all(parts)
    acts_list = read_acts(pdf)                     # section numbers from the PDF text layer
    acts = portal_style(acts_list)

    row = {"file": pdf.name, "fir_no": fields.get("fir_no"), "fir_date": fields.get("fir_date"),
           "sections_found": len(parts), "acts": acts, "status": "", "reason": "",
           "accused": len(fields["accused"]),
           "accused_needs_review": sum(1 for a in fields["accused"] if a.get("needs_review")),
           "vehicles": 0, "persons": 0, "leaks": 0}

    reason = skip_reason(acts)
    if not reason:                                 # belt and braces: keywords in the clean OCR Marathi too
        ocr_acts = parts.get("acts", "")
        hit = next((k for k in SKIP_ACT_KEYWORDS if k.lower() in ocr_acts.lower()), None)
        if hit:
            reason = f"sensitive act keyword in OCR text: {hit}"
    if not reason and (not acts_list or any(a["code"] == "?" for a in acts_list)):
        reason = "could not read every Act on the form - needs manual check"
    if not reason and fields.get("inquest_filled"):
        reason = "inquest / accidental death number present"
    if not reason:
        reason = minor_reason(fields)
    if reason:
        row.update(status="SKIPPED", reason=reason)
        return row                                 # nothing redacted or stored for skipped FIRs

    out = redact_fir(fields, vault)
    out["acts"] = acts_list
    row.update(vehicles=len(out["vehicles"]),
               persons=1 + len(out["accused"]) + len(out["other_persons"]),
               leaks=len(out["leaks"]))
    if out["leaks"]:
        # never store the leaking words themselves in the report
        row.update(status="QUARANTINED", reason=f"{len(out['leaks'])} real-name words survived redaction")
        out_dir = QUARANTINE
    else:
        # rules passed, but a manual audit showed rules miss people never named in the
        # form's tables. Not safe for any LLM / sharing until the NER step (stage 1b) runs.
        row.update(status="RULES_PASSED", reason="awaiting LLM name check (stage 1b)")
        out_dir = OUT
    out["status"] = row["status"]
    out["source_file"] = pdf.name
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{stem}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return row


def main():
    # Windows consoles default to an old code page; make printing Marathi safe
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    warnings.filterwarnings("ignore")
    redo = "--redo-ocr" in sys.argv
    OCR.mkdir(parents=True, exist_ok=True)
    vault = Vault()
    rows = []
    for pdf in sorted(RAW_PDF.glob("*.pdf")):
        try:
            row = process(pdf, vault, redo)
        except Exception as e:                     # one bad PDF must not stop the batch
            row = {"file": pdf.name, "status": "ERROR", "reason": repr(e)}
        rows.append(row)
        print(f"{row['file']:<26} {row['status']:<12} {row.get('reason', '')}")
    vault.save()

    cols = ["file", "fir_no", "fir_date", "status", "reason", "sections_found", "acts",
            "accused", "accused_needs_review", "persons", "vehicles", "leaks"]
    with REPORT.open("w", newline="", encoding="utf-8-sig") as f:   # utf-8-sig so Excel shows Marathi
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    counts = {s: sum(r["status"] == s for r in rows) for s in ("RULES_PASSED", "QUARANTINED", "SKIPPED", "ERROR")}
    print("\nTotal:", len(rows), counts, f"\nReport: {REPORT}")


if __name__ == "__main__":
    main()
