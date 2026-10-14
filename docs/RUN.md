# How to run FIRGraph-RAG (Windows)

Open PowerShell:

```powershell
cd $HOME\Documents\FIRGraph-RAG
.\.venv\Scripts\Activate.ps1
```

Ollama must be running (the Ollama app in the system tray), with the model pulled once:
`ollama pull qwen2.5:7b`

| Step | Command | What it does |
|---|---|---|
| 1 | `python -m pipeline.run` | PDFs in `data\raw_pdfs` → OCR → fields → skip checks → rule redaction |
| 2 | `python -m pipeline.ner` | Local LLM finds names the rules missed → `LLM_CHECKED` |
| 3 | `python -m pipeline.graph` | Builds the knowledge graph from checked FIRs |
| 4 | `python -m pipeline.ask "your question"` | Question → Cypher → result → answer |
| ✔ | `python -m tests.scan_repo` | **Before every git commit:** no real name/plate in code or docs |
| ✔ | `python -m tests.check_leaks` | Pass/fail against the manual audit: did every leaked name get caught? |

`python -m pipeline.ask` with no question gives an interactive prompt.

**After adding new PDFs:** run steps 1–3 again. Step 1 reuses cached OCR, so only new FIRs are slow.

## Questions to try

- Which vehicles appear in more than one FIR?
- How many FIRs are there for each type of offence?
- Which FIRs happened in कर्वेनगर?
- Which officer investigated the most FIRs?
- List all theft FIRs with their dates.
- Which people are mentioned in FIR 0033/2026, and in what role?

## Review demo (≈5 min)

1. Open a FIR PDF from `data\raw_pdfs`. Copy some Marathi text out of it to show it's garbled
   (why we OCR).
2. `python -m pipeline.run` → point at FIR 35 being SKIPPED (minor).
3. Open `data\processed\0033 Publish FIR.json` → pseudonyms `[P_…]`, `[V_…]`, `[PHONE]`.
   **Only FIR 33 or 31.** These are the two verified clean by a full manual read. Do not open any
   other FIR's output on screen until `tests.check_leaks` shows PASS for it.
4. `python -m pipeline.graph` → node counts.
5. `python -m pipeline.ask "How many FIRs are there for each type of offence?"` → show the Cypher,
   the rows and the answer.
6. Open `docs\BUILD_LOG.md` → challenges.

**Never show real names on screen.** Don't run `tests.check_leaks --show` on a projector. Don't open `data\ocr\` or `data\vault\` during a demo.
