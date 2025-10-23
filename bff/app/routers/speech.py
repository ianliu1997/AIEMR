from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlmodel import Session

from AIEMR_system.speech2emr.app.model_registry import get_registry
from AIEMR_system.speech2emr.app.settings import settings as speech_settings
from AIEMR_system.speech2emr.app.simple_crud import (
    get_record_by_id,
    create_patient_record,
)
from AIEMR_system.speech2emr.app.simple_models import PatientRecord
from AIEMR_system.speech2emr.app.main import run_transcription_simple

from ..dependencies import speech_session
from ..services.speech import list_jobs, patient_summaries, serialize_record

router = APIRouter(prefix="/v1/speech", tags=["speech"])


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _adapter_label(key: str) -> str:
    if key == "base":
        return "General (Base model)"
    return key.replace("_", " ").title()


@router.get("/adapters")
async def list_adapters():
    registry = get_registry()
    adapters = []
    for key, path in registry.list_adapters().items():
        adapters.append(
            {
                "key": key,
                "label": _adapter_label(key),
                "path": path,
                "description": None if key == "base" else "LoRA fine-tuned adapter",
            }
        )
    return {"adapters": adapters}


@router.get("/jobs")
async def get_jobs(
    patientId: Optional[str] = None,
    session: Session = Depends(speech_session),
):
    return {"jobs": list_jobs(session, patient_id=patientId)}


@router.post("/jobs", status_code=202)
async def create_job(
    background: BackgroundTasks,
    patientId: str = Form(..., min_length=1),
    adapterKey: Optional[str] = Form(default=None),
    topics: Optional[List[str]] = Form(default=None),
    userLocalDateTime: Optional[str] = Form(default=None),
    userTimezone: Optional[str] = Form(default=None),
    audio: UploadFile = File(...),
    session: Session = Depends(speech_session),
):
    if not audio.filename or not audio.filename.lower().endswith(".wav"):
        raise HTTPException(status_code=415, detail="Only WAV audio is supported")

    dest = speech_settings.UPLOAD_DIR / f"{uuid.uuid4().hex}.wav"
    with dest.open("wb") as buffer:
        shutil.copyfileobj(audio.file, buffer)

    parsed_local = _parse_datetime(userLocalDateTime)
    record: PatientRecord = create_patient_record(
        session,
        patient_id=patientId,
        user_local_datetime=parsed_local,
        user_timezone=userTimezone,
        adapter_key=adapterKey,
    )

    if record.id is None:
        raise HTTPException(status_code=500, detail="Failed to persist job")

    background.add_task(
        run_transcription_simple,
        record.id,
        dest,
        adapterKey or speech_settings.DEFAULT_ADAPTER,
    )

    job = serialize_record(record)
    job["topics"] = topics or None
    return JSONResponse(job, status_code=202, headers={"retry-after": "3"})


def _record_from_id(session: Session, job_id: str) -> PatientRecord | None:
    try:
        return get_record_by_id(session, int(job_id))
    except ValueError:
        return None


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, session: Session = Depends(speech_session)):
    record = _record_from_id(session, job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")
    return serialize_record(record)


@router.get("/jobs/{job_id}/transcript")
async def get_transcript(job_id: str, session: Session = Depends(speech_session)):
    record = _record_from_id(session, job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")
    if not record.Transcript_file_ID:
        return JSONResponse({"status": record.status}, status_code=202)
    path = speech_settings.TRANSCRIPT_DIR / f"{record.Transcript_file_ID}.txt"
    if not path.exists():
        return JSONResponse({"status": record.status}, status_code=202)
    return PlainTextResponse(path.read_text(encoding="utf-8"))


@router.get("/jobs/{job_id}/emr")
async def get_emr(job_id: str, session: Session = Depends(speech_session)):
    record = _record_from_id(session, job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")
    if not record.JSON_file_ID:
        return JSONResponse({"status": record.status}, status_code=202)
    path = Path(speech_settings.EMR_DIR) / f"{record.JSON_file_ID}.json"
    if not path.exists():
        return JSONResponse({"status": record.status}, status_code=202)
    import json

    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    return JSONResponse(content=payload)


@router.get("/patients")
async def get_patients(session: Session = Depends(speech_session)):
    return {"patients": patient_summaries(session)}
