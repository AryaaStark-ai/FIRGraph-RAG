"""Small text helpers used everywhere."""
import re
import unicodedata

_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def to_ascii_digits(text: str) -> str:
    """'२०२६' -> '2026'. FIRs mix Marathi and English digits."""
    return text.translate(_DEV_DIGITS)


def clean(text: str) -> str:
    """Normalise unicode and digits, squash spaces."""
    text = unicodedata.normalize("NFC", text)
    text = to_ascii_digits(text)
    text = text.replace("‌", "").replace("‍", "")  # zero-width joiners
    text = re.sub(r"[ \t]+", " ", text)
    return text


def similar(a: str, b: str) -> float:
    """0..1 similarity (Levenshtein ratio) without extra packages."""
    a, b = a.replace(" ", ""), b.replace(" ", "")
    if not a or not b:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return 1 - prev[-1] / max(len(a), len(b))
