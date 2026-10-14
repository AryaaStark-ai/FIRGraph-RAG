"""Stage 2: load anonymised FIRs into a knowledge graph.

Uses Kuzu, an embedded graph database that speaks Cypher (like Neo4j) and runs inside
Python, so no Docker or server is needed for the prototype. Moving to Neo4j later
means the same Cypher, a different driver.

    python -m pipeline.graph                    # load only LLM_CHECKED FIRs (safe)
    python -m pipeline.graph --include-rules    # TESTING ONLY: also RULES_PASSED FIRs

The graph holds pseudonyms only (P_0001, V_001, O_001), never real names.
"""
import json
import re
import shutil
import sys

import kuzu

from .config import DATA, OUT
from .redact import locality

GRAPH_DIR = DATA / "graph"

SCHEMA = [
    "CREATE NODE TABLE FIR(id STRING, fir_no STRING, year STRING, date DATE, time STRING, "
    "occurred DATE, place STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE Person(id STRING, sex STRING, age INT64, PRIMARY KEY(id))",
    "CREATE NODE TABLE Vehicle(id STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE Officer(id STRING, rank STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE Station(id STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE Section(id STRING, act STRING, section STRING, offence STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE Locality(id STRING, PRIMARY KEY(id))",
    "CREATE REL TABLE COMPLAINANT_IN(FROM Person TO FIR)",
    "CREATE REL TABLE ACCUSED_IN(FROM Person TO FIR)",
    "CREATE REL TABLE MENTIONED_IN(FROM Person TO FIR)",
    "CREATE REL TABLE VEHICLE_IN(FROM Vehicle TO FIR)",
    "CREATE REL TABLE INVESTIGATED_BY(FROM FIR TO Officer)",
    "CREATE REL TABLE REGISTERED_BY(FROM FIR TO Officer)",
    "CREATE REL TABLE REGISTERED_AT(FROM FIR TO Station)",
    "CREATE REL TABLE CHARGED_UNDER(FROM FIR TO Section)",
    "CREATE REL TABLE OCCURRED_IN(FROM FIR TO Locality)",
    "CREATE REL TABLE LIVES_IN(FROM Person TO Locality)",
]

# plain-English description handed to the LLM in ask.py
SCHEMA_TEXT = """Nodes:
  FIR(id e.g. 'FIR 0033/2026', fir_no, year, date DATE (registered), time, occurred DATE, place)
  Person(id e.g. 'P_0003', sex 'M'/'F', age)      -- pseudonyms only
  Vehicle(id e.g. 'V_002')
  Officer(id e.g. 'O_001', rank)
  Station(id, Marathi name e.g. 'अलंकार')
  Section(id e.g. 'BNS 303(2)', act, section, offence e.g. 'theft', 'cheating', 'rash driving on a public way')
  Locality(id, Marathi area name e.g. 'कोथरुड', 'कर्वेनगर', 'एरंडवणे')
Relationships:
  (Person)-[:COMPLAINANT_IN]->(FIR)   (Person)-[:ACCUSED_IN]->(FIR)   (Person)-[:MENTIONED_IN]->(FIR)
  (Vehicle)-[:VEHICLE_IN]->(FIR)
  (FIR)-[:INVESTIGATED_BY]->(Officer) (FIR)-[:REGISTERED_BY]->(Officer)
  (FIR)-[:REGISTERED_AT]->(Station)   (FIR)-[:CHARGED_UNDER]->(Section)
  (FIR)-[:OCCURRED_IN]->(Locality)    (Person)-[:LIVES_IN]->(Locality)"""


def iso(d):
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", d or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def build(include_rules=False):
    shutil.rmtree(GRAPH_DIR, ignore_errors=True)
    GRAPH_DIR.parent.mkdir(parents=True, exist_ok=True)
    conn = kuzu.Connection(kuzu.Database(str(GRAPH_DIR)))
    for q in SCHEMA:
        conn.execute(q)

    def node(label, id_, **props):
        props = {k: v for k, v in props.items() if v is not None}
        sets = ", ".join(f"n.{k} = ${k}" for k in props)
        conn.execute(f"MERGE (n:{label} {{id: $id}})" + (f" SET {sets}" if sets else ""), {"id": id_, **props})

    def rel(a_lbl, a, r, b_lbl, b):
        conn.execute(f"MATCH (a:{a_lbl} {{id:$a}}), (b:{b_lbl} {{id:$b}}) MERGE (a)-[:{r}]->(b)", {"a": a, "b": b})

    def date(v):
        return {"d": v} if v else None

    allowed = {"LLM_CHECKED"} | ({"RULES_PASSED"} if include_rules else set())
    loaded, skipped = 0, 0
    for f in sorted(OUT.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("status") not in allowed:
            skipped += 1
            continue
        fid = f"FIR {d['fir_no']}/{d['year']}"
        conn.execute("MERGE (n:FIR {id:$id}) SET n.fir_no=$no, n.year=$y, n.time=$t, n.place=$p",
                     {"id": fid, "no": d["fir_no"], "y": d["year"], "t": d.get("fir_time") or "",
                      "p": d["place"].get("address") or ""})
        for prop, val in (("date", iso(d.get("fir_date"))), ("occurred", iso(d.get("occurred_from")))):
            if val:
                conn.execute(f"MATCH (n:FIR {{id:$id}}) SET n.{prop} = date($v)", {"id": fid, "v": val})

        node("Station", d["police_station"])
        rel("FIR", fid, "REGISTERED_AT", "Station", d["police_station"])

        loc = locality(d["place"].get("address", ""))
        if loc != "[ADDRESS]":
            node("Locality", loc)
            rel("FIR", fid, "OCCURRED_IN", "Locality", loc)

        def person(p, role):
            if not p or not p.get("id"):
                return
            node("Person", p["id"], sex=p.get("sex"), age=p.get("age"))
            rel("Person", p["id"], role, "FIR", fid)
            if p.get("locality") and p["locality"] != "[ADDRESS]":
                node("Locality", p["locality"])
                rel("Person", p["id"], "LIVES_IN", "Locality", p["locality"])

        person(d["complainant"], "COMPLAINANT_IN")
        for a in d["accused"]:
            person(a, "ACCUSED_IN")
        named = {d["complainant"].get("id")} | {a.get("id") for a in d["accused"]}
        for pid in d.get("other_persons", []):
            if pid not in named:
                node("Person", pid)
                rel("Person", pid, "MENTIONED_IN", "FIR", fid)
        for vid in d.get("vehicles", []):
            node("Vehicle", vid)
            rel("Vehicle", vid, "VEHICLE_IN", "FIR", fid)
        for o in d.get("officers", []):
            node("Officer", o["id"], rank=o.get("rank"))
            rel("FIR", fid, "INVESTIGATED_BY" if o["role"] == "investigating_officer" else "REGISTERED_BY",
                "Officer", o["id"])
        for a in d.get("acts", []):
            sid = f"{a['code']} {a['section']}"
            node("Section", sid, act=a["act"], section=a["section"], offence=a.get("offence"))
            rel("FIR", fid, "CHARGED_UNDER", "Section", sid)
        loaded += 1

    counts = {}
    for label in ("FIR", "Person", "Vehicle", "Officer", "Section", "Locality"):
        r = conn.execute(f"MATCH (n:{label}) RETURN count(n)")
        counts[label] = r.get_next()[0]
    return loaded, skipped, counts


def main():
    include = "--include-rules" in sys.argv
    if include:
        print("WARNING: including RULES_PASSED FIRs (not yet LLM-checked). For testing only.\n")
    loaded, skipped, counts = build(include)
    print(f"Graph built in {GRAPH_DIR}")
    print(f"FIRs loaded: {loaded}   not loaded (not checked yet): {skipped}")
    print("Nodes:", counts)


if __name__ == "__main__":
    main()
