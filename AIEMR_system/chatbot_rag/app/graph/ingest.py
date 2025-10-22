import json, hashlib, pathlib
from contextlib import contextmanager
from neo4j import Driver
from app.graph.cypher import SCHEMA, SECTION_QUERIES, BACKFILL_UUIDS

def _run_write(sess, cypher, **params):
    def _tx(tx):
        res = tx.run(cypher, **params); s = res.consume(); return s.counters
    return sess.execute_write(_tx)

def ensure_schema(driver: Driver):
    with driver.session() as s:
        for stmt in [c.strip()+";" for c in SCHEMA.strip().split(";") if c.strip()]:
            try: _run_write(s, stmt)
            except Exception as e: print("schema note:", e)
        # Backfill UUIDs for existing data - run each statement separately
        for stmt in [c.strip() for c in BACKFILL_UUIDS.strip().split(";") if c.strip()]:
            try: _run_write(s, stmt)
            except Exception as e: print("uuid backfill note:", e)


def load_json(path: pathlib.Path) -> list[dict]:
    data = json.loads(path.read_text())
    return data if isinstance(data, list) else [data]  # mirrors your loader. :contentReference[oaicite:7]{index=7}

def file_sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

# Keep lightweight ingestion metadata in Neo4j to detect updates.
META_CYPHER = """
MERGE (p:Patient {patientID: $pid})
MERGE (m:IngestionMeta {patientID:$pid})
ON CREATE SET m.first_ingested = datetime()
SET m.last_ingested = datetime(),
    m.last_file = $fname,
    m.last_mtime = $mtime,
    m.last_hash = $hash
MERGE (p)-[:HAS_INGESTION_META]->(m)
"""

def ingest_records(driver: Driver, records: list[dict], meta: dict | None = None):
    with driver.session() as s:
        for rec in records:
            pid = rec.get("patient_id")
            for q in SECTION_QUERIES:
                _run_write(s, q, record=rec)
            if meta:
                _run_write(s, META_CYPHER, pid=pid, **meta)
