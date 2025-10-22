# EMR AI System — API Specification (Updated)

Date: 2025-10-02

This document updates and replaces prior versions of "EMR AI System (API).pdf". It reflects the latest API behavior, including:
- **Adapter-based EMR prompt selection** (automatic schema selection based on transcription adapter)
- **Single-table database design** (simplified PatientRecord architecture)
- **User-local time capture** and canonical UTC storage
- **GPU memory management** for Google Colab deployment AI System — API Specification (Updated)

Date: 2025-09-23

This document updates and replaces prior versions of “EMR AI System (API).pdf”. It reflects the latest API behavior, including user-local time capture and canonical UTC storage.

## 1. Overview
The EMR AI System ingests WAV audio, performs ASR with **LoRA-finetuned Whisper models**, and generates **adapter-specific EMR JSON** via an LLM pipeline. The system automatically selects the appropriate EMR schema and prompts based on which transcription adapter was used (e.g., Medical History vs Menstrual History).

Data is persisted in SQLite using a **simplified single-table design** for easy querying and deployment on Google Colab.

Base URL: `http://<host>:<port>/`

### 1.1 Key Features
- **Adapter-Based Transcription**: Uses LoRA-finetuned Whisper models for specialized medical conversations
- **Automatic EMR Schema Selection**: System reads the adapter used for transcription and automatically applies the matching EMR schema, prompts, and examples
- **Single-Table Design**: All patient data in one `patient_record` table for simplified queries
- **GPU Memory Optimization**: Sequential model loading to support Google Colab T4 (22.2 GB) constraints
- **Timezone-Aware**: Captures user local time while storing canonical UTC timestamps

### 1.2 Available Adapters
- `model_outputs_seg_MedicalHistory` — General medical history conversations
- `model_outputs_seg_MenstrualHistory` — Menstrual health conversations

Each adapter automatically determines:
- Which Pydantic schema to use for EMR validation
- Which system prompts to apply during LLM conversion
- Which example files to provide for few-shot learning

### 1.3 Tracking IDs (Simplified Design)
**Current System (Single Table):**
- `patient_record.id` (primary key, internal)
- `patient_record.PatientID` (external EMR patient ID)
- `patient_record.Transcript_file_ID` (references transcript file)
- `patient_record.JSON_file_ID` (references EMR JSON file)
- `patient_record.adapter_key` (stores which adapter was used)

**Legacy Tables (Still Defined but Not Used in Main Flow):**
- Patient: `patient.id` (internal), `patient.patient_id` (external)
- Recording: `recording.id` (internal)
- Audio: `audio.id` (internal), `audio.audio_id` (external)
- Transcription: `transcription.id` (internal), `transcription.transcript_id` (external)
- EMR Document: `emrdocument.id` (internal), `emrdocument.file_id` (public handle)

### 1.2 Time Semantics
- Canonical timestamp: `recording.audio_datetime` (UTC) — used for sorting/analytics.
- Optional client fields: `recording.user_local_datetime` and `recording.user_timezone` stored for display/audit.
- If client sends a timezone-aware datetime, it is converted to UTC for `audio_datetime`.
- If client sends a naive datetime and a timezone (IANA or numeric offset), timezone is applied before conversion to UTC.
- If nothing is provided, server UTC time is stored in `audio_datetime` and user-local fields are null.

---

## 2. Authentication
No auth in the default build (dev/demo). Add API keys or OAuth if exposed publicly.

---

## 3. Endpoints

### 3.1 Health
GET `/`
- 200: `{ "message": "ASR Patient API is running" }`

### 3.2 List Models
GET `/models`
- 200: `string[]` — adapter keys available for ASR.

### 3.3 Upload Audio **[CRITICAL - Adapter-Based Processing]**
POST `/upload/` — `multipart/form-data`

This is the main entry point for the system. The `adapter` parameter determines:
1. Which LoRA-finetuned Whisper model transcribes the audio
2. Which EMR schema and prompts are automatically applied during conversion

- Form fields:
  - `patient_id` (string, required): EMR patient identifier. Stored in `PatientID` field.
  - `file` (file, required): WAV audio file only.
  - **`adapter`** (string, **RECOMMENDED**): ASR adapter key. Options:
    - `model_outputs_seg_MedicalHistory` (default if not specified)
    - `model_outputs_seg_MenstrualHistory`
  - `user_local_datetime` (string, optional): ISO 8601 local datetime. Examples: `2025-10-02T10:15:20`, `2025-10-02T10:15:20-04:00`.
  - `user_timezone` (string, optional): IANA zone (`America/New_York`) or numeric offset (`+08:00`, `-0530`). Used if local datetime is naive.

- Responses:
  - 202 Accepted: `{ "status": "queued", "record_id": <patient_record.id> }`
  - 415 Unsupported Media Type: non-WAV file
  - 413 Payload Too Large: if file size limit enforced

- **Processing Flow:**
  1. **Upload**: Audio saved to `uploads/` folder, `patient_record` created with `adapter_key` stored
  2. **Transcription**: Background task loads Whisper + specified adapter → generates transcript → saves to `transcripts/transcript_{id}.txt` → updates `Transcript_file_ID`
  3. **GPU Cleanup**: Whisper model completely unloaded from GPU to free memory
  4. **EMR Conversion**: System reads `adapter_key` from database → automatically selects matching schema/prompts/examples → generates EMR JSON → saves to `emr/emr_{id}.json` → updates `JSON_file_ID`
  5. **Status Update**: Record status changes from `uploaded` → `transcribed` → `emr_generated`

- **Adapter-to-Schema Mapping:**
  - `model_outputs_seg_MedicalHistory` → Uses `MedicalHistory` Pydantic schema, medical history prompts, example files
  - `model_outputs_seg_MenstrualHistory` → Uses `MenstrualHistory` Pydantic schema, menstrual history prompts, example files

- **Important Notes:**
  - ⚠️ The `adapter` parameter is **stored in the database** and used later for EMR conversion
  - ⚠️ If you don't specify an adapter, system uses default (Medical History)
  - ✅ System automatically prevents using wrong EMR schema for the transcription type

### 3.4 Live Recording (Demo only)
POST `/record/start/`
- Form: `patient_id` (required), `adapter` (optional)
- 200: `{ "message": "Recording started for patient <patient_id>", "audio_id": <uuid> }`
- Notes: Uses host microphone; not suitable for containers/cloud.

POST `/record/stop/`
- Form: `audio_id` (required)
- 200: `{ "status": "stopped", "audio_id": <uuid>, "path": "uploads/<uuid>.wav" }`
- Behavior: Queues transcription similar to `/upload/`.

### 3.5 Fetch Transcription
GET `/transcription/{audio_id}`
- Path: `audio_id` (int) — the `recording.id`.
- 200: Returns `text/plain` transcript file.
- 202: Transcript not ready.
- 404: Unknown `audio_id`.

### 3.6 GPU Diagnostics
GET `/gpu-status`
- 200: `{ gpu_available: boolean, memory?: {...} }`

POST `/gpu-cleanup`
- 200: `{ cleanup_success: boolean, memory_after_cleanup: {...}, potential_leak: boolean }`

### 3.7 EMR JSON
Prefix: `/emr`

GET `/emr/{file_id}`
- 200: `application/json` file
- 404: Not found

GET `/emr/meta/{file_id}`
- 200: `{ file_id, patient_id, recording_id, transcription_id, storage_path, schema_name, schema_version, created_at, status, size_bytes, checksum_sha256 }`
- 404: Not found

GET `/emr/by-transcription/{transcription_id}`
- 200: `{ file_id }`
- 404: Not found

GET `/emr/search?patient_id=<id>`
- 200: `[{ file_id, transcription_id, created_at }]`

---

## 4. Data Model

### 4.1 Current Architecture (Single Table Design)

**PatientRecord** — Primary table for all tracking:
```python
{
  id: int,                        # Primary key (auto-increment)
  PatientID: str,                 # External EMR patient identifier
  Date: str,                      # Recording date in user timezone (YYYY-MM-DD)
  Time: str,                      # Recording time in user timezone (HH:MM:SS)
  Transcript_file_ID: str?,       # e.g., "transcript_123" (matches filename)
  JSON_file_ID: str?,             # e.g., "emr_123" (matches EMR filename)
  user_timezone: str?,            # User's timezone for reference
  adapter_key: str?,              # CRITICAL: Which adapter was used (e.g., "model_outputs_seg_MedicalHistory")
  internal_recording_id: int?,    # Optional link to legacy Recording table
  status: str,                    # "uploaded" | "transcribed" | "emr_generated"
  created_at: timestamp           # System UTC timestamp
}
```

**Key Features:**
- ✅ **Single table** - no JOINs needed for queries
- ✅ **File ID matching** - Transcript_file_ID and JSON_file_ID match actual filenames
- ✅ **Adapter tracking** - Stores which model was used for transcription
- ✅ **User timezone** - Separate Date/Time fields in user's local time
- ✅ **Simple queries** - `SELECT * FROM patient_record WHERE PatientID = ?`

**File Organization:**
```
uploads/record_{id}.wav                                      # Audio file
transcripts/transcript_{id}.txt                              # Transcript file
emr/emr_{id}.json                                           # EMR JSON file
jsonfiles/emr_20251002_171203_patient_P001_transcription_123.json  # Timestamped backup
```

### 4.2 Legacy Architecture (Defined but Not Used in Main Flow)

These tables still exist for compatibility but the main upload flow uses `PatientRecord`:

- **Patient**: `{ id, patient_id, name, created_at }`
- **Recording**: `{ id, patient_id, audio_datetime (UTC), user_local_datetime?, user_timezone?, transcript_path?, adapter_key?, status }`
- **Audio**: `{ id, audio_id, filepath, language?, duration?, file_size?, recording_id, created_at }`
- **Transcription**: `{ id, transcript_id, audio_id, text, confidence_score?, processing_time?, created_at }`
- **EMRDocument**: `{ id, file_id, json_file_id, patient_id, recording_id?, transcription_id?, storage_path, schema_name, schema_version, created_at, status, size_bytes?, checksum_sha256? }`

**Note:** These tables are created on startup but the simplified flow (via `/upload/`) uses only `PatientRecord`.

---

## 5. Examples (Windows PowerShell)

### 5.1 Medical History Upload

```powershell
# Using curl.exe (recommended for file uploads)
curl.exe -X POST http://localhost:8000/upload/ `
  -F "patient_id=P001" `
  -F "file=@C:\path\to\medical_audio.wav;type=audio/wav" `
  -F "adapter=model_outputs_seg_MedicalHistory"

# Expected Response:
# { "status": "queued", "record_id": 123 }

# Check database after processing:
# patient_record.id = 123
# patient_record.adapter_key = "model_outputs_seg_MedicalHistory"
# patient_record.Transcript_file_ID = "transcript_123"
# patient_record.JSON_file_ID = "emr_123"
# Files created: transcripts/transcript_123.txt, emr/emr_123.json
```

### 5.2 Menstrual History Upload

```powershell
# Upload with menstrual history adapter
curl.exe -X POST http://localhost:8000/upload/ `
  -F "patient_id=P002" `
  -F "file=@C:\path\to\menstrual_audio.wav;type=audio/wav" `
  -F "adapter=model_outputs_seg_MenstrualHistory"

# System automatically:
# 1. Transcribes with MenstrualHistory LoRA adapter
# 2. Stores adapter_key in database
# 3. Uses MenstrualHistory EMR schema and prompts during conversion
# 4. Generates JSON with menstrual-specific fields
```

### 5.3 Upload with Timezone

```powershell
# With timezone-aware datetime
curl.exe -X POST http://localhost:8000/upload/ `
  -F "patient_id=P003" `
  -F "file=@C:\path\to\audio.wav;type=audio/wav" `
  -F "adapter=model_outputs_seg_MedicalHistory" `
  -F "user_local_datetime=2025-10-02T10:15:20-04:00"

# With naive local time + offset
$form = @{
  patient_id = 'P004'
  file = Get-Item 'C:\path\to\audio.wav'
  adapter = 'model_outputs_seg_MedicalHistory'
  user_local_datetime = '2025-10-02T10:15:20'
  user_timezone = '+08:00'
}
Invoke-RestMethod -Method Post -Uri 'http://localhost:8000/upload/' -Form $form
```

### 5.4 Query Patient Records (Python)

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
        print(f"  Date: {record.Date}, Time: {record.Time}")
        print(f"  Adapter: {record.adapter_key}")
        print(f"  Transcript: {record.Transcript_file_ID}")
        print(f"  EMR JSON: {record.JSON_file_ID}")
        print(f"  Status: {record.status}")
```

### 5.5 Google Colab Example

```python
# In Google Colab
from google.colab import files
import requests

# Upload audio file
uploaded = files.upload()
audio_filename = list(uploaded.keys())[0]

# Submit to API
url = "http://localhost:8000/upload/"
with open(audio_filename, 'rb') as f:
    files_dict = {'file': f}
    data = {
        'patient_id': 'P001',
        'adapter': 'model_outputs_seg_MedicalHistory'
    }
    response = requests.post(url, files=files_dict, data=data)
    print(response.json())

# Monitor progress
import time
record_id = response.json()['record_id']

while True:
    # Check status in database or via API
    time.sleep(5)
    # Query to check if status = 'emr_generated'
```

---

## 6. Error Handling
- `/upload/`: 202 (queued), 415 (non-WAV), 413 (if size enforced)
- `/transcription/{audio_id}`: 200 (file), 202 (not ready), 404 (unknown)
- EMR routes: 404 if not found

---

## 7. Migration & Compatibility

### 7.1 Current Migration Script (Required)

**For `patient_record` Table:**

Use **`db_migrate_1001.py`** or **`quick_fix_colab.py`** to add the `adapter_key` column to existing databases:

```powershell
# Windows/Local
python db_migrate_1001.py

# Google Colab
python quick_fix_colab.py
```

**What it does:**
- Checks if `patient_record` table exists
- Adds `adapter_key` column if missing
- Idempotent (safe to run multiple times)
- Verifies the change

**When needed:**
- If you have existing `patient.db` without `adapter_key` column
- After upgrading to adapter-based EMR conversion
- Required for system to work correctly

### 7.2 Obsolete Migration Scripts

**DO NOT USE (Legacy multi-table architecture):**
- ❌ `migrate_db.py` - For legacy Recording table
- ❌ `migrate_patient_db.py` - For 5-table legacy structure
- ❌ `migrate_colab_db.py` - Legacy Colab migration
- ❌ `migrate_to_single_table.py` - One-time conversion (already done)

These scripts modify tables that are no longer used in the main flow.

### 7.3 Backward Compatibility

- ✅ Fresh deployments: Tables auto-created with correct schema (no migration needed)
- ✅ Existing databases: Run `db_migrate_1001.py` once to add `adapter_key`
- ✅ Clients not sending timezone: Server uses UTC
- ✅ Missing adapter parameter: System uses default (Medical History)
- ✅ Legacy tables: Still defined for compatibility but not used in main flow

---

## 8. System Architecture

### 8.1 Key Design Decisions

**1. Adapter-Based Processing**
- Problem: Different medical conversations need different EMR structures
- Solution: LoRA-finetuned Whisper models for specialized transcription + automatic schema selection
- Benefit: One system handles multiple medical domains without manual configuration

**2. Single-Table Design**
- Problem: Complex JOINs across 5 tables (Patient → Recording → Audio → Transcription → EMRDocument)
- Solution: Simplified `patient_record` table with all tracking in one row
- Benefit: Simple queries, easy deployment, faster performance

**3. Sequential GPU Model Loading**
- Problem: Google Colab T4 has only 22.2 GB GPU memory
- Challenge: Whisper (~8GB) + EMR LLM (~14GB) = 22GB total
- Solution: Load Whisper → transcribe → unload → clear cache → load EMR → convert
- Benefit: Fits in single T4 GPU without OOM errors

**4. File ID Matching**
- Problem: Hard to correlate database IDs with actual files
- Solution: `Transcript_file_ID = "transcript_123"` matches `transcripts/transcript_123.txt`
- Benefit: Easy file retrieval, clear naming convention

### 8.2 Processing Pipeline

```
┌─────────────┐
│   Upload    │  - Audio saved to uploads/
│   Audio     │  - patient_record created
└──────┬──────┘  - adapter_key stored in DB
       │
       ▼
┌─────────────┐
│ Transcribe  │  - Load Whisper + adapter
│   (GPU)     │  - Generate transcript
└──────┬──────┘  - Save to transcripts/
       │         - Update Transcript_file_ID
       ▼
┌─────────────┐
│   Unload    │  - Unload Whisper completely
│   Whisper   │  - torch.cuda.empty_cache()
└──────┬──────┘  - Free ~8GB GPU memory
       │
       ▼
┌─────────────┐
│ EMR Convert │  - Read adapter_key from DB
│   (GPU)     │  - get_task_for_adapter()
└──────┬──────┘  - Load EMR LLM
       │         - Generate JSON with schema
       │         - Save to emr/ and jsonfiles/
       ▼         - Update JSON_file_ID
┌─────────────┐
│  Complete   │  - Status: emr_generated
└─────────────┘  - All files ready
```

### 8.3 Adapter-to-Schema Mapping

**Configuration File:** `emr/emr_tasks.py`

```python
TASKS = {
    "model_outputs_seg_MedicalHistory": EMRTaskConfig(
        schema_name="medical_his",
        schema=MedicalHistory,          # Pydantic schema
        title="Medical History",
        system_template="...",           # LLM prompt
        user_template="...",
        example_files=["example_medical_history.txt", "example_medical_history.jsonl"]
    ),
    "model_outputs_seg_MenstrualHistory": EMRTaskConfig(
        schema_name="menstrual_his",
        schema=MenstrualHistory,         # Different schema
        title="Menstrual History",
        system_template="...",           # Different prompt
        user_template="...",
        example_files=["example_menstrual_history.txt", "example_menstrual_history.jsonl"]
    ),
}
```

**How it works:**
1. Upload provides adapter (e.g., `model_outputs_seg_MenstrualHistory`)
2. Stored in `patient_record.adapter_key`
3. During EMR conversion, system calls `get_task_for_adapter(adapter_key)`
4. Returns correct `EMRTaskConfig` with schema/prompts/examples
5. LLM generates JSON matching that specific schema

### 8.4 GPU Memory Management

**Challenge:** Colab T4 Limits
- Total: 22.2 GB
- Whisper: ~8 GB during inference
- EMR LLM: ~14 GB with quantization
- Can't fit both simultaneously

**Solution: Sequential Loading**

```python
# 1. Load Whisper
whisper_model = load_whisper_with_adapter(adapter)
transcript = whisper_model.transcribe(audio)

# 2. CRITICAL: Complete unload before EMR
whisper_model.unload()
del whisper_model
gc.collect()
torch.cuda.empty_cache()
torch.cuda.synchronize()
# GPU now has ~22.1 GB free

# 3. Load EMR (safe now)
emr_model = load_emr_llm()  # Uses ~14 GB
json_output = emr_model.generate(transcript)
```

**Memory Monitoring:**
- Endpoints: `/gpu-status`, `/gpu-cleanup`
- Logging: GPU memory before/after each stage
- Leak detection: Warns if memory usage exceeds threshold

---

## 9. Change Log (October 2, 2025 Update)

**Major Changes:**
- ✅ **Adapter-based EMR conversion** — System automatically selects schema/prompts based on transcription adapter
- ✅ **Single-table database design** — Simplified `patient_record` table replaces 5-table architecture
- ✅ **GPU memory optimization** — Sequential model loading for Colab T4 deployment
- ✅ **File ID matching** — Database IDs now match actual filenames for easy retrieval
- ✅ **Adapter tracking** — Added `adapter_key` column to store which model was used

**Updated Sections:**
- Section 1: Added adapter-based processing overview and key features
- Section 3.3: Detailed adapter parameter explanation and processing flow
- Section 4: Documented single-table design vs legacy architecture
- Section 5: Added adapter-specific examples and Colab usage
- Section 7: Updated migration instructions for current system
- Section 8: New comprehensive architecture documentation

**Previous Changes (September 23, 2025):**
- Added optional form fields to `/upload/`: `user_local_datetime`, `user_timezone`
- Defined time semantics: canonical UTC `recording.audio_datetime`
- Documented GPU diagnostic endpoints

---

## 10. Troubleshooting

### 10.1 Common Issues

**Issue: "Unknown adapter key" in logs**
- **Cause:** Adapter name doesn't match available adapters
- **Solution:** Check adapter folder names in `adapters/` directory
- **Available:** `model_outputs_seg_MedicalHistory`, `model_outputs_seg_MenstrualHistory`

**Issue: "CUDA out of memory"**
- **Cause:** GPU memory leak or both models loaded simultaneously
- **Solution:** 
  - Check GPU status: `GET /gpu-status`
  - Force cleanup: `POST /gpu-cleanup`
  - Verify Whisper is unloaded before EMR conversion

**Issue: "Table patient_record has no column named adapter_key"**
- **Cause:** Using existing database without migration
- **Solution:** Run `python db_migrate_1001.py` or `python quick_fix_colab.py`

**Issue: EMR validation error**
- **Cause:** LLM output doesn't match Pydantic schema
- **Solution:** Check `emr/EMRconversion.py` schemas are flexible (have `extra = "allow"`)
- **Note:** Raw JSON is saved even if validation fails

**Issue: Wrong EMR schema applied**
- **Cause:** adapter_key not stored during upload
- **Solution:** Ensure upload includes `adapter` parameter
- **Check:** Verify `patient_record.adapter_key` is not NULL in database

### 10.2 Verification Steps

**Check if system is working:**

```python
# 1. Check database structure
import sqlite3
conn = sqlite3.connect("patient.db")
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(patient_record)")
columns = [row[1] for row in cursor.fetchall()]
print("adapter_key" in columns)  # Should be True

# 2. Check latest record
cursor.execute("SELECT * FROM patient_record ORDER BY id DESC LIMIT 1")
record = cursor.fetchone()
print(f"Latest record: {record}")

# 3. Check file existence
import os
record_id = record[0]  # Assuming id is first column
print(f"Audio: {os.path.exists(f'uploads/record_{record_id}.wav')}")
print(f"Transcript: {os.path.exists(f'transcripts/transcript_{record_id}.txt')}")
print(f"EMR JSON: {os.path.exists(f'emr/emr_{record_id}.json')}")
```

### 10.3 Performance Benchmarks (Colab T4)

**Expected Processing Times:**

| Stage | Time | GPU Memory |
|-------|------|------------|
| Upload | <1 sec | N/A |
| Whisper Transcription (5 min audio) | 30-60 sec | ~8 GB |
| GPU Cleanup | 2-3 sec | -8 GB |
| EMR Conversion | 15-30 sec | ~14 GB |
| Total | **~1-2 min** | Peak: 14 GB |

**If slower than expected:**
- Check GPU is available: `/gpu-status`
- Check for memory leaks: Look for >20GB usage after cleanup
- Check network: Model downloads may be slow on first run

---

## 11. PDF Export (Windows)
- VS Code: Open this file → Right-click → "Open Preview" → Print to PDF (Ctrl+P → Destination: Save as PDF)
- Browser: Use a Markdown preview extension or GitHub view → Print to PDF.
- Pandoc (optional):
```powershell
pandoc EMR_AI_System_API_UPDATED.md -o "EMR AI System (API) UPDATED.pdf"
```
