from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from neo4j import Driver

from AIEMR_system.chatbot_rag.app.config import settings as rag_settings
from AIEMR_system.chatbot_rag.app.services.syncer import sync_once
from AIEMR_system.chatbot_rag.app.services.visualize import fetch_patient_graph, to_pyvis_html
from AIEMR_system.chatbot_rag.app.services.retriever import hybrid_answer, graph_answer


SUMMARY_CYPHER = """
MATCH (p:Patient)
OPTIONAL MATCH (p)-[rel]->(n)
WITH p, COUNT(DISTINCT rel) AS edgeCount, COUNT(DISTINCT n) AS nodeCount
OPTIONAL MATCH (p)-[:HAS_INGESTION_META]->(m:IngestionMeta)
RETURN p.patientID AS patientId,
       edgeCount,
       nodeCount,
       m.last_ingested AS lastIngestedAt
ORDER BY p.patientId
"""


def _to_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    # Neo4j DateTime objects expose to_native()
    to_native = getattr(value, "to_native", None)
    if callable(to_native):
        return to_native().isoformat()
    return str(value)


async def run_sync(driver: Driver) -> Dict[str, Any]:
    await sync_once(driver)
    return {"status": "completed", "startedAt": datetime.utcnow().isoformat() + "Z"}


def graph_patient_summaries(driver: Driver) -> List[Dict[str, Any]]:
    with driver.session() as session:
        rows = session.run(SUMMARY_CYPHER)
        summaries: List[Dict[str, Any]] = []
        for row in rows:
            node_count = row["nodeCount"]
            edge_count = row["edgeCount"]
            summaries.append(
                {
                    "patientId": row["patientId"],
                    "hasGraph": (node_count or 0) > 0,
                    "graphHtmlUrl": f"/v1/rag/patients/{row['patientId']}/graph-html",
                    "lastIngestedAt": _to_iso(row.get("lastIngestedAt")),
                    "nodeCount": node_count,
                    "edgeCount": edge_count,
                }
            )
    return summaries


def build_patient_graph_html(driver: Driver, patient_id: str) -> Path:
    graph = fetch_patient_graph(driver, patient_id)
    if graph.number_of_nodes() == 0:
        raise ValueError(f"No graph found for {patient_id}")
    out = rag_settings.GRAPH_HTML_DIR / f"{patient_id}_graph.html"
    to_pyvis_html(graph, str(out))
    return out


def run_rag_query(driver: Driver, *, question: str, mode: str, patient_ids: Optional[List[str]] = None, extra_doc: Optional[str] = None) -> Dict[str, Any]:
    if mode == "graph":
        result = graph_answer(driver, question)
    else:
        result = hybrid_answer(driver, question, patient_ids=patient_ids, extra_doc=extra_doc)
    context = result.get("context_json") or result.get("intermediate_steps")
    if isinstance(context, (list, dict)):
        from json import dumps

        context = dumps(context, indent=2, ensure_ascii=False)
    return {
        "question": question,
        "mode": mode,
        "answer": result.get("answer"),
        "contextJson": context,
        "evidenceNodeIds": result.get("value_node_ids"),
    }
