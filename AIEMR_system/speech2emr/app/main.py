import os
# Set PyTorch CUDA memory management before importing torch-related libraries
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True,max_split_size_mb:512'

from pathlib import Path
import shutil
import uuid
import logging
from fastapi import (
    FastAPI, UploadFile, File, Form, BackgroundTasks, APIRouter,
    Depends, HTTPException, Request
)
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.settings import settings
from app.database import engine, get_session
from app import models, crud
from app.simple_models import PatientRecord
from app import simple_crud
from app.asr import ASRService
from app.model_registry import get_registry

from app.models import EMRDocument
from app.gpu_monitor import GPUMemoryMonitor
from emr.service import build_and_store_emr


# Setting
os.makedirs(settings.EMR_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
log = logging.getLogger("uvicorn")

app = FastAPI(title="Medical Speech-to-Text API")
# Don't initialize ASR service at startup - do it lazily to avoid blocking
asr_service = None

def get_asr_service():
    """Lazy initialization of ASR service"""
    global asr_service
    if asr_service is None:
        asr_service = ASRService()
    return asr_service

# ---------------------------------------------------------------------------
@app.on_event("startup")
def _init_db() -> None:
    models.SQLModel.metadata.create_all(engine)
    PatientRecord.metadata.create_all(engine)  # Create the simplified table
    log.info("DB initialised using %s", settings.DB_URL)

@app.get("/")
def root():
    return {"message": "ASR Patient API is running"}

@app.get("/models")
def list_models():
    return get_registry().list_adapters()

# ---------------------------------------------------------------------------
@app.post("/upload/", status_code=202)
async def upload_audio(
    background: BackgroundTasks,
    request: Request,
    patient_id: str = Form(..., min_length=1),
    file: UploadFile = File(...),
    adapter: str | None = Form(None),
    user_local_datetime: str | None = Form(None, description="Client local datetime in ISO 8601, e.g. 2025-09-23T10:15:20"),
    user_timezone: str | None = Form(None, description="Client timezone, IANA like 'America/New_York' or numeric offset like +08:00"),
    session: Session = Depends(get_session),
):
    # ---------- validation ----------
    if file.filename and not file.filename.lower().endswith(".wav"):
        raise HTTPException(415, "Only WAV files are accepted")
    #if file.size and file.size > 50_000_000:  # 50 MB
    #    raise HTTPException(413, "File too large (>50 MB)")

    # ---------- store safely ----------
    safe_name = f"{uuid.uuid4()}.wav"
    dest: Path = settings.UPLOAD_DIR / safe_name
    with dest.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    log.info("Saved upload as %s", dest)

    # Create patient/recording rows as today, but store adapter_key:
    # Try to get patient by ID if patient_id is numeric, otherwise create by name
    try:
        patient = crud.get_patient_by_id(session, int(patient_id))
        if not patient:
            # ID not found, create with the ID as name
            patient = crud.create_patient(session, name=str(patient_id))
    except ValueError:
        # patient_id is not numeric, treat as patient name
        patient = crud.get_or_create_patient(session, patient_id)
    
    # Parse optional user-local time inputs
    from datetime import datetime, timezone
    audio_dt_utc = None
    user_local_dt_obj = None
    if user_local_datetime:
        try:
            # Try parsing ISO 8601. If timezone-aware, convert to UTC directly.
            # If naive, we'll use user_timezone (offset or IANA) if provided; otherwise keep as local-only copy and set server time for UTC.
            parsed = datetime.fromisoformat(user_local_datetime)
            if parsed.tzinfo is not None:
                audio_dt_utc = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                user_local_dt_obj = parsed.replace(tzinfo=None)
            else:
                user_local_dt_obj = parsed
        except Exception:
            # Ignore parse errors; fall back to server time
            user_local_dt_obj = None

    # If parsed local time was naive but we have an offset like +08:00/-05:00 in user_timezone, apply it
    if audio_dt_utc is None and user_local_dt_obj is not None and user_timezone:
        try:
            # Handle numeric offset like +08:00 or -0530
            tz = None
            tz_str = user_timezone.strip()
            if (tz_str.startswith('+') or tz_str.startswith('-')):
                # Normalize formats: "+08:00" or "+0800"
                sign = 1 if tz_str[0] == '+' else -1
                digits = tz_str[1:].replace(':', '')
                if len(digits) == 2:
                    hours = int(digits)
                    minutes = 0
                elif len(digits) == 4:
                    hours = int(digits[:2])
                    minutes = int(digits[2:])
                else:
                    hours = 0; minutes = 0
                from datetime import timedelta
                tz = timezone(sign * timedelta(hours=hours, minutes=minutes))
                audio_dt_utc = (user_local_dt_obj.replace(tzinfo=tz)).astimezone(timezone.utc).replace(tzinfo=None)
            else:
                # IANA TZ: try zoneinfo (Python 3.9+)
                try:
                    from zoneinfo import ZoneInfo
                    tz = ZoneInfo(tz_str)
                    audio_dt_utc = (user_local_dt_obj.replace(tzinfo=tz)).astimezone(timezone.utc).replace(tzinfo=None)
                except Exception:
                    pass
        except Exception:
            pass

    # Auto-detect client local time from headers if not provided
    if audio_dt_utc is None and user_local_dt_obj is None:
        # Common header candidates set by browsers/clients or proxies
        hdr = request.headers
        # Prefer explicit client-local timestamp if provided
        client_local = hdr.get("x-client-localtime") or hdr.get("x-local-time")
        tz_header = (
            hdr.get("time-zone")
            or hdr.get("timezone")
            or hdr.get("x-client-timezone")
            or hdr.get("x-timezone")
        )
        offset_header = hdr.get("x-client-offset")  # e.g., "+08:00" or "-0530" or minutes like "-480"

        from datetime import timezone, timedelta
        try:
            if client_local:
                # Try parse client-sent local ISO string (may include tz)
                parsed = datetime.fromisoformat(client_local)
                if parsed.tzinfo is not None:
                    user_local_dt_obj = parsed.replace(tzinfo=None)
                    audio_dt_utc = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                else:
                    user_local_dt_obj = parsed
            elif tz_header:
                # IANA TZ supplied via header
                try:
                    from zoneinfo import ZoneInfo
                    tz = ZoneInfo(tz_header)
                    now_local = datetime.now(tz)
                    user_local_dt_obj = now_local.replace(tzinfo=None)
                    audio_dt_utc = now_local.astimezone(timezone.utc).replace(tzinfo=None)
                    user_timezone = tz_header
                except Exception:
                    pass
            elif offset_header:
                # Numeric offset supplied
                off = offset_header.strip()
                # If minutes integer, convert to hours:minutes
                if off.lstrip("-+").isdigit():
                    mins = int(off)
                    sign = 1
                    if mins < 0:
                        sign = -1
                        mins = -mins
                    hours, minutes = divmod(mins, 60)
                    tz = timezone(sign * timedelta(hours=hours, minutes=minutes))
                else:
                    # Formats like +08:00 or -0530
                    sign = 1 if off.startswith("+") else -1
                    digits = off[1:].replace(":", "")
                    if len(digits) == 2:
                        hours = int(digits)
                        minutes = 0
                    else:
                        hours = int(digits[:2])
                        minutes = int(digits[2:]) if len(digits) >= 4 else 0
                    tz = timezone(sign * timedelta(hours=hours, minutes=minutes))
                now_local = datetime.now(tz)
                user_local_dt_obj = now_local.replace(tzinfo=None)
                audio_dt_utc = now_local.astimezone(timezone.utc).replace(tzinfo=None)
                user_timezone = offset_header
        except Exception:
            # If any parsing fails, leave as None so we fall back to server UTC later in create_patient_record
            user_local_dt_obj = None

    # Create simplified patient record using user's timezone
    patient_record = simple_crud.create_patient_record(
        session,
        patient_id=str(patient_id),
        user_local_datetime=user_local_dt_obj,
        user_timezone=user_timezone,
        adapter_key=adapter  # CRITICAL: Store adapter for EMR conversion
    )

    # Kick off background transcription and pass adapter:
    if settings.USE_CELERY:
        from workers.transcribe import run_transcription_task
        run_transcription_task.delay(str(dest), str(settings.TRANSCRIPT_DIR / f"{patient_record.id}.txt"), adapter or settings.DEFAULT_ADAPTER)  # type: ignore
    else:
        if patient_record.id is not None:
            background.add_task(run_transcription_simple, patient_record.id, dest, adapter or settings.DEFAULT_ADAPTER)

    # ---------------------------------------------------------------------------
def run_transcription_simple(record_id: int, wav_path: Path, adapter: str | None) -> None:
    """
    Simple transcription workflow using the single-table design
    """
    log.info("Transcription started for record %s (adapter-%s)", record_id, adapter)
    
    # Log initial GPU memory status
    GPUMemoryMonitor.log_gpu_memory_status("Before transcription")
    
    service = get_asr_service()  # Lazy load here
    text = service.transcribe(wav_path, adapter_key=adapter)
    
    # Generate transcript file ID that matches the filename
    transcript_file_id = f"transcript_{record_id}"
    out_path: Path = settings.TRANSCRIPT_DIR / f"{transcript_file_id}.txt"
    out_path.write_text(text, encoding="utf-8")
    
    # Update the patient record with transcript file ID
    with Session(engine) as session:
        simple_crud.update_transcript_file_id(session, record_id, transcript_file_id)
        
        # Get the record to access patient info for EMR
        record = simple_crud.get_record_by_id(session, record_id)
        if record:
            # Trigger EMR conversion after successful transcription
            log.info("Starting EMR conversion for record %s", record_id)
            
            # COMPLETELY unload Whisper model to free full GPU for EMR
            log.info("Unloading Whisper model to free full GPU for EMR processing")
            service.unload_whisper_models()
            
            # Additional aggressive memory clearing for EMR processing
            import gc
            import torch
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
                log.info(f"GPU memory after clearing: {torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_reserved(0)} bytes free")
            
            try:
                # Generate JSON file ID that matches the filename
                json_file_id = f"emr_{record_id}"
                json_path = Path(settings.EMR_DIR) / f"{json_file_id}.json"
                
                # Create EMR document (simplified)
                # Use the adapter that was stored during upload to select the correct EMR prompt
                emr_doc = build_and_store_emr(
                    session,
                    transcription_id=record_id,
                    recording_id=record_id,
                    patient_id=record.PatientID,
                    transcript_path=str(out_path),
                    adapter_key=record.adapter_key,
                    use_full_gpu=True
                )
                
                # Update the patient record with JSON file ID
                simple_crud.update_json_file_id(session, record_id, json_file_id)
                
                log.info("EMR conversion completed for record %s, JSON file: %s", record_id, json_file_id)
                
                # Log GPU memory after EMR conversion
                GPUMemoryMonitor.log_gpu_memory_status("After EMR conversion")
                
            except Exception as e:
                log.error("EMR conversion failed for record %s: %s", record_id, str(e))
        else:
            log.warning("Could not find patient record %s", record_id)
    
    # Final cleanup and memory check
    log.info("Performing final GPU memory cleanup after all tasks completed")
    GPUMemoryMonitor.cleanup_gpu_memory(aggressive=True)
    GPUMemoryMonitor.log_gpu_memory_status("Final cleanup - All tasks completed")
    
    # Check for potential memory leaks
    GPUMemoryMonitor.check_memory_leak(expected_free_gb=35.0)
    
    log.info("Transcription finished for record %s", record_id)

def run_transcription_old(rec_id: int, wav_path: Path, adapter: str | None) -> None:
    """
    Legacy transcription function - kept for compatibility
    """
    pass


# ---------------------------------------------------------------------------
# Endpoint to start and stop live recording-only for local laptop demo purposes

"""
Those endpoints relied on sounddevice opening the host’s microphone and a busy-waiting thread:

Works on your laptop → fails in Docker/Kubernetes/GCP Cloud Run (no ALSA).

Blocks the Uvicorn worker while queue.get() waits.
---------------------------------------------------------------------------
Scaling horizontally becomes impossible (each replica would record its own silence).

Alternative: let the client stream audio
Use WebRTC / WebSocket to push Opus chunks to the API.

Buffer them on disk (or directly to the model’s streamer).

You can still expose /record/start and /record/stop, but they become control messages, not “open the server microphone”.
"""

@app.post("/record/start/")
def start_record(patient_id: str = Form(...),
                 adapter: str | None = Form(None),
                 session: Session = Depends(get_session),
                 ):
    try:
        service = get_asr_service()  # Lazy load
        audio_id = service.start_live_recording(patient_id)
        # Note: adapter tracking would need to be added to ASRService if needed
        return {
            "message": f"Recording started for patient {patient_id}",
            "audio_id": audio_id
        }
    except Exception as e:
        log.error(f"Error starting recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/record/stop/")
def stop_record(background: BackgroundTasks,
                audio_id: str = Form(...),
                session: Session = Depends(get_session),
                ):
    try:
        service = get_asr_service()  # Lazy load
        result = service.stop_live_recording(audio_id)
        adapter = settings.DEFAULT_ADAPTER  # Use default since we simplified tracking

        # Create DB rows and queue transcription like/upload:
        # Try to get patient by ID if patient_id is numeric, otherwise create by name
        try:
            patient = crud.get_patient_by_id(session, int(result["patient_id"]))
            if not patient:
                patient = crud.create_patient(session, name=str(result["patient_id"]))
        except (ValueError, KeyError):
            # patient_id is not numeric or missing, create with default name
            patient = crud.create_patient(session, name="Unknown Patient")
        
        rec = crud.add_recording(session, patient, Path(result["path"]).name, adapter)

        if settings.USE_CELERY:
            from workers.transcribe import run_transcription_task
            run_transcription_task.delay(result["path"], str(settings.TRANSCRIPT_DIR / f"{rec.id}.txt"), adapter)  # type: ignore
        else:
            if rec.id is not None:
                background.add_task(run_transcription, rec.id, Path(result["path"]), adapter)

        return {
            "message": "Recording saved",
            **result
        }
    except Exception as e:
        log.error(f"Error stopping recording: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    

# ---------------------------------------------------------------------------
def run_transcription(rec_id: int, wav_path: Path, adapter: str | None) -> None:
    """
    Blocking call – executed via FastAPI BackgroundTask.
    Swap this for a Celery task if you need multiple GPU nodes.
    """
    log.info("Transcription started for %s (adapter-%s)", rec_id, adapter)
    
    # Log initial GPU memory status
    GPUMemoryMonitor.log_gpu_memory_status("Before transcription")
    
    service = get_asr_service()  # Lazy load here
    text = service.transcribe(wav_path, adapter_key=adapter)
    
    # Log GPU memory after transcription
    GPUMemoryMonitor.log_gpu_memory_status("After transcription, before EMR")
    out_path: Path = settings.TRANSCRIPT_DIR / f"{rec_id}.txt"
    out_path.write_text(text, encoding="utf-8")
    
    # update DB with transcript path
    with Session(engine) as session:
        crud.set_transcript_path(session, rec_id, str(out_path))
        
        # Get the recording to access patient info
        recording = session.get(models.Recording, rec_id)
        if recording and recording.patient:
            patient_id = str(recording.patient.id)
            
            # Trigger EMR conversion after successful transcription
            log.info("Starting EMR conversion for transcription %s", rec_id)
            
            # COMPLETELY unload Whisper model to free full GPU for EMR
            log.info("Unloading Whisper model to free full GPU for EMR processing")
            service.unload_whisper_models()
            
            # Additional aggressive memory clearing for EMR processing
            import gc
            import torch
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()  # Wait for all operations to complete
                log.info(f"GPU memory after clearing: {torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_reserved(0)} bytes free")
            
            try:
                emr_doc = build_and_store_emr(
                    session,
                    transcription_id=rec_id,
                    recording_id=rec_id, 
                    patient_id=patient_id,
                    transcript_path=str(out_path),
                    use_full_gpu=True  # Use full GPU capacity for EMR
                )
                log.info("EMR conversion completed for transcription %s, file_id: %s", rec_id, emr_doc.file_id)
                
                # Log GPU memory after EMR conversion
                GPUMemoryMonitor.log_gpu_memory_status("After EMR conversion")
                
            except Exception as e:
                log.error("EMR conversion failed for transcription %s: %s", rec_id, str(e))
        else:
            log.warning("Could not find recording or patient for transcription %s", rec_id)
    
    # Final cleanup and memory check
    log.info("Performing final GPU memory cleanup after all tasks completed")
    GPUMemoryMonitor.cleanup_gpu_memory(aggressive=True)
    GPUMemoryMonitor.log_gpu_memory_status("Final cleanup - All tasks completed")
    
    # Check for potential memory leaks
    GPUMemoryMonitor.check_memory_leak(expected_free_gb=35.0)
    
    log.info("Transcription finished for %s", rec_id)

# ---------------------------------------------------------------------------
@app.get("/transcription/{audio_id}")
def fetch_transcription(
    audio_id: int,
    session: Session = Depends(get_session),
):
    rec = session.get(models.Recording, audio_id)
    if not rec:
        raise HTTPException(404, "Unknown audio_id")
    if not rec.transcript_path:
        raise HTTPException(202, "Transcript not ready")
    return FileResponse(
        rec.transcript_path,
        media_type="text/plain",
        filename=f"{audio_id}.txt",
    )


# ---------------------------------------------------------------------------
# GPU Memory Test Endpoint
@app.get("/gpu-status")
def get_gpu_status():
    """Get current GPU memory status for monitoring"""
    memory_info = GPUMemoryMonitor.get_gpu_memory_info()
    if memory_info:
        return {
            "gpu_available": True,
            "memory": memory_info
        }
    else:
        return {
            "gpu_available": False,
            "message": "No CUDA GPU available"
        }

@app.post("/gpu-cleanup")
def force_gpu_cleanup():
    """Force GPU memory cleanup (for testing)"""
    success = GPUMemoryMonitor.force_memory_reset()
    memory_info = GPUMemoryMonitor.get_gpu_memory_info()
    
    return {
        "cleanup_success": success,
        "memory_after_cleanup": memory_info,
        "potential_leak": GPUMemoryMonitor.check_memory_leak(35.0) if memory_info else False
    }

# ---------------------------------------------------------------------------
emr_router = APIRouter(prefix="/emr", tags=["emr"])

@emr_router.get("/{file_id}")
def get_emr_json(file_id: str, session: Session = Depends(get_session)):
    doc = session.exec(select(EMRDocument).where(EMRDocument.file_id == file_id)).first()
    if not doc:
        raise HTTPException(status_code=404, detail="EMR JSON not found")
    return FileResponse(doc.storage_path, media_type="application/json")

@emr_router.get("/meta/{file_id}")
def get_emr_meta(file_id: str, session: Session = Depends(get_session)):
    doc = session.exec(select(EMRDocument).where(EMRDocument.file_id == file_id)).first()
    if not doc:
        raise HTTPException(status_code=404, detail="EMR JSON not found")
    return {
        "file_id": doc.file_id,
        "patient_id": doc.patient_id,
        "recording_id": doc.recording_id,
        "transcription_id": doc.transcription_id,
        "storage_path": doc.storage_path,
        "schema_name": doc.schema_name,
        "schema_version": doc.schema_version,
        "created_at": doc.created_at,
        "status": doc.status,
        "size_bytes": doc.size_bytes,
        "checksum_sha256": doc.checksum_sha256,
    }

@emr_router.get("/by-transcription/{transcription_id}")
def get_emr_by_transcription(transcription_id: int, session: Session = Depends(get_session)):
    doc = session.exec(select(EMRDocument).where(EMRDocument.transcription_id == transcription_id)).first()
    if not doc:
        raise HTTPException(status_code=404, detail="No EMR JSON for this transcription")
    return {"file_id": doc.file_id}

@emr_router.get("/search")
def search_emr(patient_id: str, session: Session = Depends(get_session)):
    docs = session.exec(select(EMRDocument).where(EMRDocument.patient_id == patient_id)).all()
    return [{"file_id": d.file_id, "transcription_id": d.transcription_id, "created_at": d.created_at} for d in docs]



# after you create FastAPI app instance
app.include_router(emr_router)