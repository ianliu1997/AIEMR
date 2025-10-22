# app/services/qdrant_indexer.py
from typing import List, Dict, Any, Optional
from hashlib import sha256
import uuid, json

from neo4j import Driver
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from openai import OpenAI

from app.config import settings

_openai = OpenAI(api_key=settings.OPENAI_API_KEY)
_qc = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)

def _phash(pid: str) -> str:
    return sha256((settings.PATIENT_SALT + str(pid)).encode()).hexdigest()

def _as_uuid(s: str) -> str:
    """Convert string to UUID format. Handle None/empty strings safely."""
    if not s:  # Handle None or empty string
        return str(uuid.uuid4())  # Generate random UUID
    try: 
        return str(uuid.UUID(s))
    except: 
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(s)))

def _embed(texts: list[str]) -> list[list[float]]:
    resp = _openai.embeddings.create(model=settings.EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]

def ensure_collection():
    _qc.recreate_collection(
        collection_name=settings.QDRANT_COLLECTION,
        vectors_config=VectorParams(size=settings.EMBED_DIM, distance=Distance.COSINE),
    )
    # index on patient_id_hash for fast filtering
    try:
        _qc.create_payload_index(settings.QDRANT_COLLECTION, field_name="patient_id_hash", field_schema="keyword")
    except Exception:
        pass

# Canonical text to embed (tunable)
def _canonical_text(section: str, field: str, r: Dict[str, Any]) -> str:
    if section == "MedicalHistory" and field == "PastDisease":
        return (f"Past disease ({r.get('category')}; type: {r.get('disease_type')}), "
                f"since {r.get('since_year')}, on medication: {r.get('on_medication')}.")
    unit = f" {r.get('unit')}" if r.get('unit') else ""
    return f"Patient {field}: {r.get('value')}{unit}."

# Pull rows from Neo4j for given patients (or all if None)
CYPHER_ROWS = """
MATCH (p:Patient)
WHERE $pids IS NULL OR p.patientID IN $pids
MATCH (p)-[]->(sec:SectionTable {patientID:p.patientID})
MATCH (sec)-[:HAS_INFORMATION_OF]->(s:Schema {patientID:p.patientID})
MATCH (s)-[:HAS_VALUE]->(v:Value {patientID:p.patientID})
WHERE v.node_id IS NOT NULL AND s.node_id IS NOT NULL
RETURN p.patientID AS patientID, sec.name AS section, s.field AS field,
       v.value AS value, v.valueType AS valueType, v.unit AS unit,
       v.category AS category, v.type AS disease_type,
       v.since_year AS since_year, v.on_medication AS on_medication,
       v.node_id AS v_id, s.node_id AS s_id
"""

def _rows_to_points(rows: List[Dict[str, Any]]) -> List[PointStruct]:
    texts, payloads, ids = [], [], []
    for r in rows:
        txt = _canonical_text(r["section"], r["field"], r)
        pid_hash = _phash(r["patientID"])
        payload = {
            "neo4j_id": r["v_id"],
            "schema_id": r["s_id"],
            "patient_id_hash": pid_hash,
            "patient_id": r["patientID"],            # optional; avoid returning to clients
            "section": r["section"],
            "field": r["field"],
            "value_type": r["valueType"],
            "unit": r.get("unit"),
            "category": r.get("category"),
            "disease_type": r.get("disease_type"),
            "since_year": r.get("since_year"),
            "on_medication": r.get("on_medication"),
            "embedding_model": settings.EMBED_MODEL,
            "embedding_version": 1,
        }
        qid = _as_uuid(r["v_id"])
        ids.append(qid); texts.append(txt); payloads.append(payload)
    vecs = _embed(texts)
    return [PointStruct(id=i, vector=v, payload=p) for i, v, p in zip(ids, vecs, payloads)]

def rebuild_all(driver: Driver) -> dict:
    ensure_collection()
    with driver.session() as s:
        rows = [dict(r) for r in s.run(CYPHER_ROWS, pids=None)]
    pts = _rows_to_points(rows)
    _qc.upsert(settings.QDRANT_COLLECTION, pts)
    return {"collection": settings.QDRANT_COLLECTION, "upserted": len(pts)}

def upsert_patients(driver: Driver, pids: List[str]) -> dict:
    with driver.session() as s:
        rows = [dict(r) for r in s.run(CYPHER_ROWS, pids=pids)]
    if not rows:
        return {"collection": settings.QDRANT_COLLECTION, "upserted": 0}
    pts = _rows_to_points(rows)
    _qc.upsert(settings.QDRANT_COLLECTION, pts)
    return {"collection": settings.QDRANT_COLLECTION, "upserted": len(pts)}

# ANN search helper for retriever
def ann_ids(query_text: str, patient_ids: Optional[List[str]] = None, top_k: int = 12) -> List[str]:
    qvec = _embed([query_text])[0]
    qfilter = None
    if patient_ids:
        should = [FieldCondition(key="patient_id_hash", match=MatchValue(value=_phash(pid))) for pid in patient_ids]
        qfilter = Filter(should=should)
    hits = _qc.search(settings.QDRANT_COLLECTION, query_vector=qvec, limit=top_k, query_filter=qfilter)
    return [h.payload["neo4j_id"] for h in hits if h.payload and "neo4j_id" in h.payload]
