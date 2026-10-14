# FIRGraph-RAG

**A Knowledge Graph-Based Retrieval System for Multi-Hop Querying over Marathi FIR Documents**

B.E. Final Year Project · Artificial Intelligence & Data Science · Dr. D.Y. Patil Institute of Technology, Pune

> 🚧 Work in progress. Stage 1 (data extraction) is being built. See [`docs/BUILD_LOG.md`](docs/BUILD_LOG.md) for progress and challenges.

---

## The idea in one line

A chatbot that reads publicly published police FIRs and answers questions about **how people, places, vehicles and cases are connected**, and shows the path it took to reach the answer.

## Why a graph?

Normal RAG is like Ctrl+F on a pile of documents: it finds paragraphs that *sound similar* to the question.
An FIR isn't just text. It's a web of people, places, dates, vehicles and offences that are linked to each other.

FIRGraph-RAG stores that web as a **knowledge graph** (Neo4j). To answer "how is A connected to B?", it walks the graph, the way an investigator follows red strings on a detective's wall.

| Question | Vector RAG | GraphRAG |
|---|---|---|
| "What happened in FIR 33?" | ✅ | ✅ |
| "Does any vehicle appear in more than one FIR?" | ❌ needs joining facts across documents | ✅ one graph query |
| "Which accused appear in cases at two different police stations?" | ❌ | ✅ |

## Vision

1. Use **real, publicly published** Maharashtra Police FIRs, not synthetic data.
2. Handle **Marathi**, scanned forms and messy OCR, which most similar projects avoid.
3. **Privacy first**: every person is pseudonymised (`P_0001`), minors' cases are excluded, and no raw FIR leaves the laptop.
4. **Prove it works**: benchmark GraphRAG against a plain vector-RAG baseline on the same question set.
5. **Explainable answers**: the UI shows the reasoning and highlights the graph path used.

## Architecture (planned)

```
CCTNS public portal
   │  Playwright scraper (filters out sensitive cases BEFORE download)
   ▼
FIR PDFs ──► page images ──► Tesseract OCR (mar+eng) ──► form-section splitter
   ▼
Field parser ──► minor check (drop FIR) ──► redaction + pseudonymisation ──► leak check
   ▼
Local LLM (Ollama) extracts entities & relations from the redacted narrative
   ▼
Neo4j knowledge graph ──► GraphRAG (neo4j-graphrag) ◄──► FastAPI ◄──► React UI
                                       ▲
                       Vector-RAG baseline (ChromaDB) for evaluation
```

## Tech stack

Python · Tesseract OCR · PyMuPDF · Playwright · Ollama (local LLM) · Pydantic · Neo4j · neo4j-graphrag · FastAPI · React · ChromaDB

Reasons for each choice: [`docs/TECH_STACK.md`](docs/TECH_STACK.md) *(coming)*.

## Project status

| Stage | Status |
|---|---|
| Data source + legal/ethics review | ✅ done |
| OCR, section split, field parser, minor check | ✅ prototype, tested on 2 FIRs |
| Redaction + leak check | ✅ rules + local-LLM name finder (stage 1b) |
| Data collection | ✅ manual download (portal blocks automated browsers; see build log) |
| Knowledge graph | ✅ prototype on Kuzu (embedded Cypher); Neo4j later |
| GraphRAG question answering | ✅ command-line prototype (text-to-Cypher) |
| LLM relation extraction from narratives | ⏳ |
| Web UI | ⏳ |
| Evaluation vs vector RAG | ⏳ |

## Data & ethics

- Source: FIRs that Maharashtra Police publish under the Supreme Court's direction in *Youth Bar Association v. Union of India* (2016).
- **No FIR data is stored in this repository.** The `data/` folder is git-ignored.
- Excluded entirely: any case involving a person under 18 (Juvenile Justice Act s.74), sexual offences/POCSO, SC/ST Atrocities Act cases, dowry and domestic violence, and deaths.
- The system is for research on retrieval methods. It makes **no** risk scores or judgements about individuals.

Details: [`docs/ETHICS_AND_LEGAL.md`](docs/ETHICS_AND_LEGAL.md) *(coming)*.

## Setup

See [`docs/SETUP.md`](docs/SETUP.md), then [`docs/RUN.md`](docs/RUN.md).

## Acknowledgements

- [neo4j/neo4j-graphrag-python](https://github.com/neo4j/neo4j-graphrag-python), used as a library (Apache-2.0)
- [neo4j-labs/llm-graph-builder](https://github.com/neo4j-labs/llm-graph-builder), architecture reference (Apache-2.0)
