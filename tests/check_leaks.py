"""Pass/fail test for anonymisation, against the MANUAL audit (not the automatic leak check).

    python -m tests.check_leaks

Ground truth: data/audit/leaked_names.json (private, git-ignored). For each FIR it lists
the real-name words a human found left behind after rule redaction, plus other identifying
details (building names, account numbers). A FIR passes when NONE of them appear anywhere
in its processed output.

Pass mark for stage 1b: every listed NAME is gone. Extra words wrongly masked are acceptable.
The printout shows only counts and FIR numbers, never the names themselves.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRUTH = ROOT / "data" / "audit" / "leaked_names.json"
DIRS = [ROOT / "data" / "processed", ROOT / "data" / "quarantine"]


def find_output(fir):
    for d in DIRS:
        for f in d.glob(f"{fir}*.json"):
            return f
    return None


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    total_names = caught_names = 0
    all_names_ok = True
    print(f"{'FIR':<6}{'status':<14}{'names caught':<15}{'other details caught':<22}result")
    for fir, t in truth.items():
        if fir.startswith("_"):
            continue
        f = find_output(fir)
        if not f:
            print(f"{fir:<6}{'(no output)':<14}")
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        blob = json.dumps({k: v for k, v in d.items() if k != "leaks"}, ensure_ascii=False)
        left_names = [w for w in t["names"] if w.lower() in blob.lower()]
        left_other = [w for w in t["other"] if w.lower() in blob.lower()]
        n, o = len(t["names"]), len(t["other"])
        total_names += n
        caught_names += n - len(left_names)
        ok = not left_names
        all_names_ok &= ok
        print(f"{fir:<6}{d.get('status', '?'):<14}{f'{n - len(left_names)}/{n}':<15}"
              f"{f'{o - len(left_other)}/{o}':<22}{'PASS' if ok and not left_other else ('PASS (names)' if ok else 'FAIL')}")
    print(f"\nNames caught: {caught_names}/{total_names}  ->  stage 1b "
          f"{'PASSES' if all_names_ok else 'FAILS'} the pass mark (every leaked name caught).")
    if "--show" in sys.argv:
        print("\n(--show) Remaining words, for fixing. Do NOT run this on a projector.")
        for fir, t in truth.items():
            if fir.startswith("_"):
                continue
            f = find_output(fir)
            if f:
                blob = f.read_text(encoding="utf-8").lower()
                left = [w for w in t["names"] + t["other"] if w.lower() in blob]
                if left:
                    print(f"  {fir}: {left}")


if __name__ == "__main__":
    main()
