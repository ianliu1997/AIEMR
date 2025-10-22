import asyncio, pathlib, time
from typing import Iterable
from neo4j import Driver
from app.config import settings
from app.graph.ingest import ensure_schema, load_json, file_sha256, ingest_records
from app.services.qdrant_indexer import upsert_patients

# Read last seen hashes from Neo4j
GET_META = """
OPTIONAL MATCH (m:IngestionMeta {patientID:$pid})
RETURN m.last_hash AS last_hash
"""

def _iter_json_files(root: pathlib.Path) -> Iterable[pathlib.Path]:
    return sorted(p for p in root.glob("*.json") if p.is_file())

def _patient_id_from_records(records: list[dict]) -> str | None:
    return records[0].get("patient_id") if records else None

async def sync_once(driver: Driver):
    ensure_schema(driver)
    for f in _iter_json_files(settings.EMR_DIR):
        records = load_json(f)
        pid = _patient_id_from_records(records)
        if not pid:
            continue
        mtime = int(f.stat().st_mtime)
        sha = file_sha256(f)
        with driver.session() as s:
            last_hash = s.run(GET_META, pid=pid).single().get("last_hash")
        if sha != last_hash:
            ingest_records(driver, records, meta={"fname": f.name, "mtime": mtime, "hash": sha})
            # upsert this patient into Qdrant
            try:
                upsert_patients(driver, [pid])
            except Exception as e:
                print(f"[sync] Qdrant upsert error for patient {pid}: {e}")

async def periodic_sync(driver: Driver):
    while True:
        try:
            await sync_once(driver)
        except Exception as e:
            # Avoid PHI in logs; keep messages generic
            print(f"[sync] error: {e}")
        await asyncio.sleep(settings.SYNC_INTERVAL_SEC)
