# app/routers/rag.py
from typing import Optional, List
from fastapi import APIRouter, Depends, File, UploadFile, Form
from pydantic import BaseModel, Field

from app.deps import get_driver
from app.services.qdrant_indexer import rebuild_all, upsert_patients
from app.services.retriever import hybrid_answer
from app.services.graphrag import graph_answer

router = APIRouter(prefix="/rag", tags=["rag"])

class QueryPayload(BaseModel):
    question: str = Field(..., description="User question")
    mode: str = Field("hybrid", pattern="^(hybrid|graph)$")
    patient_ids: Optional[List[str]] = Field(default=None, description="Restrict to these patient IDs")

@router.post("/index/rebuild")
def rag_index_rebuild(driver = Depends(get_driver)):
    return rebuild_all(driver)

@router.post("/index/upsert")
def rag_index_upsert(payload: List[str], driver = Depends(get_driver)):
    # payload is a list of patient IDs
    return upsert_patients(driver, payload)

@router.post("/query")
async def rag_query(payload: QueryPayload, driver = Depends(get_driver)):
    """
    Query the RAG system (JSON format, no file upload).
    
    - **question**: The question to ask
    - **mode**: Either 'hybrid' (default) or 'graph'
    - **patient_ids**: Optional list of patient IDs to filter
    """
    if payload.mode == "graph":
        return graph_answer(driver, payload.question)
    return hybrid_answer(driver, payload.question, patient_ids=payload.patient_ids, extra_doc=None)

@router.post("/query/upload")
async def rag_query_with_document(
    question: str = Form(..., description="User question"),
    mode: str = Form("hybrid", description="Query mode: 'hybrid' or 'graph'"),
    patient_ids: Optional[str] = Form(None, description="Comma-separated patient IDs (e.g., '00028,00042')"),
    document: UploadFile = File(..., description="Text file to include as extra context"),
    driver = Depends(get_driver)
):
    """
    Query the RAG system with document upload (multipart/form-data).
    
    - **question**: The question to ask
    - **mode**: Either 'hybrid' (default) or 'graph'
    - **patient_ids**: Optional comma-separated patient IDs to filter (e.g., "00028,00042")
    - **document**: Text file to include as extra context
    """
    # Validate mode
    if mode not in ["hybrid", "graph"]:
        from fastapi import HTTPException
        raise HTTPException(400, "mode must be 'hybrid' or 'graph'")
    
    # Parse patient_ids from comma-separated string
    parsed_patient_ids = None
    if patient_ids:
        parsed_patient_ids = [pid.strip() for pid in patient_ids.split(",") if pid.strip()]
    
    # Read document
    extra_doc = (await document.read()).decode("utf-8")
    
    # Route to appropriate handler
    if mode == "graph":
        return graph_answer(driver, question)
    return hybrid_answer(driver, question, patient_ids=parsed_patient_ids, extra_doc=extra_doc)
