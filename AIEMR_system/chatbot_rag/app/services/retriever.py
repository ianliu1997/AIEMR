# app/services/retriever.py
from typing import Any, Dict, List, Optional
from openai import OpenAI
from neo4j import Driver
import json

from app.config import settings
from app.services.qdrant_indexer import ann_ids

_openai = OpenAI(api_key=settings.OPENAI_API_KEY)

CTX_CYPHER = """
MATCH (v:Value) WHERE v.node_id IN $ids
MATCH (s:Schema)-[:HAS_VALUE]->(v)
MATCH (sec:SectionTable)-[:HAS_INFORMATION_OF]->(s)
MATCH (p:Patient)-[]->(sec)
WITH p, sec, s, v
ORDER BY p.patientID
WITH p.patientID AS patientID, sec.name AS section,
     collect(DISTINCT {
       field: s.field,
       value: v.value,
       valueType: v.valueType,
       unit: v.unit,
       node_id: v.node_id,
       category: v.category,
       disease_type: v.type,
       since_year: v.since_year,
       on_medication: v.on_medication
     })[0..24] AS facts
RETURN patientID, section, facts
"""

def _fetch_context(driver: Driver, ids: List[str]) -> List[Dict[str, Any]]:
    if not ids: return []
    with driver.session() as s:
        return [dict(r) for r in s.run(CTX_CYPHER, ids=ids)]

def _format_context(rows: List[Dict[str, Any]]) -> str:
    by_patient = {}
    for r in rows:
        by_patient.setdefault(r["patientID"], {})[r["section"]] = r["facts"]
    return json.dumps(by_patient, ensure_ascii=False, indent=2)

def hybrid_answer(driver: Driver, question: str, patient_ids: Optional[List[str]] = None, extra_doc: Optional[str] = None) -> Dict[str, Any]:
    ids = ann_ids(question, patient_ids=patient_ids, top_k=12)
    ctx_rows = _fetch_context(driver, ids)
    ctx_json = _format_context(ctx_rows)

    system = ("You are a clinical QA assistant. Use ONLY the provided JSON facts (and optional document) to answer. "
              "If insufficient evidence is present, say so explicitly.")
    user = f"Question:\n{question}\n\nEMR JSON (grouped by patient/section):\n{ctx_json}"
    if extra_doc:
        user += f"\n\nAdditional consultation document:\n{extra_doc}"

    # Try with temperature first, fall back without if not supported
    try:
        resp = _openai.chat.completions.create(
            model=settings.CHAT_MODEL,
            messages=[{"role":"system","content":system},
                      {"role":"user","content":user}],
            temperature=0.2,
        )
    except Exception as e:
        # If temperature not supported, use default
        if "temperature" in str(e).lower() or "unsupported" in str(e).lower():
            resp = _openai.chat.completions.create(
                model=settings.CHAT_MODEL,
                messages=[{"role":"system","content":system},
                          {"role":"user","content":user}],
            )
        else:
            raise
    
    return {"answer": resp.choices[0].message.content, "context_json": ctx_json, "value_node_ids": ids}
