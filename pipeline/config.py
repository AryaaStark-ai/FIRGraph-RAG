"""Shared settings for the FIRGraph-RAG pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"            # everything under data/ is gitignored
RAW_PDF = DATA / "raw_pdfs"     # downloaded FIRs (never leave your laptop)
PAGES = DATA / "pages"          # rendered page images
OCR = DATA / "ocr"              # raw OCR text (still contains names!)
OUT = DATA / "processed"        # redacted JSON, safe to send to an LLM
VAULT = DATA / "vault"          # real-name <-> pseudonym map (keep private)
SKIPPED = DATA / "skipped.csv"  # log of FIRs we dropped and why

# OCR language files. Kept inside the project (tessdata/) so no admin rights are needed on Windows.
# Tesseract language files: the project's own tessdata/ folder if present (no admin rights
# needed on Windows), else Tesseract's default location.
TESSDATA = ROOT / "tessdata" if (ROOT / "tessdata" / "mar.traineddata").exists() else None
                # folder with mar.traineddata if Tesseract can't find it, e.g. r"C:\Program Files\Tesseract-OCR\tessdata"
OCR_LANG = "mar+eng"
DPI = 300

# ---------- Cases we must not process ----------
# Whole Acts to skip (matched on English or Marathi words in the act name)
SKIP_ACT_KEYWORDS = [
    "POCSO", "बालकांचे संरक्षण", "लैंगिक अपराधांपासून",          # child sexual offences
    "Atrocit", "अत्याचार प्रतिबंध", "अनुसूचित जाती",                # SC/ST Atrocities Act
    "Dowry", "हुंडा",                                                  # dowry
    "Domestic Violence", "कौटुंबिक हिंसाचार",                         # domestic violence
    "Juvenile", "बाल न्याय",                                           # juvenile justice
    "Immoral Traffic", "अनैतिक",                                      # trafficking
]

# BNS Chapter V (sections 63-99): sexual offences, offences against women
# and children, dowry death, cruelty by husband/relatives.
BNS_SKIP_RANGES = [(63, 99)]
# Deaths / suicide: involve deceased persons and inquest reports.
BNS_SKIP_SINGLE = {103, 105, 106, 108}

MINOR_AGE = 18
