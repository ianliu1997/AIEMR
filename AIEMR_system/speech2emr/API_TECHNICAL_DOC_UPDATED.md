# EMR AI System — Technical API Documentation

**Last Updated:** 2025-10-02

This document provides comprehensive technical guidance for the EMR AI System, covering:
- Adapter-based medical transcription with LoRA-finetuned Whisper models
- Automatic EMR schema selection based on adapter type
- Single-table database design for simplified deployment
- GPU memory management strategies for Google Colab T4
- System architecture and processing pipeline
- Troubleshooting and operational best practices

---

## System Overview

The EMR AI System converts medical audio recordings to structured EMR JSON through a multi-stage pipeline:

1. **Upload** — Audio saved with adapter specification
2. **Transcription** — LoRA-finetuned Whisper model for domain-specific accuracy
3. **GPU Cleanup** — Sequential model loading to fit Colab T4 memory constraints
4. **EMR Conversion** — Automatic schema selection + LLM-based structured JSON generation

**Key Innovation:** Adapter-based processing automatically selects the appropriate EMR schema, prompts, and examples based on which Whisper adapter was used for transcription. This eliminates manual configuration and ensures the correct medical data structure for each conversation type.

---

## Available Adapters

| Adapter Key | Purpose | EMR Schema | Fields |
|-------------|---------|------------|--------|
| `model_outputs_seg_MedicalHistory` | General medical history conversations | MedicalHistory | Medications, allergies, surgeries, family history, etc. |
| `model_outputs_seg_MenstrualHistory` | Menstrual health conversations | MenstrualHistory | Cycle duration, menarche age, symptoms, contraception, etc. |

Each adapter automatically determines:
- ✅ Pydantic validation schema
- ✅ LLM system prompts
- ✅ Few-shot example files
- ✅ JSON structure

---

## Authentication
- None (developer/demo). If exposing publicly, add auth (e.g., API keys or OAuth).

---

## API Endpoints

### Core Upload Flow

#### POST `/upload/` **[PRIMARY ENDPOINT]**

Upload audio with adapter specification for transcription and EMR generation.

**Request:**
- Method: `POST`
- Content-Type: `multipart/form-data`
- Parameters:
  - `patient_id` (string, required): External EMR patient identifier
  - `file` (file, required): WAV audio file only
  - **`adapter`** (string, **RECOMMENDED**): ASR adapter key
    - `model_outputs_seg_MedicalHistory` (default)
    - `model_outputs_seg_MenstrualHistory`
  - `user_local_datetime` (string, optional): ISO 8601 local datetime
  - `user_timezone` (string, optional): IANA zone or numeric offset

**Response:**
- 202 Accepted: `{ "status": "queued", "record_id": <int> }`
- 415 Unsupported Media Type: non-WAV file
- 413 Payload Too Large: file too large

**Processing Flow:**

```
Upload → Database Record Created
  ↓ (adapter_key stored)
Background Task Started
  ↓
Load Whisper + Adapter → Transcribe
  ↓
Save transcript_<id>.txt → Update DB
  ↓
Unload Whisper + GPU Cleanup
  ↓
Read adapter_key from DB
  ↓
get_task_for_adapter() → Select Schema
  ↓
Load EMR LLM → Generate JSON
  ↓
Save emr_<id>.json → Update DB
  ↓
Status: emr_generated
```

**Critical Notes:**
- ⚠️ **Adapter is stored in database** — Used later for EMR schema selection
- ⚠️ **GPU memory managed sequentially** — Whisper unloaded before EMR to fit T4 constraints
- ⚠️ **Schema selected automatically** — System reads adapter_key and applies correct prompts
- ✅ **Prevents schema mismatch** — Medical history transcript gets medical schema, not menstrual

**Example (PowerShell):**
```powershell
curl.exe -X POST http://localhost:8000/upload/ `
  -F "patient_id=P001" `
  -F "file=@C:\path\to\audio.wav;type=audio/wav" `
  -F "adapter=model_outputs_seg_MenstrualHistory"
```

### Health & Diagnostics

#### GET `/`
Health check.
- 200 OK: `{ "message": "ASR Patient API is running" }`

#### GET `/models`
List available ASR adapters.
- 200 OK: `string[]` — adapter keys.

#### GET `/gpu-status`
Return GPU availability and memory info.
- 200 OK: `{ gpu_available: boolean, memory?: { free, used, total, ... } }`

#### POST `/gpu-cleanup`
Force GPU memory cleanup (debugging).
- 200 OK: `{ cleanup_success: boolean, memory_after_cleanup: {...}, potential_leak: boolean }`

### Transcription Retrieval

#### GET `/transcription/{audio_id}`
Fetch text transcription when ready.
- Path: `audio_id` (int) — this is the `recording.id`
- 200 OK: Returns `text/plain` file content
- 202 Accepted: Transcript not ready
- 404 Not Found: Unknown `audio_id`

### EMR Document Endpoints (prefix `/emr`)

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

## System Architecture

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

---

## Operational Best Practices

### Database Migrations

**Current Migration (REQUIRED):**
- Script: `db_migrate_1001.py` or `quick_fix_colab.py`
- Purpose: Adds `adapter_key` column to `patient_record` table
- When needed:
  - Existing database without `adapter_key` column
  - After upgrading to adapter-based system
- How to run:
  ```powershell
  # Local Windows
  python db_migrate_1001.py
  
  # Google Colab
  python quick_fix_colab.py
  ```
- Safe: Idempotent (can run multiple times)

**Obsolete Migrations (DO NOT USE):**
- ❌ `migrate_db.py` - For legacy Recording table
- ❌ `migrate_patient_db.py` - For 5-table architecture (300+ lines)
- ❌ `migrate_colab_db.py` - Legacy Colab migration
- ❌ `migrate_to_single_table.py` - One-time conversion (already done)
- ❌ `test_patient_db.py` - Tests legacy structure

### GPU Memory Management

**Monitor GPU Status:**
```powershell
# Check current GPU usage
curl http://localhost:8000/gpu-status

# Force cleanup if needed
curl -X POST http://localhost:8000/gpu-cleanup
```

**Expected Memory Usage:**
- Idle: <100 MB
- During transcription: ~8 GB
- After cleanup: <500 MB (small residual)
- During EMR: ~14 GB
- After EMR: <500 MB

**Warning Signs:**
- Memory stays >2 GB after cleanup → Memory leak
- "CUDA out of memory" errors → Model not properly unloaded
- Slow processing (>5 min for 5 min audio) → GPU bottleneck

### Example File Requirements

**CRITICAL:** Each adapter MUST have matching example files:

**Medical History:**
- `examples/example_medical_history.txt` - Sample transcript
- `examples/example_medical_history.jsonl` - Sample JSON output
- Format: JSON must match `MedicalHistory` Pydantic schema exactly

**Menstrual History:**
- `examples/example_menstrual_history.txt` - Sample transcript  
- `examples/example_menstrual_history.jsonl` - Sample JSON output
- Format: JSON must match `MenstrualHistory` Pydantic schema exactly

**Why Required:**
- LLM uses few-shot learning (examples guide output format)
- Missing examples → LLM may hallucinate structure
- Wrong format → Pydantic validation failures
- Mismatched schema → System hangs in validation loops

**Troubleshooting Missing Examples:**
1. Check file existence: `ls examples/`
2. Verify file extension: Must be `.jsonl` (not `.json`)
3. Validate JSON structure: Load and check against schema
4. Test: Upload audio, check if EMR completes in <2 minutes

### Pydantic Schema Guidelines

**DO:**
- ✅ Use flexible validators: `extra = "allow"`
- ✅ Allow None for optional fields: `field: str | None = None`
- ✅ Use reasonable defaults: `field: int = 0`
- ✅ Test with example files: Validate examples load successfully

**DON'T:**
- ❌ Use strict Field constraints: `Field(ge=8, le=19)` causes LLM loops
- ❌ Require too many fields: LLM may struggle to populate all
- ❌ Use complex nested structures: Keep schemas relatively flat
- ❌ Change schemas without updating examples: Causes mismatches

**Example Good Schema:**
```python
class MenstrualHistory(BaseModel):
    age_menarche: int | None = None           # Flexible
    cycle_duration: int | None = None          # No strict bounds
    menstruation_len: int | None = None        # Allows missing data
    
    class Config:
        extra = "allow"                        # Accepts extra fields
```

### Performance Benchmarks (Colab T4)

**Expected Times (5-minute audio):**
- Upload: <1 second
- Transcription: 30-60 seconds
- GPU cleanup: 2-3 seconds
- EMR conversion: 15-30 seconds
- **Total: 1-2 minutes**

**If Slower:**
- >2 minutes transcription → Check GPU availability, model loading time
- >1 minute EMR → Check for Pydantic validation loops (strict Field constraints)
- >5 minutes total → Memory leak or GPU not properly freed

**First Run:**
- May be slower (model downloads from HuggingFace)
- Subsequent runs use cached models (~1-2 min consistently)

---

## Troubleshooting

### "Unknown adapter key" Error

**Symptom:** Logs show "Unknown adapter key: <adapter_name>"

**Cause:** Adapter name doesn't match available adapters

**Solution:**
1. Check adapter folder names: `ls adapters/`
2. Verify exact spelling (case-sensitive)
3. Available adapters:
   - `model_outputs_seg_MedicalHistory`
   - `model_outputs_seg_MenstrualHistory`

### "CUDA out of memory" Error

**Symptom:** System crashes during EMR conversion with OOM error

**Cause:** Whisper not properly unloaded or GPU memory leak

**Solution:**
1. Check GPU status: `curl http://localhost:8000/gpu-status`
2. Force cleanup: `curl -X POST http://localhost:8000/gpu-cleanup`
3. Check logs for "GPU cleanup" confirmation messages
4. Restart server if persistent

### "Table has no column adapter_key" Error

**Symptom:** Database error when accessing `patient_record.adapter_key`

**Cause:** Using database created before adapter_key migration

**Solution:**
```powershell
# Run migration script
python db_migrate_1001.py

# Verify column added
sqlite3 patient.db "PRAGMA table_info(patient_record);"
# Should see adapter_key in column list
```

### EMR Validation Error

**Symptom:** Logs show Pydantic validation failures, raw JSON saved

**Cause:** LLM output doesn't match schema structure

**Solution:**
1. Check example files exist and match schema
2. Verify schema has `extra = "allow"` in Config
3. Remove strict Field constraints (e.g., `ge=`, `le=`)
4. Check raw JSON in `emr/emr_{id}.json` for actual structure
5. Update schema to match common LLM outputs

### System Hangs During EMR Conversion

**Symptom:** MenstrualHistory processing takes >15 minutes

**Cause:** Usually strict Pydantic Field constraints causing validation loops

**Solution:**
1. Check `emr/EMRconversion.py` for Field validators:
   ```python
   # BAD (causes loops):
   age_menarche: int = Field(ge=8, le=19)
   
   # GOOD (flexible):
   age_menarche: int | None = None
   ```
2. Remove `ge=` and `le=` constraints
3. Verify example files exist and are correct format (.jsonl not .json)
4. Restart processing

### Wrong EMR Schema Applied

**Symptom:** MenstrualHistory transcript gets MedicalHistory EMR structure

**Cause:** adapter_key not stored or wrong adapter specified

**Solution:**
1. Check upload included adapter parameter:
   ```powershell
   -F "adapter=model_outputs_seg_MenstrualHistory"
   ```
2. Verify database: 
   ```sql
   SELECT adapter_key FROM patient_record WHERE id = <record_id>;
   ```
3. If NULL, re-upload with correct adapter
4. If correct but wrong schema used, check `emr/emr_tasks.py` for mapping

### Files Not Created

**Symptom:** Database record exists but transcript/EMR files missing

**Cause:** Background task failed or still processing

**Solution:**
1. Check status field:
   ```sql
   SELECT status FROM patient_record WHERE id = <record_id>;
   ```
2. Check server logs for errors
3. Verify folders exist: `uploads/`, `transcripts/`, `emr/`
4. Check file permissions (Colab: usually not an issue)
5. Monitor GPU status for crashes

---

## Versioning & Compatibility

**Current Version:** 2.0 (October 2, 2025)
- Adapter-based EMR conversion
- Single-table database design
- GPU memory optimization

**Previous Version:** 1.0 (September 23, 2025)
- Multi-table architecture
- No adapter-based schema selection
- Manual EMR type configuration

**Backward Compatibility:**
- ✅ Clients not sending `adapter`: System uses default (MedicalHistory)
- ✅ Clients not sending timezone: Server stores UTC
- ✅ Legacy tables: Still defined but not used in main flow
- ✅ Old migration scripts: Won't break system, just unnecessary
- ⚠️ Database migration required: Run `db_migrate_1001.py` for existing DBs

**Breaking Changes:**
- Adapter-key column required in `patient_record` table (migration needed)
- EMR schema selection now automatic (manual override not supported)

---

## Change Log

### Version 2.0 (2025-10-02)

**Major Changes:**
- ✅ Adapter-based EMR conversion with automatic schema selection
- ✅ Single-table database design (`PatientRecord` replaces 5 tables)
- ✅ GPU memory optimization for Google Colab T4 deployment
- ✅ File ID matching convention for easier file lookup
- ✅ Example file requirements documented
- ✅ Pydantic schema best practices

**New Features:**
- Adapter-to-schema mapping via `emr/emr_tasks.py`
- Sequential model loading to prevent OOM errors
- Comprehensive troubleshooting guide
- Performance benchmarks for Colab T4

**Bug Fixes:**
- Fixed: adapter_key not stored during upload
- Fixed: MenstrualHistory hanging due to strict Field constraints
- Fixed: Missing example files causing validation failures

**Documentation:**
- Complete system architecture documentation
- GPU memory management strategies
- Migration script clarification
- Operational best practices

### Version 1.0 (2025-09-23)

**Features:**
- Timezone-aware datetime capture
- Multi-table architecture
- Basic Whisper transcription
- EMR generation via LLM

---

## Contact & Support

For issues or questions:
1. Check troubleshooting section above
2. Review server logs for error messages
3. Verify GPU status and memory usage
4. Check database schema matches documentation
5. Ensure example files exist and match schemas

**Common Quick Fixes:**
- Restart server to clear GPU memory
- Run `db_migrate_1001.py` for database issues
- Check `emr/emr_tasks.py` for adapter configuration
- Verify example files in `examples/` directory
