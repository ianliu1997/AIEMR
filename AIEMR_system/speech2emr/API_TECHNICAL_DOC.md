# Medical Speech-to-Text API — Technical (API) Document

Date: 2025-09-23

## Overview
This service ingests WAV audio uploads or live recordings, transcribes speech to text with Whisper, and generates EMR JSON documents via an EM## System Architecture

### Adapter-to-Schema Mapping

**Configuration:** `emr/emr_tasks.py` (CRITICAL FILE)

```python
TASKS = {
    "model_outputs_seg_MedicalHistory": EMRTaskConfig(
        schema_name="medical_his",
        schema=MedicalHistory,              # Pydantic validation schema
        title="Medical History",
        system_template="...",               # LLM system prompt
        user_template="...",                 # LLM user prompt
        example_files=["example_medical_history.txt", "example_medical_history.jsonl"]
    ),
    "model_outputs_seg_MenstrualHistory": EMRTaskConfig(
        schema_name="menstrual_his",
        schema=MenstrualHistory,             # Different schema
        title="Menstrual History",
        system_template="...",               # Different prompts
        user_template="...",
        example_files=["example_menstrual_history.txt", "example_menstrual_history.jsonl"]
    ),
}
```

**How Schema Selection Works:**

1. User uploads audio with adapter parameter (e.g., `model_outputs_seg_MenstrualHistory`)
2. System stores `adapter_key` in `patient_record` table
3. Background task transcribes using that adapter's LoRA weights
4. EMR conversion reads `adapter_key` from database
5. Calls `get_task_for_adapter(adapter_key)` to retrieve configuration
6. LLM generates JSON using:
   - Correct Pydantic schema for validation
   - Domain-specific system prompts
   - Appropriate few-shot examples
7. Output matches the medical conversation type automatically

**Benefits:**
- ✅ No manual schema selection needed
- ✅ Prevents schema mismatches
- ✅ Easy to add new adapter types
- ✅ Consistent prompt engineering per domain

### GPU Memory Management

**Challenge:** Google Colab T4 Constraints
- Total GPU memory: 22.2 GB
- Whisper (with adapter): ~8 GB during inference
- EMR LLM (quantized): ~14 GB
- Cannot load both simultaneously (would exceed 22 GB)

**Solution: Sequential Loading with Complete Cleanup**

```python
# Stage 1: Transcription
whisper_model = load_whisper_with_adapter(adapter)
transcript = whisper_model.transcribe(audio_path)
whisper_model.save_transcript(transcript)

# Stage 2: CRITICAL - Complete GPU Cleanup
whisper_model.unload()
del whisper_model
gc.collect()
torch.cuda.empty_cache()
torch.cuda.synchronize()
# GPU now has ~22.1 GB free

# Stage 3: EMR Generation (safe now)
emr_model = load_emr_llm()  # Uses ~14 GB
json_output = emr_model.generate_json(transcript, task_config)
```

**Memory Monitoring:**
- Endpoints: `/gpu-status`, `/gpu-cleanup`
- Logs: GPU memory before/after each stage
- Alerts: Warnings if memory usage stays high after cleanup

**Performance Impact:**
- Sequential: ~1-2 minutes total (30-60s transcribe + 15-30s EMR)
- Parallel (if possible): Would save ~10-20s but requires 22+ GB GPU

### Processing Pipeline

```
┌──────────────────┐
│   Upload Audio   │  - POST /upload/
│                  │  - Audio → uploads/record_{id}.wav
└────────┬─────────┘  - Create patient_record row
         │            - Store adapter_key in DB
         ▼            - Return record_id immediately
┌──────────────────┐
│ Background Task  │  - FastAPI BackgroundTasks
│     Starts       │  - Non-blocking
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Transcription   │  - Load Whisper + LoRA adapter
│    (GPU Stage)   │  - transcribe(audio_path)
└────────┬─────────┘  - Save transcripts/transcript_{id}.txt
         │            - Update Transcript_file_ID
         │            - Status: transcribed
         ▼
┌──────────────────┐
│  GPU Cleanup     │  - whisper_model.unload()
│                  │  - torch.cuda.empty_cache()
└────────┬─────────┘  - Free ~8 GB GPU memory
         │            - Verify cleanup via logging
         ▼
┌──────────────────┐
│  EMR Conversion  │  - Read adapter_key from DB
│    (GPU Stage)   │  - get_task_for_adapter(adapter_key)
└────────┬─────────┘  - Load EMR LLM (~14 GB)
         │            - Generate JSON with Guidance library
         │            - Validate against Pydantic schema
         │            - Save emr/emr_{id}.json
         │            - Save timestamped backup copy
         │            - Update JSON_file_ID
         │            - Status: emr_generated
         ▼
┌──────────────────┐
│    Complete      │  - All files ready
│                  │  - Status in database
└──────────────────┘  - Ready for retrieval
```

**Timing Breakdown (5-minute audio on Colab T4):**
1. Upload: <1 second
2. Whisper transcription: 30-60 seconds
3. GPU cleanup: 2-3 seconds
4. EMR conversion: 15-30 seconds
5. **Total: ~1-2 minutes**

### File Naming Convention

**Design Goal:** Make database IDs match actual filenames

| Database Field | File Path | Example |
|----------------|-----------|---------|
| `id` | `uploads/record_{id}.wav` | `uploads/record_123.wav` |
| `Transcript_file_ID` | `transcripts/{value}.txt` | `transcripts/transcript_123.txt` |
| `JSON_file_ID` | `emr/{value}.json` | `emr/emr_123.json` |

**Benefits:**
- Easy manual file lookup: Given `record_id=123`, transcript is at `transcripts/transcript_123.txt`
- Simple programmatic access: `f"emr/emr_{record.JSON_file_ID}.json"`
- No additional mapping tables needed
- Clear for debugging and manual inspection

---peline. It stores structured records in SQLite using SQLModel.

Base URL: `http://<host>:<port>/`

Key IDs and Tracking:
- Patient: `patient.id` (internal), `patient.patient_id` (external ID)
- Recording: `recording.id` (internal), timestamps: `audio_datetime` (UTC), `user_local_datetime` + `user_timezone` (optional, user-provided)
- Audio: `audio.id` (internal), `audio.audio_id` (external ID)
- Transcription: `transcription.id` (internal), `transcription.transcript_id` (external ID)
- EMR Document: `emrdocument.id` (internal), `emrdocument.file_id` (primary handle), `emrdocument.json_file_id` (external ID)

Time Semantics:
- `recording.audio_datetime` is stored in UTC and used for queries/sorting.
- Clients may submit `user_local_datetime` and `user_timezone`; these are recorded for display/audit.

---

## Authentication
- None (developer/demo). If exposing publicly, add auth (e.g., API keys or OAuth).

---

## Endpoints

### GET `/`
Health check.
- 200 OK: `{ "message": "ASR Patient API is running" }`

### GET `/models`
List available ASR adapters.
- 200 OK: `string[]` — adapter keys.

### POST `/upload/` (202 Accepted)
Upload a WAV and queue transcription+EMR.
- Content-Type: `multipart/form-data`
- Form fields:
  - `patient_id` (string, required): Either a numeric internal ID or a patient name (new patient will be created if not found).
  - `file` (file, required): WAV file only.
  - `adapter` (string, optional): ASR adapter key. Defaults to server setting.
  - `user_local_datetime` (string, optional): Client local datetime. ISO 8601. Examples: `2025-09-23T10:15:20` or `2025-09-23T10:15:20-04:00`.
  - `user_timezone` (string, optional): IANA TZ (e.g., `America/New_York`) or numeric offset (`+08:00`, `-0530`). Used if `user_local_datetime` is naive.
- Responses:
  - 202 Accepted: `{ "status": "queued", "audio_id": <recording.id> }`
  - 415 Unsupported Media Type if file not `.wav`
  - 413 Payload Too Large (if enabled)
- Notes:
  - `audio_datetime` will be stored in UTC regardless; user-local fields are preserved if supplied.

### POST `/record/start/`
Start a local demo live recording (host mic) — laptop-only, not for production.
- Form fields: `patient_id` (string, required), `adapter` (string, optional)
- 200 OK: `{ "message": "Recording started for patient <patient_id>", "audio_id": <uuid> }`

### POST `/record/stop/`
Stop live recording and queue transcription.
- Form fields: `audio_id` (string, required)
- 200 OK: `{ "status": "stopped", "audio_id": <uuid>, "path": "uploads/<uuid>.wav" }`

### GET `/transcription/{audio_id}`
Fetch text transcription when ready.
- Path: `audio_id` (int) — this is the `recording.id`
- 200 OK: Returns `text/plain` file content
- 202 Accepted: Transcript not ready
- 404 Not Found: Unknown `audio_id`

### GET `/gpu-status`
Return GPU availability and memory info.
- 200 OK: `{ gpu_available: boolean, memory?: { free, used, total, ... } }`

### POST `/gpu-cleanup`
Force GPU memory cleanup (debugging).
- 200 OK: `{ cleanup_success: boolean, memory_after_cleanup: {...}, potential_leak: boolean }`

### EMR Router (prefix `/emr`)

#### GET `/emr/{file_id}`
Download an EMR JSON by `file_id`.
- 200 OK: `application/json` file
- 404 Not Found

#### GET `/emr/meta/{file_id}`
Get metadata for an EMR JSON.
- 200 OK:
  - `file_id` (string)
  - `patient_id` (string)
  - `recording_id` (int|null)
  - `transcription_id` (int|null)
  - `storage_path` (string)
  - `schema_name` (string)
  - `schema_version` (string)
  - `created_at` (ISO datetime in UTC)
  - `status` (string)
  - `size_bytes` (int|null)
  - `checksum_sha256` (string|null)
- 404 Not Found

#### GET `/emr/by-transcription/{transcription_id}`
Find EMR JSON `file_id` by transcription id.
- 200 OK: `{ file_id: string }`
- 404 Not Found

#### GET `/emr/search?patient_id=<id>`
List EMR documents for a given `patient_id`.
- 200 OK: `[{ file_id, transcription_id, created_at }]`

---

## Data Model

### Current Architecture (Single-Table Design)

**PatientRecord** — Primary table for tracking:

```python
{
  id: int,                        # Primary key (auto-increment)
  PatientID: str,                 # External EMR patient identifier
  Date: str,                      # Recording date in user timezone (YYYY-MM-DD)
  Time: str,                      # Recording time in user timezone (HH:MM:SS)
  Transcript_file_ID: str?,       # e.g., "transcript_123" (matches filename)
  JSON_file_ID: str?,             # e.g., "emr_123" (matches EMR filename)
  user_timezone: str?,            # User's timezone for reference
  adapter_key: str?,              # CRITICAL: Stores which adapter was used
  internal_recording_id: int?,    # Optional link to legacy Recording table
  status: str,                    # "uploaded" | "transcribed" | "emr_generated"
  created_at: timestamp           # System UTC timestamp
}
```

**Design Benefits:**
- ✅ No JOINs needed — All information in one row
- ✅ Simple queries — `SELECT * FROM patient_record WHERE PatientID = ?`
- ✅ File ID matching — `Transcript_file_ID` matches actual filename
- ✅ Adapter tracking — System knows which EMR schema to apply
- ✅ Fast deployment — Single table creation, minimal migrations

**File Organization:**
```
uploads/record_{id}.wav                     # Original audio
transcripts/transcript_{id}.txt             # Transcription text
emr/emr_{id}.json                          # EMR JSON (primary)
jsonfiles/emr_<timestamp>_patient_<pid>_transcription_<id>.json  # Backup copy
```

### Legacy Architecture (Defined but Not Used)

These tables still exist for compatibility but the main flow uses `PatientRecord`:

- **Patient**: `{ id, patient_id, name, created_at }`
- **Recording**: `{ id, patient_id, audio_datetime (UTC), user_local_datetime?, user_timezone?, transcript_path?, adapter_key?, status }`
- **Audio**: `{ id, audio_id, filepath, language?, duration?, file_size?, recording_id, created_at }`
- **Transcription**: `{ id, transcript_id, audio_id, text, confidence_score?, processing_time?, created_at }`
- **EMRDocument**: `{ id, file_id, json_file_id, patient_id, recording_id?, transcription_id?, storage_path, schema_name, schema_version, created_at, status, size_bytes?, checksum_sha256? }`

**Note:** These were part of the original multi-table architecture. New deployments only need `PatientRecord`.

---

## Example Requests (Windows PowerShell)

### Medical History Upload
```powershell
# Basic medical history upload
curl.exe -X POST http://localhost:8000/upload/ `
  -F "patient_id=P001" `
  -F "file=@C:\path\to\medical_audio.wav;type=audio/wav" `
  -F "adapter=model_outputs_seg_MedicalHistory"

# Response: { "status": "queued", "record_id": 123 }
```

### Menstrual History Upload
```powershell
# Menstrual history with automatic schema selection
curl.exe -X POST http://localhost:8000/upload/ `
  -F "patient_id=P002" `
  -F "file=@C:\path\to\menstrual_audio.wav;type=audio/wav" `
  -F "adapter=model_outputs_seg_MenstrualHistory"

# System automatically:
# 1. Uses MenstrualHistory LoRA adapter for transcription
# 2. Stores adapter_key in database
# 3. Selects MenstrualHistory schema during EMR conversion
# 4. Generates JSON with menstrual-specific fields
```

### Upload with Timezone
```powershell
# Timezone-aware datetime (no separate timezone needed)
curl.exe -X POST http://localhost:8000/upload/ `
  -F "patient_id=P003" `
  -F "file=@C:\path\to\audio.wav;type=audio/wav" `
  -F "adapter=model_outputs_seg_MedicalHistory" `
  -F "user_local_datetime=2025-10-02T10:15:20-04:00"

# Naive local time + offset
$form = @{
  patient_id = 'P004'
  file = Get-Item 'C:\path\to\audio.wav'
  adapter = 'model_outputs_seg_MedicalHistory'
  user_local_datetime = '2025-10-02T10:15:20'
  user_timezone = '+08:00'
}
Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/upload/' -Form $form
```

### Query Database (Python)
```python
from sqlmodel import Session, select
from app.database import engine
from app.simple_models import PatientRecord

# Get all records for a patient
with Session(engine) as session:
    records = session.exec(
        select(PatientRecord).where(PatientRecord.PatientID == "P001")
    ).all()
    
    for record in records:
        print(f"Record {record.id}:")
        print(f"  Date/Time: {record.Date} {record.Time}")
        print(f"  Adapter: {record.adapter_key}")
        print(f"  Status: {record.status}")
        print(f"  Transcript: transcripts/{record.Transcript_file_ID}.txt")
        print(f"  EMR JSON: emr/{record.JSON_file_ID}.json")
```

---

## Operational Notes
- Whisper model is unloaded before EMR generation to free GPU memory; memory cleanup is logged and validated.
- `audio_datetime` is the canonical timestamp for sorting and analytics; user-local fields are for display/audit.
- SQLite migrations are applied via `migrate_patient_db.py` and are safe for older DBs (rebuilds legacy `recording` table when needed).

## Versioning & Compatibility
- Backward compatible: Clients that don’t send `user_local_datetime`/`user_timezone` continue to work; server stores UTC time.
- Consider adding versioned routes if response shapes change.
