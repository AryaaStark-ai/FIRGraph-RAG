# Setup (Windows)

Laptop used for development: ASUS Vivobook, Ryzen 7 5800HS, 16 GB RAM, NVIDIA RTX 3050 (4 GB), Windows 64-bit.

## 1. Check what's already installed

Open **PowerShell** in the project folder and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\check_setup.ps1
```

Anything marked `[MISSING]` or shown in yellow needs installing (step 2).

## 2. Install what's missing

| Tool | Why | How to install |
|---|---|---|
| **Git** | version control, push to GitHub | `winget install Git.Git` |
| **Python 3.12** | the whole pipeline | already installed ✅ |
| **Node.js 20+** | React UI | `winget install OpenJS.NodeJS.LTS` (if `node --version` is below 20) |
| **Ollama** | runs the LLM locally so FIR text never leaves the laptop | already installed ✅ |
| **Docker Desktop** | runs Neo4j | `winget install Docker.DockerDesktop`, then restart and open Docker Desktop once |
| **Tesseract OCR** | reads Marathi from FIR page images | `winget install UB-Mannheim.TesseractOCR`, then add `C:\Program Files\Tesseract-OCR` to your user PATH (step 2b) |

### 2b. Tesseract PATH + Marathi language file (no admin needed)

```powershell
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path","User") + ";C:\Program Files\Tesseract-OCR", "User")
# open a NEW PowerShell, then:
cd $HOME\Documents\FIRGraph-RAG
mkdir tessdata
Copy-Item "C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata","C:\Program Files\Tesseract-OCR\tessdata\osd.traineddata" tessdata\
Invoke-WebRequest "https://github.com/tesseract-ocr/tessdata_best/raw/main/mar.traineddata" -OutFile tessdata\mar.traineddata
tesseract --list-langs --tessdata-dir tessdata      # should list eng, mar, osd
```

The project's `config.py` picks up `tessdata/` automatically.

After installing, close and reopen PowerShell and run `check_setup.ps1` again.

## 3. Python environment

If PowerShell says `pip` is not recognised, that's expected: always use `python -m pip` inside the
virtual environment. If activation says "running scripts is disabled", run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

```powershell
cd $HOME\Documents\FIRGraph-RAG
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium   # optional: scraper is on hold
```

## 4. Local LLM

Don't pull a model yet. The model is chosen in a later step and recorded in `BUILD_LOG.md`.
(With 4 GB of VRAM, a 7–8B model in 4-bit runs partly on the GPU.)

## 5. Neo4j (later stage)

```powershell
docker run -d --name firgraph-neo4j -p 7474:7474 -p 7687:7687 `
  -e NEO4J_AUTH=neo4j/<choose-a-password> -e NEO4J_PLUGINS='["apoc"]' neo4j:5
```

## 6. Run the extraction pipeline

```powershell
.\.venv\Scripts\Activate.ps1
python -m pipeline.run          # all PDFs in data\raw_pdfs -> data\report.csv
python -m tests.graph_feasibility data\ocr\0033_Publish_FIR.txt
```
