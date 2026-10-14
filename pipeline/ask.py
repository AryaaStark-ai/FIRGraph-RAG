"""Stage 3: ask the knowledge graph a question in plain English (GraphRAG, text-to-Cypher).

    python -m pipeline.ask "Which vehicles appear in more than one FIR?"
    python -m pipeline.ask                      # interactive: type questions, blank line to quit

Steps it prints, so the reasoning is visible:
  1. QUESTION
  2. CYPHER   - the local LLM turns the question into a graph query, given the schema
  3. RESULT   - rows returned by the graph (read-only; write queries are refused)
  4. ANSWER   - the LLM answers using ONLY those rows
If the query fails, the error goes back to the LLM once to fix it.
"""
import re
import sys

import kuzu

from .graph import GRAPH_DIR, SCHEMA_TEXT
from .llm import MODEL, chat

CYPHER_SYSTEM = f"""You translate questions into ONE read-only Cypher query for the Kuzu graph database.
{SCHEMA_TEXT}

Rules:
- Output ONLY the Cypher query. No explanation, no markdown fences.
- Read-only: MATCH / WHERE / WITH / RETURN / ORDER BY / LIMIT only. Never CREATE, MERGE, SET, DELETE.
- Use property names exactly as in the schema. Dates are DATE values: date('2026-02-15').
- For crime types, match Section.offence with CONTAINS, e.g. s.offence CONTAINS 'theft'.
- Variable-length shortest path in Kuzu:  MATCH p = (a)-[* SHORTEST 1..6]-(b) RETURN nodes(p)
- To return node ids from a path: properties(nodes(p), 'id')
- Use LIMIT 50 unless counting.

Examples:
Q: Which vehicles appear in more than one FIR?
MATCH (v:Vehicle)-[:VEHICLE_IN]->(f:FIR) WITH v, collect(f.id) AS firs WHERE size(firs) > 1 RETURN v.id, firs
Q: How many FIRs are there for each type of offence?
MATCH (f:FIR)-[:CHARGED_UNDER]->(s:Section) RETURN s.offence, count(DISTINCT f) AS firs ORDER BY firs DESC
Q: Which FIRs happened in कोथरुड?
MATCH (f:FIR)-[:OCCURRED_IN]->(l:Locality {{id:'कोथरुड'}}) RETURN f.id, f.occurred
Q: Which officer investigated the most FIRs?
MATCH (f:FIR)-[:INVESTIGATED_BY]->(o:Officer) RETURN o.id, o.rank, count(f) AS n ORDER BY n DESC LIMIT 1"""

ANSWER_SYSTEM = """You answer questions about a police FIR knowledge graph.
Use ONLY the query result given. If it is empty, say nothing matched.
People are pseudonyms like P_0003; never guess real names. Be short and specific."""

WRITE_WORDS = re.compile(r"\b(CREATE|MERGE|SET|DELETE|DETACH|DROP|ALTER|COPY|INSTALL|LOAD|CALL)\b", re.I)


def clean_cypher(text: str) -> str:
    text = re.sub(r"^```\w*|```$", "", text.strip(), flags=re.M).strip()
    return text.rstrip(";")


def run_query(conn, cypher: str):
    if WRITE_WORDS.search(cypher):
        raise ValueError("refused: only read-only queries are allowed")
    r = conn.execute(cypher)
    cols = r.get_column_names()
    rows = []
    while r.has_next() and len(rows) < 100:
        rows.append(r.get_next())
    return cols, rows


def ask(conn, question: str, verbose=True):
    cypher = clean_cypher(chat(CYPHER_SYSTEM, f"Q: {question}"))
    try:
        cols, rows = run_query(conn, cypher)
    except Exception as e:                                 # one self-repair attempt
        if verbose:
            print(f"\n(first query failed: {e}; asking the model to fix it)")
        cypher = clean_cypher(chat(CYPHER_SYSTEM, f"Q: {question}\nYour previous query:\n{cypher}\n"
                                   f"failed with error:\n{e}\nWrite a corrected query."))
        cols, rows = run_query(conn, cypher)
    table = "\n".join([" | ".join(cols)] + [" | ".join(map(str, r)) for r in rows]) or "(no rows)"
    answer = chat(ANSWER_SYSTEM, f"Question: {question}\n\nQuery result:\n{table}")
    if verbose:
        print(f"\nQUESTION: {question}\n\nCYPHER:\n{cypher}\n\nRESULT ({len(rows)} rows):\n{table}\n\nANSWER:\n{answer}\n")
    return {"question": question, "cypher": cypher, "columns": cols, "rows": rows, "answer": answer}


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if not GRAPH_DIR.exists():
        raise SystemExit("No graph yet. Run:  python -m pipeline.graph")
    conn = kuzu.Connection(kuzu.Database(str(GRAPH_DIR), read_only=True))
    print(f"Model: {MODEL}")
    if len(sys.argv) > 1:
        ask(conn, " ".join(sys.argv[1:]))
        return
    while True:
        q = input("\nAsk a question (blank to quit): ").strip()
        if not q:
            break
        try:
            ask(conn, q)
        except Exception as e:
            print(f"Could not answer: {e}")


if __name__ == "__main__":
    main()
