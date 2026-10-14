# Build Log — FIRGraph-RAG

A dated record of what was built, what broke, and how it was fixed.
Use this for the "Challenges faced" section of the report and viva.
No real names, phone numbers or addresses from FIRs appear in this file.

---

## 2026-10-14 — Day 1: data source, legal check, extraction prototype

### Data source found
- The Maharashtra Police CCTNS citizen portal has a **Search & View Published FIR** page
  (`citizen.mahapolice.gov.in/Citizen/MH/PublishedFIRs.aspx`).
- Search by unit (e.g. Pune City), police station and a date range of less than 90 days.
  No FIR number or CAPTCHA was needed when tested manually.
- The result table already shows police station, date, FIR number and **sections** before
  downloading, so sensitive cases can be filtered out before any PDF is fetched.
- First try was the Pune City Police "Atrocities Act" monthly registers. **Rejected:** they
  are summary tables with no names (so no person-to-person links) and contain caste data.

### Legal / ethics check (summary — not legal advice; guide sign-off pending)
- Supreme Court (*Youth Bar Association v. Union of India*, 2016) directs police to publish
  non-sensitive FIRs online, so the source is official and public.
- DPDP Act 2023 s.3(c)(ii) excludes data published under a legal obligation; s.17(2)(b)
  exempts research use if data is not used for decisions about individuals and follows
  prescribed safeguards (minimisation, accuracy, limited retention, security).
- **Juvenile Justice Act s.74** forbids disclosing anything that identifies a child in
  conflict with law, child victim or child witness. → Any FIR involving a person under 18
  is dropped entirely.
- Also skipped: POCSO, sexual offences and offences against women/children (BNS ch. V,
  s.63–99), SC/ST Atrocities Act, dowry, domestic violence, deaths/suicide (BNS 103, 105,
  106, 108) and FIRs with an inquest number.

### Challenge 1 — PDF text layer is garbage
- Extracting text directly from the published PDFs gives broken Marathi
  (e.g. `प्रथम` → `Ĥम`, `संहिता` → `संदहता`) because of an old font encoding.
- **Fix:** ignore the text layer; render every page to a 300-dpi image (PyMuPDF) and OCR it
  with Tesseract using the `mar+eng` models. Result: clean Unicode Marathi.

### Challenge 2 — OCR loses table structure
- In the accused table, OCR dropped the row numbers for several rows and the surname often
  wrapped onto the next line, where it looked like part of the address.
- **Fix:** detect each accused row by its address marker (`1. ...`) instead of its row
  number; number rows in order; accept a wrapped word as a surname only if a matching
  name phrase exists in the narrative (fuzzy match allows OCR typos).
- One row's first name was lost entirely by OCR → the parser flags it `needs_review`
  instead of guessing.

### Challenge 3 — same person spelled differently in one FIR
- One FIR spells the same person's first name three different ways (clerk typo + OCR).
- **Fix (partial):** fuzzy clustering — same surname + first names ≥80% similar → same ID.

### Challenge 4 — minors
- Test FIR 0035 contains an accused born in 2010 and a 17-year-old family member.
- **Fix:** `minors.py` checks birth years in the accused/complainant tables **and** ages
  written in the narrative (`वय 17 वर्षे`) plus words like `अल्पवयीन`. Any hit → FIR dropped.
  Both signals caught FIR 0035 independently.

### Challenge 5 — rule-based name redaction is not enough
- Test FIR 0033 (2 parties, road accident): all names, phone, flat number and both vehicle
  plates redacted; **leak check: 0 leaks**. Vehicle numbers written three ways
  (in English letters, spelled out in Marathi, and OCR-mangled with the state code missing)
  all mapped to the same vehicle ID.
- Stress test on FIR 0035 (16-person family fight, never saved because of the minor):
  rules over-captured words around names (e.g. "then + name", "son + name") as part of the
  name, split one person into several IDs, and the **leak check found 3 surviving
  surname/middle-name words**.
- **Decision:** move to a hybrid approach — a *local* LLM (runs on the laptop, so no data
  leaves it) proposes names, the rules catch structured fields, and the automatic leak
  check quarantines any FIR that still leaks for manual review.

### Dev environment decisions
- Dev laptop: Ryzen 7 5800HS, 16 GB RAM, RTX 3050 4 GB, Windows. This is enough for a 7–8B
  local model in 4-bit, so the **local LLM** route (Ollama) is feasible. That was the main
  privacy requirement: raw FIR text never goes to a cloud API.
- Scope fixed: **Alankar Police Station, Pune City, Jan–Mar 2026.**
- The prototype was first developed in a cloud workspace on Linux. The project then moved to the
  Windows laptop (`Documents/FIRGraph-RAG`), because the police portal has to be reached from
  a normal home connection and the real data must stay on the laptop.
- Created `check_setup.ps1` to check prerequisites in one go (Git, Python, Node 20+, Ollama,
  Docker, Tesseract + Marathi pack, GPU).
- Changed `TESSDATA` in `config.py` from a Linux path to `None` so Windows uses Tesseract's
  default location.

### Feasibility test — graph + multi-hop queries (`tests/graph_feasibility.py`)
- Goal: prove the redacted output can actually answer multi-hop questions as a graph.
- Neo4j/Docker weren't available in the cloud workspace, so the test uses **Kuzu**, an
  embedded graph DB that speaks the same Cypher. No server is needed. The real system keeps Neo4j.
- Input: real FIR 0033 (OCR → parse → minor check → redaction, 0 leaks) + **one synthetic test
  record** invented to reuse the real accused and vehicle IDs, simulating a repeat. It is clearly
  marked SYNTHETIC and is never presented as real data.
- Results, all 4 correct:
  1. Accused in more than one FIR → `P_0003` in both FIRs ✅
  2. Vehicle in more than one FIR → `V_002` in both ✅
  3. Shortest path between two complainants → `P_0001 → FIR 0033 → V_002 → FIR TEST-001 → P_9001` ✅
  4. FIRs per section → BNS 281 = 2 ✅
- **Bug found in my own test:** the first run of Q1 returned nothing because the test record
  hard-coded the accused as `P_0002`, but the vault had given the real accused `P_0003`
  (IDs are assigned in the order names are found). Fixed by reading the ID from the real record.
  Lesson for the real pipeline: **never assume pseudonym numbers**. Always look them up from the vault.

### Feasibility test — police portal automation → FAILED, design changed
- The cloud workspace's network blocks the police site (HTTP 403 at the proxy).
- The in-app browser on the laptop returned "site policy check unavailable".
- On the laptop, `playwright codegen` opened the portal (no CAPTCHA), but the **Unit dropdown
  stayed empty** ("Select" only) in the automated browser, even after a reload. In normal Chrome
  the same dropdown lists PUNE CITY. Most likely the site serves its data only to non-automated
  browsers.
- **Decision:** no attempt to bypass it (no stealth plugins, no request spoofing), because that
  would break the responsible-scraping requirement (NFR8).
- **New approach: manual collection.** The team searches the portal in normal Chrome, checks the
  Sections column, skips excluded categories by eye, and downloads the rest into
  `data/raw_pdfs/`. The code still runs `skip_filter` and `minor_check` as a safety net.
  Start with 30–40 FIRs of mixed types (accident, theft, cheating, assault).
- **Temporary deviation from NFR1:** the laptop has no shell access from the build session, so
  during development the PDFs are processed in a private cloud workspace (deleted at session end).
  No real names go to GitHub or any LLM. After Review 3, processing moves to the laptop.

### First batch run — 9 real FIRs (Alankar PS, 11–28 Feb 2026) with `pipeline/run.py`
New: `pipeline/run.py` runs every PDF through all stages and writes `data/report.csv`
(one row per FIR, no names). Results after the fixes below:

| Outcome | FIRs |
|---|---|
| Passed rules + automatic leak check | 8 |
| Skipped (person under 18) | 1 (FIR 35) |
| Errors | 0 |

#### Challenge 6 — OCR garbles section numbers → sensitive-case filter unreliable
- OCR read `324(4)` as `3244)` and `303(2)` as `320392)`, because the act name wraps inside the
  table cell. A wrong section number could let a sensitive case through the filter.
- Finding: the PDF's own text layer has broken Marathi letters but **clean digits**.
- **Fix — hybrid reading (`pipeline/acts.py`):** section numbers come from the PDF text layer,
  the Act is recognised from either layer, and the sensitive-Act keyword check runs on both
  the text layer and the clean OCR Marathi. Any Act the code can't recognise → FIR skipped
  for manual check. Result: **all sections on all 9 FIRs read correctly** (checked against the
  portal's Sections column). Offence names added for common BNS sections (e.g. 303 = theft).

#### Challenge 7 — the leak check gave false confidence
- Round 1: 3 FIRs quarantined. Causes: (a) a first name was caught but the middle name and
  surname right after it stayed visible; (b) a person mentioned with no relation word before
  their name was missed; (c) everyday words ("police", "station", "hall", "society") were
  wrongly captured as name parts, causing false alarms.
- Fixes: absorb name words next to a `[P_x]` tag; learn surnames from every name found and
  search again; a `NON_NAME` word list; building and society names in addresses → `[BUILDING]`.
- Round 2: **8/8 passed the automatic leak check.**
- **But a manual read of all 8 anonymised narratives found real names still present in 6 of
  8 FIRs.** These were roommates, a neighbour, a domestic worker, a relative, a family friend,
  and police officers named in the story. The leak check only looks for names the system has
  already found, so a person it never detected can't be flagged.
- Also found unmasked: a driving-licence number, IMEI numbers, a laptop serial number, and
  vehicle plates written letter-by-letter with spaces/dots (e.g. `एम एच 12 ए बी 1234`).
  **Fixed** with ID-number patterns and a spaced-plate pattern.
- **Conclusion: rules + a self-check cannot anonymise free-text Marathi narratives.** A model
  that recognises person names from context (NER) is required. Status of these FIRs changed
  from `PROCESSED` to `RULES_PASSED — awaiting LLM name check`, and nothing goes to any cloud
  LLM or outside the team until stage 1b (local LLM NER on the laptop) passes a manual audit.
- Note for evaluation: report anonymisation quality with a **manual audit**, not just the
  automatic leak check.

#### Other observations
- 4 of 8 FIRs have no named accused (unknown thieves / snatchers), so those cases link to the
  rest of the graph through places, sections and vehicles, not people.
- One FIR mentions a granddaughter with no age. It isn't blocked (no age, not a party to the
  case), but she is pseudonymised. To review with the guide: should any mention of a child
  relative block the FIR?
- OCR speed: about 1–2 min per FIR on the 2-core cloud workspace.

### Setup issue — Tesseract installed but not found; Marathi file "access denied"
- `winget` reported Tesseract already installed, but `tesseract` wasn't on PATH. Fixed by
  adding `C:\Program Files\Tesseract-OCR` to the user PATH.
- Downloading `mar.traineddata` into `C:\Program Files\...` failed (needs admin).
- **Fix:** keep the language files in the project's own `tessdata/` folder (git-ignored);
  `config.py` uses it automatically when `tessdata/mar.traineddata` exists.

### First batch: 9 real FIRs (Alankar PS, Feb 2026) through the whole stage-1 pipeline
New file `pipeline/run.py` runs every PDF through OCR → split → parse → skip checks → redaction →
leak check and writes `data/report.csv` (no names in it).

Offence mix in the batch: road accidents, rope-across-road injury, mobile theft from a car, laptop
theft from a parked car, chain snatching, cheating/breach of trust, house-trespass robbery,
breach of an externment order, and one group assault.

**Challenge 6: OCR garbles section numbers.** `324(4)` came out as `3244)`, `303(2)` as `320392)`.
That's dangerous, because the sensitive-case filter depends on section numbers.
- Discovery: the PDF's own text layer has broken Marathi letters but **clean digits**.
- **Fix:** new `pipeline/acts.py` uses a hybrid read: section numbers from the text layer; act names
  recognised from garbled or clean text; sensitive-Act keywords checked in both the text layer and
  the OCR Marathi. If any Act can't be recognised, the FIR is held for manual check.
- Result: **all sections on all 9 FIRs read exactly right**, matching the portal's own table.
- Added English offence names for common BNS sections (e.g. 303 → theft, 318 → cheating).

**Challenge 7: leaks, round 1.** 3 of 8 FIRs were quarantined by the leak check. Causes:
(a) only a first name was tagged, leaving middle name + surname visible; (b) a person mentioned
without a relation word before the name was never detected; (c) everyday words (police station,
hall, society) were wrongly captured as name parts and then flagged.
- **Fix:** a list of non-name words; surnames learnt from every detected name (two rounds);
  name words next to a tag are absorbed into it; a leftover name word shared by several people
  becomes `[NAME]`; building/society/hall names in addresses become `[BUILDING]`.
- Result: leak check passed 8 of 8.

**Challenge 8 (key finding): the automatic leak check gives false confidence.**
- A manual read of all 8 "clean" outputs found **real names still present in 6 of 8** (FIRs 26, 27, 28, 29, 30, 32): roommates,
  a neighbour, domestic staff, a relative, and police officers mentioned in the story.
  (First count said 7 of 8; on re-check, FIR 31's only problems were a licence and a serial number.) None of them
  appear in the form's tables, so the rules never knew them and the leak check couldn't flag them.
- It also found unmasked identifiers: driving-licence number, phone IMEI numbers, a laptop serial
  number, and plates written with spaced letters (e.g. `एम एच 12 ए बी 1234`).
- **Fixes now:** regexes for licence numbers, 14–17-digit IDs (IMEI/account), serial numbers, and
  spaced/dotted plates. All verified on the affected FIRs.
- **Design decision:** rules **cannot** reliably find every person in free Marathi text. A local-LLM
  name-finding step (stage 1b) is **required**, not optional. Until it exists, outputs are labelled
  `RULES_PASSED (awaiting LLM name check)`, never "safe", and must not go to any external service.
- Evaluation plan updated: leak rate will be measured by **manual audit**, not just the automatic check.

| Result (9 FIRs) | Count |
|---|---|
| Sections read correctly (hybrid) | 9 / 9 |
| Skipped: minor involved | 1 (FIR 35) |
| Passed rules + automatic leak check | 8 / 8 |
| Manual audit: still had a real name | 6 / 8 → needs LLM step |
| Errors | 0 |

**Windows OCR setup:** downloading the Marathi model into `Program Files` needs admin rights. Fix:
keep language files in the project's own `tessdata/` folder (git-ignored); `config.py` uses it
automatically, and `ocr.py` finds `tesseract.exe` even when it isn't on PATH.

### Setup issue — `pip` not recognised on Windows
- `pip` wasn't on PATH even though Python 3.12 was installed.
- **Fix:** use a project virtual environment (`python -m venv .venv`, then
  `.\.venv\Scripts\Activate.ps1`) and call `python -m pip …`. Added to SETUP.md.

### Base projects — license check
| Project | License | How we use it |
|---|---|---|
| neo4j-labs/llm-graph-builder | Apache-2.0 | Reference for architecture/UI ideas; any reused code credited with NOTICE |
| neo4j/neo4j-graphrag-python | Apache-2.0 (to confirm in LICENSE file) | Used as a library for KG construction and retrievers |
| rathcoding/knowledge-graph-rag | No license found | Ideas only — no code copied |
| ManishKondoju/CrimeInvestigationGraph | No license found | Ideas only — no code copied |

### First run on the Windows laptop — Unicode crash at the end
- `python -m pipeline.run` on the laptop processed all 9 FIRs with the **same results as the cloud run**
  (8 RULES_PASSED, FIR 35 skipped for a minor), then crashed while saving the name vault:
  `UnicodeEncodeError: 'charmap' codec can't encode characters`.
- Cause: on Windows, Python writes text files in the old cp1252 code page unless told otherwise,
  and cp1252 has no Marathi letters. Linux defaults to UTF-8, so the cloud tests never showed it.
- **Fix:** every file read/write now says `encoding="utf-8"`, and console output is switched to UTF-8.
- Lesson: test on the target OS. Cross-platform text encoding is a classic bug.
- Knock-on bug: the crashed save had left an **empty** `vault.json`, so the next run failed to load it.
  **Fix:** the vault is now saved atomically (write a temp file, then swap it in); an empty vault file
  is treated as a fresh start; a damaged non-empty one stops the run with a clear message instead
  of silently re-numbering everyone.

---

## 2026-10-14 (evening) — Stages 1b, 2 and 3: first end-to-end system

Goal for the day: get the first half of the project running on the laptop, from PDF to answered question.

### Stage 1b — local LLM name finder (`pipeline/ner.py`, `pipeline/llm.py`)
- Model: **qwen2.5:7b** via Ollama on the laptop. Chosen because it handles Devanagari better than
  most 7B models and fits 16 GB RAM + 4 GB GPU. FIR text never leaves the laptop.
  (`deepseek-r1:1.5b` was already installed. It wasn't removed, since Ollama keeps models side by side,
  and it's too small for reliable Marathi name finding.)
- Narrative is split into ~900-character chunks at sentence ends, so a name is never cut in half.
- The model returns JSON `{"names": [...]}`, at temperature 0 for repeatable output.
- **Guards against model mistakes:**
  - a returned name must occur verbatim in the text, otherwise it is dropped (no invented names);
  - titles (श्री, सौ, डॉ, police ranks) are stripped;
  - known Pune areas and place-shaped words (…नगर, …पेठ, …वाडी, …चौक) are rejected. Found in testing:
    a model may label an area such as कर्वेनगर as a person.
- New names get pseudonyms from the same vault, then the same "absorb leftover name words" step runs.
- Final leak check covers every real name the vault knows, across FIRs (also with spaces removed).
  Status becomes `LLM_CHECKED` or `QUARANTINED`.
- Tested in the cloud workspace with a stand-in for the LLM (no model there). The leaked names from
  the audit were removed, an invented name was rejected, and an area name was rejected.
  **The real-model test runs on the laptop.**

### Stage 2 — knowledge graph (`pipeline/graph.py`)
- Kuzu embedded graph DB (Cypher, no server or Docker), stored in `data/graph/` (git-ignored).
- Loads only `LLM_CHECKED` FIRs; `--include-rules` exists for testing only.
- Nodes: FIR, Person, Vehicle, Officer, Station, Section (with English offence name), Locality.
  Relations: COMPLAINANT_IN, ACCUSED_IN, MENTIONED_IN, VEHICLE_IN, INVESTIGATED_BY, REGISTERED_BY,
  REGISTERED_AT, CHARGED_UNDER, OCCURRED_IN, LIVES_IN.
- First build (9 FIRs → 8 loaded): 8 FIRs, 41 people, 5 vehicles, 8 officers, 17 sections, 7 localities.
- Added offence names for Motor Vehicles Act and Maharashtra Police Act sections, and more Pune
  areas (नळस्टॉप, पौड, वनाज …), after the first build showed unnamed sections and unplaced FIRs.

### Stage 3 — ask questions, GraphRAG text-to-Cypher (`pipeline/ask.py`)
- Question → local LLM writes one Cypher query (given the schema + 4 examples) → graph runs it →
  LLM answers from the returned rows only. All four steps are printed, so the reasoning is visible.
- Safety: any query containing CREATE / MERGE / SET / DELETE / DROP … is refused, and the graph is
  opened read-only.
- If a query errors, the error goes back to the model once to fix it (self-repair).
- Tested: offence counts, FIRs by locality, officer workload, date filter, write-refusal. The whole
  ask() flow was tested with a stand-in model.

### Run order (also in docs/RUN.md)
`pipeline.run` → `pipeline.ner` → `pipeline.graph` → `pipeline.ask`

### Demo-safety check and a full re-audit (14 Oct, evening)
Prompted by a review question: *"the demo opens FIR 33's output, so is FIR 33 one of the six that
leaked names?"*

- **Process flaw found in my own audit:** the first manual audit printed only the first 1,800
  characters of each narrative, so the ends of the stories were never read. All 8 were re-read
  **in full**.
- Result: the count holds (names leaked in **6 of 8**: FIRs 26, 27, 28, 29, 30, 32), and **FIR 33 and
  FIR 31 are clean end to end**, so the demo uses only those two. The full read found more than the
  partial one:
  - **28 leaked name words** in total, including five police officers named in FIR 29, a rescuer
    and a neighbour in FIR 30, and a name written in **English letters** in FIR 28;
  - an 11-digit **bank account number** (FIR 28);
  - **home-address details spilling onto the next line** past the masked part (FIRs 26, 30, 32);
  - FIR 30's "place of occurrence" was the victim's **own flat**, with flat number and building name.
- **Bug found while reading FIR 28:** the surname finder took the word before a name as a first name
  ("मध्ये" = "in"). That one man became **4 different IDs**, and every "मध्ये" in the story was
  replaced by a person tag, creating fake people for the graph.

**Fixes**
- Words like मध्ये, नंतर, तेव्हा, की, and words ending in grammar suffixes (-नंतर, -ताना, -ून, -साठी…)
  can no longer be read as names. The surname finder walks outward from the surname and stops at the
  first non-name word. Names sharing their last two words are merged into one person.
  Result: **0 fake people** (the vault went from 41 to 32 entries); FIR 28 now has 7 genuine person tags.
- Residence addresses are masked across line breaks, up to the phone/age/occupation marker.
- Bank account numbers near an "account" word → `[ACCOUNT]`. More building-name spellings.
- A place of occurrence that is a home (flat/house number, wing) → `[HOME] <locality>`.

**New test: `tests/check_leaks.py`**, with the manual audit as ground truth
- `data/audit/leaked_names.json` (private, git-ignored) lists every word a human found left behind,
  per FIR. The test fails a FIR if any of them still appears in its output. It prints counts only,
  never names (`--show` prints them for fixing; never on a projector).
- **Pass mark for stage 1b: every leaked name caught.** Extra words wrongly masked are acceptable.
- **Baseline, rules only:** names caught **0 / 28** (expected: these are exactly what rules miss);
  other identifying details caught **6 / 6** after the fixes above.
- Next: run stage 1b with the real model on the laptop and re-run this test.

### Before the first GitHub push: real names found in code comments
- A pre-commit check found **real people's names and vehicle numbers from the FIRs inside code
  comments and docstrings**. They had been copied in as examples while writing the parsers:
  8 names (including the minor from FIR 35 and a police officer), 4 vehicle numbers, and one name in
  this log. `.gitignore` protects the data folder, but it can't protect text typed into code.
- **Fix:** every example was replaced with an invented one (रमेश/सुनीता जाधव, MH 12 AB 1234), and the
  invented names were checked so they don't match anyone in the FIRs.
- **New tool: `tests/scan_repo.py`.** It collects every name, officer and plate from the local FIRs
  (including skipped ones), the vault and the audit list, then searches every file git would commit.
  It prints only file:line and the word's length, never the word, and exits with an error if
  anything is found. It was tested by planting a real name: caught, commit refused; removed: clean.
- **Rule from now on:** run `python -m tests.scan_repo` before every commit. Code examples use
  invented names only.
- Also caught before pushing: `git init` was first run in the home folder (`C:\Users\ASUS`) instead of
  the project folder, which would have offered `.ssh` and `.aws` keys for commit. Nothing was added;
  the stray `.git` was removed. Lesson: check `pwd` before `git init`.
