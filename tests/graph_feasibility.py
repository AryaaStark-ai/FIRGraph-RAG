"""Feasibility test: can redacted FIR output answer multi-hop questions as a graph?

Uses Kuzu (an embedded graph database that speaks Cypher, `pip install kuzu`)
so it runs without Docker. The real system will use Neo4j; the Cypher is the same.

Input:
  - one REAL FIR, run through OCR -> parse -> minor check -> redaction (pseudonyms only)
  - one SYNTHETIC test record, invented here, that reuses the real FIR's accused and
    vehicle IDs to simulate a repeat offender / repeat vehicle. It is NOT a real FIR.

Run from the project root:  python -m tests.graph_feasibility data/ocr/0033_Publish_FIR.txt
"""
import shutil
import sys
import tempfile
from pathlib import Path

import kuzu

from pipeline.fields import parse_all
from pipeline.minors import minor_reason
from pipeline.redact import Vault, redact_fir
from pipeline.sections import split_sections


def build_records(ocr_txt: Path, workdir: Path):
    fields = parse_all(split_sections(ocr_txt.read_text(encoding="utf-8")))
    assert minor_reason(fields) is None, "test FIR involves a minor; pick another"
    real = redact_fir(fields, Vault(path=workdir / "vault.json"))   # throwaway vault
    assert real["leaks"] == [], f"leak check failed: {real['leaks']}"
    real["source"] = "real FIR (redacted)"
    real["sections"] = ["MVA 119", "MVA 177", "BNS 281", "BNS 324(4)"]

    synthetic = {
        "fir_no": "TEST-001", "year": real["year"], "police_station": real["police_station"],
        "fir_date": "05/03/2026", "source": "SYNTHETIC test record",
        "complainant": {"id": "P_9001", "locality": "कर्वेनगर"},
        "accused": [{"id": real["accused"][0]["id"], "locality": real["accused"][0]["locality"]}],
        "vehicles": real["vehicles"][-1:],
        "officers": real["officers"][:1],
        "sections": ["BNS 281"],
    }
    return real, synthetic


SCHEMA = [
    "CREATE NODE TABLE Person(id STRING, locality STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE FIR(id STRING, date STRING, source STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE Vehicle(id STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE Officer(id STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE Station(id STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE Section(id STRING, PRIMARY KEY(id))",
    "CREATE REL TABLE COMPLAINANT_IN(FROM Person TO FIR)",
    "CREATE REL TABLE ACCUSED_IN(FROM Person TO FIR)",
    "CREATE REL TABLE VEHICLE_IN(FROM Vehicle TO FIR)",
    "CREATE REL TABLE INVESTIGATED_BY(FROM FIR TO Officer)",
    "CREATE REL TABLE REGISTERED_AT(FROM FIR TO Station)",
    "CREATE REL TABLE CHARGED_UNDER(FROM FIR TO Section)",
]

QUESTIONS = [
    ("Accused who appear in more than one FIR",
     "MATCH (p:Person)-[:ACCUSED_IN]->(f:FIR) WITH p, collect(f.id) AS firs "
     "WHERE size(firs) > 1 RETURN p.id, firs"),
    ("Vehicles linked to more than one FIR",
     "MATCH (v:Vehicle)-[:VEHICLE_IN]->(f:FIR) WITH v, collect(f.id) AS firs "
     "WHERE size(firs) > 1 RETURN v.id, firs"),
    ("How is complainant P_9001 connected to the real FIR's complainant?",
     "MATCH (c:Person)-[:COMPLAINANT_IN]->(:FIR {source:'real FIR (redacted)'}) "
     "MATCH p = (c)-[* SHORTEST 1..6]-(b:Person {id:'P_9001'}) RETURN properties(nodes(p),'id')"),
    ("FIRs per section",
     "MATCH (f:FIR)-[:CHARGED_UNDER]->(s:Section) RETURN s.id, count(f) ORDER BY count(f) DESC"),
]


def main(ocr_txt):
    workdir = Path(tempfile.mkdtemp())
    try:
        real, synthetic = build_records(Path(ocr_txt), workdir)
        conn = kuzu.Connection(kuzu.Database(str(workdir / "db")))
        for q in SCHEMA:
            conn.execute(q)

        def merge(label, id_, **props):
            sets = ", ".join(f"n.{k} = ${k}" for k in props)
            conn.execute(f"MERGE (n:{label} {{id: $id}})" + (f" SET {sets}" if props else ""), {"id": id_, **props})

        def rel(a_lbl, a, r, b_lbl, b):
            conn.execute(f"MATCH (a:{a_lbl} {{id:$a}}), (b:{b_lbl} {{id:$b}}) MERGE (a)-[:{r}]->(b)", {"a": a, "b": b})

        for rec in (real, synthetic):
            fid = f"FIR {rec['fir_no']}/{rec['year']}"
            merge("FIR", fid, date=rec["fir_date"], source=rec["source"])
            merge("Station", rec["police_station"])
            rel("FIR", fid, "REGISTERED_AT", "Station", rec["police_station"])
            c = rec["complainant"]
            merge("Person", c["id"], locality=c["locality"])
            rel("Person", c["id"], "COMPLAINANT_IN", "FIR", fid)
            for a in rec["accused"]:
                merge("Person", a["id"], locality=a["locality"])
                rel("Person", a["id"], "ACCUSED_IN", "FIR", fid)
            for vid in rec["vehicles"]:
                merge("Vehicle", vid)
                rel("Vehicle", vid, "VEHICLE_IN", "FIR", fid)
            for o in rec["officers"]:
                merge("Officer", o["id"])
                rel("FIR", fid, "INVESTIGATED_BY", "Officer", o["id"])
            for s in rec["sections"]:
                merge("Section", s)
                rel("FIR", fid, "CHARGED_UNDER", "Section", s)

        for title, q in QUESTIONS:
            print(f"\n### {title}\n{q}")
            r = conn.execute(q)
            rows = 0
            while r.has_next():
                print("  ->", r.get_next())
                rows += 1
            if not rows:
                print("  -> (no rows)")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)   # throwaway vault + db deleted


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/ocr/0033_Publish_FIR.txt")
