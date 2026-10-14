"""PDF -> page images -> Marathi+English OCR text.

Why not read the PDF text directly? The published FIRs use an old Marathi font
encoding, so the text layer comes out as garbage ('प्रथम' -> 'Ĥम').
Rendering each page and OCR-ing it gives clean Unicode Marathi.
Everything here runs locally; nothing is sent anywhere.
"""
import os
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image

from .config import DPI, OCR_LANG, PAGES, TESSDATA

if TESSDATA:
    os.environ["TESSDATA_PREFIX"] = str(TESSDATA)

# Windows: find tesseract.exe even if it isn't on PATH yet
_WIN_EXE = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
if os.name == "nt" and _WIN_EXE.exists():
    pytesseract.pytesseract.tesseract_cmd = str(_WIN_EXE)

# Repeated page furniture we drop from the OCR text
_NOISE_PREFIXES = ("N.C.R.B", "I.I.F", "LLF", "IIF")


def ocr_pdf(pdf_path: Path) -> str:
    doc = pymupdf.open(pdf_path)
    out_dir = PAGES / pdf_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    for i, page in enumerate(doc, 1):
        img_path = out_dir / f"p{i:02d}.png"
        if not img_path.exists():
            page.get_pixmap(dpi=DPI).save(img_path)
        text = pytesseract.image_to_string(Image.open(img_path), lang=OCR_LANG, config="--psm 4")
        lines = [ln for ln in text.splitlines()
                 if ln.strip() and not ln.strip().startswith(_NOISE_PREFIXES)
                 and "एकीकृत" not in ln and "वेषणफॉर्म" not in ln   # repeated form header
                 and not ln.strip().isdigit()]          # page numbers
        pages.append("\n".join(lines))
    return "\n".join(pages)
