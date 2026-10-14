"""Run BEFORE every git commit: makes sure no real name, officer or vehicle number from the
FIRs has slipped into code, comments or docs that go to GitHub.

    python -m tests.scan_repo

It collects names from the local OCR text of every FIR (including skipped ones), the name
vault and the audit list, then searches every file git would commit. Prints file + line only;
the matched word is shown as its length, so the output itself is safe to share.
Exit code 1 if anything is found, so it can also run as a git pre-commit hook.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.fields import parse_all                       # noqa: E402
from pipeline.redact import LOCALITIES, NON_NAME, STOP, _cue_names, _surname_names   # noqa: E402
from pipeline.sections import split_sections                # noqa: E402

RELATION_WORDS = set("मुलगा मुलगी भाऊ बहीण वडील आई पती पत्नी बाई पुतणी पुतण्या मित्र नात".split())
SAFE_LATIN = {"more", "patil", "several"}                   # English words / college name


def private_words():
    words, latin = set(), set()
    for f in (ROOT / "data" / "ocr").glob("*.txt"):
        d = parse_all(split_sections(f.read_text(encoding="utf-8")))
        names = [d["complainant"]["name"]] + [a["name"] for a in d["accused"]] + _cue_names(d["narrative"])
        names += _surname_names(d["narrative"], {n.split()[-1] for n in names if n and len(n.split()) > 1})
        for n in names:
            words |= set((n or "").split())
        for o in (d.get("io_name"), d.get("registered_by")):
            latin |= {w.lower() for w in (o or "").split()}
        latin |= set(re.findall(r"(?<!\d)\d{4}(?!\d)", " ".join(
            re.findall(r"[A-Za-zऀ-ॿ]{1,3}[\s.-]*\d{1,2}[\s.-]*[A-Za-zऀ-ॿ .]{1,8}[\s.-]*\d{4}", d["narrative"]))))
    audit = ROOT / "data" / "audit" / "leaked_names.json"
    if audit.exists():
        for k, v in json.loads(audit.read_text(encoding="utf-8")).items():
            if not k.startswith("_"):
                for w in v["names"] + v["other"]:
                    (latin if w.isascii() else words).add(w.lower() if w.isascii() else w)
    words = {w for w in words if len(w) >= 3 and w not in STOP | NON_NAME | RELATION_WORDS and w not in LOCALITIES}
    latin = {w for w in latin if len(w) >= 4 and w not in SAFE_LATIN}
    return words, latin


def committed_files():
    out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                         cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        return [p for p in ROOT.rglob("*") if p.is_file() and "data" not in p.parts and ".venv" not in p.parts
                and ".git" not in p.parts and "__pycache__" not in p.parts]
    return [ROOT / l for l in out.stdout.splitlines() if l.strip()]


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    words, latin = private_words()
    hits = 0
    for f in committed_files():
        if f.suffix.lower() in (".pdf", ".png", ".jpg", ".traineddata") or not f.exists():
            continue
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(lines, 1):
            low = line.lower()
            for w in words:
                if re.search(r"(?<![ऀ-ॿ])" + re.escape(w) + r"(?![ऀ-ॿ])", line):
                    print(f"  {f.relative_to(ROOT)}:{i}  private word ({len(w)} letters)")
                    hits += 1
            for w in latin:
                if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", low):
                    print(f"  {f.relative_to(ROOT)}:{i}  private word/number ({len(w)} chars)")
                    hits += 1
    print(f"\nChecked against {len(words)} Marathi + {len(latin)} English/number private words.")
    if hits:
        print(f"FOUND {hits}. Do NOT commit; fix those lines first.")
        sys.exit(1)
    print("CLEAN: safe to commit.")


if __name__ == "__main__":
    main()
