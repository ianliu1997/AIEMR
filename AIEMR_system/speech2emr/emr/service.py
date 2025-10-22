# app/emr/service.py
import os, json, hashlib, logging
from pathlib import Path
from sqlmodel import Session, select
from datetime import datetime
from app.settings import settings
from app.models import EMRDocument  
from emr.engine import EMREngine

# import emr-task settings
from typing import Optional
from emr.emr_tasks import get_task_for_adapter
from emr.EMRconversion import convert_transcript_to_emr

log = logging.getLogger(__name__)

# Get the project root directory (where this file is located relative to)
PROJECT_ROOT = Path(__file__).parent.parent.absolute()

# Your DB access functions are placeholders—adapt to your app's data layer.
def generate_emr_for_transcription(db, transcription_id: int) -> int:
    """
    1) Get transcription and its recording (for adapter key / overrides)
    2) Pick EMR task config
    3) Convert transcript → EMR JSON
    4) Persist JSON and link to transcription
    Returns: emr_file_id (or similar handle)
    """
    tx = db.get_transcription(transcription_id)            # must have .text and .audio_id
    rec = db.get_recording_by_audio_id(tx.audio_id)        # must have .adapter_key and optional .emr_task_override
    adapter_key = rec.emr_task_override or rec.adapter_key or "model_outputs_seg_MedicalHistory"

    task_cfg = get_task_for_adapter(adapter_key)

    # Optional: task-specific few-shots
    ex_raw = ex_json = None
    if task_cfg.schema_name == "menstrual_his":
        ex_raw  = db.read_text_asset("example_menstrual_history.txt")  # implement or remove
        ex_json = db.read_json_asset("example_menstrual_history.json")
    elif task_cfg.schema_name == "medical_his":
        ex_raw  = db.read_text_asset("example_medical_history.txt")
        ex_json = db.read_json_asset("example_medical_history.json")

    emr_payload = convert_transcript_to_emr(
        transcript_text=tx.text,
        task_cfg=task_cfg,
        example_raw=ex_raw, example_json=ex_json
    )

    file_id, _ = db.save_emr_json(
        payload=emr_payload,
        schema_name=task_cfg.title,
        schema_version="1.0",
        transcription_id=tx.id
    )
    return file_id

def _save_json_to_folder(emr_dict: dict, transcription_id: int, patient_id: str):
    """Save the generated EMR JSON to the jsonfiles folder with meaningful filename"""
    try:
        # Create jsonfiles directory if it doesn't exist
        jsonfiles_dir = PROJECT_ROOT / "jsonfiles"
        os.makedirs(jsonfiles_dir, exist_ok=True)
        
        # Generate filename with timestamp and IDs for uniqueness
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"emr_{timestamp}_patient_{patient_id}_transcription_{transcription_id}.json"
        
        # Save the JSON file
        json_file_path = jsonfiles_dir / filename
        with open(json_file_path, 'w', encoding='utf-8') as f:
            json.dump(emr_dict, f, indent=2, ensure_ascii=False)
        
        log.info(f"EMR JSON saved to jsonfiles folder: {filename}")
        return str(json_file_path)
        
    except Exception as e:
        log.warning(f"Failed to save EMR JSON to jsonfiles folder: {e}")
        return None

_engine = None
def get_engine(force_gpu: bool = False, prefer_full_gpu: bool = False):
    global _engine
    if _engine is None:
        _engine = EMREngine(
            allow_cpu_fallback=not force_gpu,
            prefer_full_gpu=prefer_full_gpu,
            use_quantization=not prefer_full_gpu  # Disable quantization if we want full GPU
        )
    return _engine

def build_and_store_emr(
    session: Session,
    *,
    transcription_id: int,
    recording_id: int,
    patient_id: str,
    transcript_path: str,
    adapter_key: str | None = None,  # Adapter used for transcription, determines EMR task
    example_text_path: str | None = None,
    example_json_path: str | None = None,
    force_gpu: bool = False,
    use_full_gpu: bool = False,  # New parameter for full GPU usage
) -> EMRDocument:
    # Get the appropriate EMR task configuration based on adapter_key
    task_cfg = get_task_for_adapter(adapter_key or "model_outputs_seg_MedicalHistory")
    log.info(f"Using EMR task configuration: {task_cfg.schema_name} for adapter: {adapter_key}")
    
    # Select example files based on the task configuration
    if example_text_path is None:
        if task_cfg.schema_name == "menstrual_his":
            example_text_path = str(PROJECT_ROOT / "examples" / "example_menstrual_history.txt")
        else:  # medical_his or default
            example_text_path = str(PROJECT_ROOT / "examples" / "example_medical_history.txt")
    
    if example_json_path is None:
        if task_cfg.schema_name == "menstrual_his":
            example_json_path = str(PROJECT_ROOT / "examples" / "example_menstrual_history.jsonl")
        else:  # medical_his or default
            example_json_path = str(PROJECT_ROOT / "examples" / "example_medical_history.jsonl")
    
    # 1) read transcript text from disk
    text = Path(transcript_path).read_text(encoding="utf-8")
    example_text = Path(example_text_path).read_text(encoding="utf-8")
    example_json = json.loads(Path(example_json_path).read_text(encoding="utf-8"))

    # 2) run conversion using the task-specific configuration
    emr_dict = convert_transcript_to_emr(
        transcript_text=text,
        task_cfg=task_cfg,
        example_raw=example_text,
        example_json=example_json
    )

    # 2.5) Save the generated JSON to jsonfiles folder
    _save_json_to_folder(emr_dict, transcription_id, patient_id)

    # 3) pre-register row to get file_id
    doc = EMRDocument(
        patient_id=patient_id,
        recording_id=recording_id,
        transcription_id=transcription_id,
        storage_path="",
        status="processing",
        created_at=datetime.utcnow(),
    )
    session.add(doc); session.commit(); session.refresh(doc)

    # 4) write file
    os.makedirs(settings.EMR_DIR, exist_ok=True)
    out_path = Path(settings.EMR_DIR) / f"{doc.file_id}.json"
    out_path.write_text(json.dumps(emr_dict, indent=2), encoding="utf-8")

    raw = out_path.read_bytes()
    doc.storage_path = str(out_path)
    doc.status = "ready"
    doc.size_bytes = len(raw)
    doc.checksum_sha256 = hashlib.sha256(raw).hexdigest()
    session.add(doc); session.commit(); session.refresh(doc)
    return doc
