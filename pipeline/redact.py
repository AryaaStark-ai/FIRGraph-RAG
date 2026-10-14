"""Pseudonymise an FIR before anything leaves the laptop.

  real names      -> P_0001, P_0002 ...   (same person = same ID across FIRs)
  vehicle numbers -> V_001 ...            (same plate  = same ID, so links survive)
  officers        -> O_001 ...            (rank is kept)
  Aadhaar/phone   -> [AADHAAR] / [PHONE]  (deleted, never needed)
  home addresses  -> locality only        ("कोथरुड"), house/building numbers removed

The real <-> fake mapping is stored in data/vault/ (gitignored, never shared).
After redacting, a leak check confirms no known name survives in the output.
"""
import json
import re

from .config import VAULT
from .textutil import similar

DEV = r"[ऀ-ॿ]+"
NOT_DEV = r"(?<![ऀ-ॿ])"     # word boundary for Devanagari (\b doesn't work)

# ---------------------------------------------------------------- vault
class Vault:
    def __init__(self, path=VAULT / "vault.json"):
        self.path = path
        self.data = {"people": {}, "vehicles": {}, "officers": {}}
        if path.exists():
            raw = path.read_text(encoding="utf-8").strip()
            if raw:                      # an empty file = an interrupted earlier save; start fresh
                try:
                    self.data = json.loads(raw)
                except json.JSONDecodeError as e:
                    raise SystemExit(f"Name vault {path} is damaged ({e}). Restore a backup, or delete it "
                                     "and re-run ALL FIRs so pseudonyms stay consistent.")

    def _get(self, kind, key, prefix, width):
        table = self.data[kind]
        if key not in table:
            table[key] = f"{prefix}_{len(table) + 1:0{width}d}"
        return table[key]

    def person(self, name):  return self._get("people", re.sub(r"\s+", "", name), "P", 4)
    def vehicle(self, plate): return self._get("vehicles", plate, "V", 3)
    def officer(self, name): return self._get("officers", name.upper(), "O", 3)

    def find_plate_by_tail(self, tail):
        """OCR sometimes eats the 'MH' state code; match on '12AB1234'."""
        return next((v for k, v in self.data["vehicles"].items() if k.endswith(tail)), None)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # write to a temp file, then swap it in: a crash mid-save can't leave a half-written vault
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)


# ---------------------------------------------------------------- places
# Pune / PCMC localities we are happy to keep (coarse, not identifying)
LOCALITIES = """कोथरुड एरंडवणे शिवाजीनगर डेक्कन कर्वेनगर वारजे बाणेर औंध पाषाण बावधन सुस
हडपसर कात्रज स्वारगेट येरवडा विमाननगर खराडी लोहगाव कल्याणीनगर कोंढवा वानवडी
बिबवेवाडी धनकवडी सहकारनगर पर्वती सिंहगड खडकी कॅम्प पिंपरी चिंचवड कासारवाडी
आकुर्डी निगडी भोसरी वाकड हिंजवडी देहूरोड किवळे रावेत सांगवी दापोडी
कोथरूड नळस्टॉप नळस्टप पौड वनाज प्रभात भांडारकर गोखलेनगर मॉडेल
कसबा सदाशिव नारायण शनिवार बुधवार रविवार भवानी गणेश नाना""".split()
_PETH = {"कसबा", "सदाशिव", "नारायण", "शनिवार", "बुधवार", "रविवार", "भवानी", "गणेश", "नाना"}


def locality(address: str) -> str:
    for loc in LOCALITIES:
        if loc in _PETH:
            if re.search(loc + r"\s*पेठ", address or ""):
                return loc + " पेठ"
        elif loc in (address or ""):
            return loc
    return "[ADDRESS]"


HOUSE_PATTERNS = [
    r"घर\s*(?:नंबर|नं\.?|क्र\.?)\s*\d+",
    r"(?:फ्लॅट|रूम|रुम)\s*(?:नंबर|नं\.?|क्र\.?)?\s*\S+",
    r"बिल्डी?ंग\s*(?:नं\.?)?\s*\d+",
    NOT_DEV + r"ए\s?\d+" + r"(?![ऀ-ॿ])",       # 'ए3' flat codes
]
# the 1-2 words naming a building/society/hall pin down a home too precisely: 'XYZ सोसायटीच्या समोर'
BUILDING = re.compile(r"(?:" + DEV + r"\s+){1,2}(?=(?:सोसायटी|सोसा\.|अपार्टमे[ंन्]+ट|बिल्डी?ंग|टॉवर|रेसिडेन्सी|हाईट्स|हॉल|को\.?\s*ऑप)[ऀ-ॿ]*)")
# 'रा.' / 'राहणार' introduces a home address in the story; we keep only locality
RESIDENCE = re.compile(r"(रा\.|राहणार\s*[-:]?)\s*((?:.|\n){3,220}?)(?=\s*(?:मो\.|मोबा|मोबाईल|मोबाइल|वय|धंदा|समक्ष|याने|यांनी|याला|हिला|हीला|यास|यांना|असे|यांच्या)|\.\s|$)")

# ---------------------------------------------------------------- vehicles
_LETTER = {"एम": "M", "एच": "H", "जे": "J", "बी": "B", "ए": "A", "सी": "C", "डी": "D", "ई": "E",
           "एफ": "F", "जी": "G", "आय": "I", "के": "K", "एल": "L", "एन": "N", "ओ": "O", "पी": "P",
           "क्यू": "Q", "आर": "R", "एस": "S", "टी": "T", "यू": "U", "व्ही": "V", "डब्ल्यू": "W",
           "एक्स": "X", "वाय": "Y", "झेड": "Z"}


def _spelled_to_latin(s):
    out, i = "", 0
    keys = sorted(_LETTER, key=len, reverse=True)
    while i < len(s):
        k = next((k for k in keys if s.startswith(k, i)), None)
        if not k:
            return None
        out, i = out + _LETTER[k], i + len(k)
    return out


PLATE_PATTERNS = [
    # MH 12 AB 1234 / MH-12-AB-1234
    (re.compile(r"\b([A-Za-z]{2})[\s-]*(\d{1,2})[\s-]*([A-Za-z]{1,3})[\s-]*(\d{4})\b"), "latin"),
    # 22 BH 1234 AA  (Bharat series)
    (re.compile(r"\b(\d{2})\s*(BH)\s*(\d{4})\s*([A-Za-z]{1,2})\b"), "bh"),
    # एमएच 12 एबी 1234  (spelled out in Marathi)
    (re.compile(r"(" + DEV + r")\s*[-]?\s*(\d{1,2})\s*[-]?\s*(" + DEV + r")\s*[-]?\s*(\d{4})"), "spelled"),
    # letters spelled one per word, with spaces or dots: 'एम एच 12 ए बी 1234', 'एम.एच 12 सी डी 5678'
    (re.compile(r"((?:" + DEV + r"[\s.]*){2})[-\s.]*(\d{1,2})[\s.]*(?:\d{1,2}\.?\s*)?((?:" + DEV + r"[\s.]*){1,3})[-\s.]*(\d{4})(?!\d)"), "spaced"),
    # '12 Ab 1234' with the state code lost by OCR
    (re.compile(r"(?<![A-Za-z\d])(\d{1,2})\s+([A-Za-z]{1,3})\s+(\d{4})\b"), "tail"),
]


def _redact_plates(text, vault, found):
    for pat, kind in PLATE_PATTERNS:
        def repl(m):
            g = m.groups()
            if kind == "latin":
                plate = f"{g[0]}{int(g[1]):02d}{g[2]}{g[3]}".upper()
            elif kind == "bh":
                plate = f"{g[0]}BH{g[2]}{g[3]}".upper()
            elif kind == "spaced":
                st = _spelled_to_latin(re.sub(r"[\s.]", "", g[0]))
                ser = _spelled_to_latin(re.sub(r"[\s.]", "", g[2]))
                if not st or not ser or len(st) != 2:
                    return m.group(0)
                plate = f"{st}{int(g[1]):02d}{ser}{g[3]}"
            elif kind == "spelled":
                st, ser = _spelled_to_latin(g[0]), _spelled_to_latin(g[2])
                if not st or not ser or len(st) != 2:
                    return m.group(0)                      # not a plate
                plate = f"{st}{int(g[1]):02d}{ser}{g[3]}"
            else:
                tail = f"{int(g[0]):02d}{g[1]}{g[2]}".upper()
                vid = vault.find_plate_by_tail(tail)
                if not vid:
                    return m.group(0)
                found.add(vid)
                return f"[{vid}]"
            vid = vault.vehicle(plate)
            found.add(vid)
            return f"[{vid}]"
        text = pat.sub(repl, text)
    return text


# ---------------------------------------------------------------- names
RELATION_CUES = (r"नामे|पत्नी|पती|मुलगा|मुलगी|मित्र|मैत्रीण|पुतणी|पुतण्या|भाऊ|बहीण|जाऊ\s*बाई|जाऊबाई|"
                 r"आई|वडील|मामा|काका|मावशी|आत्या|आजी|आजोबा|सासू|सासरे|दीर|नणंद|मेहुणा")
STOP = set("""वय रा रा. राहणार धंदा हा ही हे याला यांनी याने हिला यांना यास असे व आणि तसेच
सदर ठिकाणी आला आली आले गेले गेलो घरी सोबत बरोबर मला माझा माझी माझे दे असताना करिता नामे
यांच्या त्याच्या यांचा याचा याची याचे यांचे हिच्या उर्फ म्हणून इसम चालक
मध्ये मधील नंतर त्यानंतर दिल्यानंतर तेव्हा की कि परंतु पण तर तरी आता आज रोजी त्यावेळी
तेवढ्यात म्हणजे जेव्हा जर ते ती तो त्यांनी त्याने तिने आम्ही तुम्ही मी माझ्या आमचे आमच्या
त्यांचे त्याचे तिचे सोबतच व्यक्ती नावाचे नावाची नाव श्री श्रीमती सौ कु""".split())

# a word ending like this is grammar, not a name ("दिल्यानंतर", "असताना", "घरातून")
FUNCTION_SUFFIX = re.compile(r"(नंतर|ल्याने|ल्यावर|ताना|तांना|ून|ुन|ातून|ामध्ये|मध्ये|कडून|कडे|साठी|करिता)$")


def _namelike(w):
    return w not in STOP and w not in NON_NAME and not FUNCTION_SUFFIX.search(w) and not re.search(r"\d", w)


# Common words that sit next to names but are never names themselves. Cue-name capture
# stops at them, and the leak check ignores them (they caused false alarms in FIR 32).
NON_NAME = set("""पोलीस पोलिस स्टेशन ठाणे ठाण्यात ठाणेस चौकी अलंकार हॉल हॉटेल सोसायटी सोसायटीच्या
सोसायटीमध्ये अपार्टमेंट बिल्डींग बिल्डिंग कॉलनी नगर वसाहत चाळ रोड रस्ता चौक चौकात समोर जवळ
येथे येथील तेथे पुणे शहर गाव गल्ली लेन नंबर कंपनी ऑफिस आफीस दुकान बँक हॉस्पिटल रुग्णालय
कार्यक्रम मंदिर शाळा कॉलेज मार्केट गेट स्टॉप तक्रार वाजता वाजताच्या दरम्यान रोजी दिनांक""".split())


def _cue_names(narr):
    """Names introduced by a relation word: 'माझी पत्नी नामे सुनीता रमेश जाधव वय 38'."""
    names = []
    for m in re.finditer(r"(?:" + RELATION_CUES + r")\s+(?:नामे\s+)?((?:" + DEV + r"\s*){1,4})", narr):
        toks = []
        for t in m.group(1).split():
            if t in STOP or t in NON_NAME or t.startswith("रा.") or re.search(r"\d", t):
                break
            toks.append(t)
        if toks:
            names.append(" ".join(toks[:3]))
    return names


def _surname_names(narr, surnames):
    """'सुनीता जाधव', 'अनिता संजय जाधव': 1-2 words before a known surname."""
    names = []
    for sn in surnames:
        for m in re.finditer(r"((?:" + DEV + r"\s+){1,2})" + re.escape(sn) + r"(?![ऀ-ॿ])", narr):
            toks = m.group(1).split()
            keep = []
            for t in reversed(toks):                 # walk outward from the surname
                if not _namelike(t):
                    break
                keep.insert(0, t)
            if keep:
                names.append(" ".join(keep + [sn]))
    return names


def _cluster(names):
    """Group spellings of the same person inside one FIR (OCR / clerk typos):
    'रमेस जाधव' ~ 'रमेश सुनील जाधव' ~ 'रमेश सुनिल जाधव'."""
    groups = []
    for n in sorted(set(names), key=len, reverse=True):
        t = n.split()
        for g in groups:
            h = g[0].split()
            same_last = len(t) > 1 and len(h) > 1 and t[-1] == h[-1]
            if len(t) >= 2 and len(h) >= 2 and t[-2:] == h[-2:]:
                g.append(n)
                break
            if similar(n, g[0]) >= 0.85 or (same_last and similar(t[0], h[0]) >= 0.8):
                g.append(n)
                break
        else:
            groups.append([n])
    return groups


# ---------------------------------------------------------------- main
def redact_fir(fields: dict, vault: Vault) -> dict:
    narr = fields["narrative"]
    comp, accused = fields["complainant"], fields["accused"]

    # 1. collect every person-name spelling we can find
    structured = [comp["name"]] + [a["name"] for a in accused]
    structured = [n for n in structured if n and len(n.split()) >= 2]
    found = structured + _cue_names(narr)
    for _ in range(2):                       # surnames learnt in round 1 find more people in round 2
        surnames = {n.split()[-1] for n in found if len(n.split()) >= 2} - STOP - NON_NAME
        found = found + _surname_names(narr, surnames)
    found = [n for n in found if len(n.replace(" ", "")) >= 3]
    groups = _cluster(found)
    name_to_id = {}
    for g in groups:
        pid = vault.person(g[0])            # longest spelling is the canonical key
        for n in g:
            name_to_id[n] = pid

    # 2. redact the story: IDs first (Aadhaar before phone, both are digits)
    text = re.sub(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}(?!\d)", "[AADHAAR]", narr)
    text = re.sub(r"(?:\+?91[-\s]?)?(?<!\d)[6-9]\d{9}(?!\d)", "[PHONE]", text)
    text = re.sub(r"(?i)\b[A-Z]{2}[-\s]?\d{2}[-\s]?\d{9,12}\b", "[LICENCE]", text)          # driving licence
    text = re.sub(r"(?<!\d)\d{14,17}(?!\d)", "[ID_NUMBER]", text)
    text = re.sub(r"(?i)((?:account|a/c|अकाउंट|अकांऊट|अकाऊंट|खाते)[^\d\n]{0,25})\d{9,18}", r"\1[ACCOUNT]", text)                          # IMEI, account no.
    text = re.sub(r"(?i)(सिरीयल|serial)\s*(?:नं\.?|no\.?|क्र\.?)?\s*\S+", r"\1 [ID_NUMBER]", text)
    vehicles = set()
    text = _redact_plates(text, vault, vehicles)
    text = RESIDENCE.sub(lambda m: f"{m.group(1)} [{locality(m.group(2))}]", text)
    text = _strip_house(text)
    for n in sorted(name_to_id, key=len, reverse=True):              # full names, longest first
        text = re.sub(NOT_DEV + re.escape(n) + r"(?![ऀ-ॿ]{4,})", f"[{name_to_id[n]}]", text)
    # bare first names left over ('सुनीता हिला', 'रमेशने'), only if unambiguous
    firsts = {}
    for n, pid in name_to_id.items():
        firsts.setdefault(n.split()[0], set()).add(pid)
    for first, pids in firsts.items():
        if len(pids) == 1 and len(first) >= 3 and _namelike(first):
            text = re.sub(NOT_DEV + re.escape(first) + r"(?=[ऀ-ॿ]{0,4}(?![ऀ-ॿ]))",
                          f"[{next(iter(pids))}]", text)

    # 'P_0004 सुनील जाधव' / 'अनिता P_0022': absorb neighbouring name words into the tag
    tokens = {}
    for n, pid in name_to_id.items():
        for t in n.split():
            if len(t) >= 3 and t not in STOP and t not in NON_NAME:
                tokens.setdefault(t, set()).add(pid)
    if tokens:
        alt = "|".join(sorted(map(re.escape, tokens), key=len, reverse=True))
        word = NOT_DEV + r"(?:" + alt + r")(?![\u0900-\u097F])"
        for _ in range(3):
            text = re.sub(r"(\[P_\d+\])((?:\s+" + word + r")+)", r"\1", text)
            text = re.sub(r"((?:" + word + r"\s+)+)(\[P_\d+\])", r"\2", text)
        # anything left: one owner -> that ID; shared (e.g. a family surname) -> [NAME]
        def lone(m):
            pids = tokens[m.group(0)]
            return f"[{next(iter(pids))}]" if len(pids) == 1 else "[NAME]"
        text = re.sub(word, lone, text)

    officers = []
    for name, rank, role in ((fields.get("io_name"), fields.get("io_rank"), "investigating_officer"),
                             (fields.get("registered_by"), fields.get("registered_rank"), "registering_officer")):
        if name:
            oid = vault.officer(name)
            officers.append({"id": oid, "rank": rank, "role": role})
            text = re.sub(re.escape(name), f"[{oid}]", text, flags=re.I)

    year = int(fields.get("year") or 0)

    def age(by):
        return year - int(by) if by and year else None

    out = {
        "fir_no": fields["fir_no"], "year": fields["year"], "police_station": fields["police_station"],
        "fir_date": fields["fir_date"], "fir_time": fields["fir_time"],
        "occurred_from": fields["occurred_from"], "occurred_to": fields["occurred_to"],
        "occurred_time": fields["occurred_time"],
        "place": {"direction_distance": fields["place"]["direction_distance"],
                  # a public spot like a chowk/road is fine to keep, minus house numbers
                  "address": _place_address(fields["place"]["address"])},
        "complainant": {"id": name_to_id.get(comp["name"]), "birth_year": comp["birth_year"],
                        "age": age(comp["birth_year"]), "locality": locality(comp["address"])},
        "accused": [{"id": name_to_id.get(a["name"]) if len(a["name"].split()) >= 2 else None,
                     "sex": a.get("sex"), "birth_year": a.get("birth_year"),
                     "age": age(a.get("birth_year")), "locality": locality(a["address"]),
                     **({"needs_review": a["needs_review"]} if a.get("needs_review") else {})}
                    for a in accused],
        "other_persons": sorted({pid for n, pid in name_to_id.items()} -
                                {name_to_id.get(comp["name"])} -
                                {name_to_id.get(a["name"]) for a in accused}),
        "vehicles": sorted(vehicles),
        "officers": officers,
        "narrative_redacted": text,
    }
    out["leaks"] = leak_check(out, list(name_to_id) + [o for o in (fields.get("io_name"), fields.get("registered_by")) if o],
                              [comp.get("phone")])
    return out


def _place_address(addr):
    """A public spot (chowk, road, shop) is kept; a home (flat/house number) shrinks to its locality."""
    if re.search(r"(फ्लॅट|फँल्ट|फ्लैट|फलॅट|रूम|रुम|घर)\s*(नं|नंबर|क्र)|(?<![\d/])\d{1,4}\s*,?\s*[एबीसी]\s*विंग", addr or ""):
        return f"[HOME] {locality(addr)}"
    return _strip_house(addr)


def _strip_house(addr):
    addr = BUILDING.sub("[BUILDING] ", addr or "")
    for pat in HOUSE_PATTERNS:
        addr = re.sub(pat, "[HOUSE]", addr)
    return addr


def leak_check(out: dict, names: list[str], phones: list) -> list[str]:
    """Return any real name word or phone number still present in the output."""
    blob = json.dumps(out, ensure_ascii=False)
    leaks = []
    for n in names:
        for tok in n.split():
            if len(tok) >= 3 and tok not in STOP and tok not in NON_NAME and re.search(NOT_DEV + re.escape(tok) + r"(?![ऀ-ॿ])", blob, re.I):
                leaks.append(tok)
    leaks += [p for p in phones if p and p in blob]
    return sorted(set(leaks))
