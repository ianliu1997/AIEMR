from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from ..dependencies import neo4j_driver
from ..services.rag import (
    build_patient_graph_html,
    graph_patient_summaries,
    run_rag_query,
    run_sync,
)
from AIEMR_system.chatbot_rag.app.services.visualize import fetch_patient_graph


class RagQueryBody(BaseModel):
    question: str
    mode: str = Field(default="hybrid", pattern="^(hybrid|graph)$")
    patient_ids: Optional[List[str]] = Field(default=None, alias="patientIds")

router = APIRouter(prefix="/v1/rag", tags=["rag"])


@router.post("/ingest/sync", status_code=202)
async def trigger_sync(driver=Depends(neo4j_driver)):
    try:
        result = await run_sync(driver)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Ingest failed: {exc}") from exc
    return JSONResponse(result, status_code=202)


@router.get("/patients")
async def get_patients(driver=Depends(neo4j_driver)):
    try:
        summaries = graph_patient_summaries(driver)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Neo4j unavailable: {exc}") from exc
    return {"patients": summaries}


@router.get("/patients/{patient_id}/graph")
async def get_patient_graph(patient_id: str, driver=Depends(neo4j_driver)):
    try:
        graph = fetch_patient_graph(driver, patient_id)
        if graph.number_of_nodes() == 0:
            raise HTTPException(status_code=404, detail="Graph not found")
        nodes = [{"id": nid, "attrs": data} for nid, data in graph.nodes(data=True)]
        edges = [{"source": u, "target": v, "attrs": data} for u, v, data in graph.edges(data=True)]
        return {"patientId": patient_id, "nodes": nodes, "edges": edges}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Neo4j unavailable: {exc}") from exc


@router.get("/patients/{patient_id}/graph-html")
async def get_patient_graph_html(patient_id: str, driver=Depends(neo4j_driver)):
    try:
        path = build_patient_graph_html(driver, patient_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Neo4j unavailable: {exc}") from exc
    return FileResponse(path, media_type="text/html")


@router.post("/query")
async def rag_query(
    body: RagQueryBody,
    driver=Depends(neo4j_driver),
):
    try:
        return run_rag_query(
            driver,
            question=body.question,
            mode=body.mode,
            patient_ids=body.patient_ids,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"RAG query failed: {exc}") from exc


@router.post("/query-with-document")
async def rag_query_with_document(
    question: str = Form(...),
    mode: str = Form("hybrid"),
    patientIds: Optional[str] = Form(None),
    document: UploadFile = File(...),
    driver=Depends(neo4j_driver),
):
    if mode not in ("hybrid", "graph"):
        raise HTTPException(status_code=400, detail="mode must be 'hybrid' or 'graph'")
    patient_list: Optional[List[str]] = None
    if patientIds:
        patient_list = [pid.strip() for pid in patientIds.split(",") if pid.strip()]
    body = (await document.read()).decode("utf-8")
    try:
        return run_rag_query(
            driver,
            question=question,
            mode=mode,
            patient_ids=patient_list,
            extra_doc=body,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"RAG query failed: {exc}") from exc
