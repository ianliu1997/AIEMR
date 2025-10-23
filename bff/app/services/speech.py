from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from sqlmodel import Session

from AIEMR_system.speech2emr.app.settings import settings as speech_settings
from AIEMR_system.speech2emr.app.simple_crud import get_all_records
from AIEMR_system.speech2emr.app.simple_models import PatientRecord


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=None).isoformat() + "Z"
    return dt.isoformat()


def _file_timestamp(path: Optional[Path]) -> Optional[str]:
    if not path:
        return None
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
    except FileNotFoundError:
        return None
    return _iso(mtime)


def _transcript_path(record: PatientRecord) -> Optional[Path]:
    if not record.Transcript_file_ID:
        return None
    return speech_settings.TRANSCRIPT_DIR / f"{record.Transcript_file_ID}.txt"


def _emr_path(record: PatientRecord) -> Optional[Path]:
    if not record.JSON_file_ID:
        return None
    return Path(speech_settings.EMR_DIR) / f"{record.JSON_file_ID}.json"


def serialize_record(record: PatientRecord) -> dict:
    transcript_path = _transcript_path(record)
    emr_path = _emr_path(record)

    return {
        "jobId": str(record.id),
        "patientId": record.PatientID,
        "status": record.status,
        "adapterKey": record.adapter_key,
        "topics": None,
        "submittedAt": _iso(record.created_at),
        "transcriptFileId": record.Transcript_file_ID,
        "emrFileId": record.JSON_file_ID,
        "transcriptUrl": f"/v1/speech/jobs/{record.id}/transcript" if transcript_path else None,
        "emrUrl": f"/v1/speech/jobs/{record.id}/emr" if emr_path else None,
        "timeline": {
            "uploadedAt": _iso(record.created_at),
            "transcribedAt": _file_timestamp(transcript_path),
            "emrGeneratedAt": _file_timestamp(emr_path),
        },
        "errors": [],
    }


def list_jobs(session: Session, *, patient_id: Optional[str] = None) -> list[dict]:
    records: Iterable[PatientRecord] = get_all_records(session)
    ordered: list[PatientRecord] = sorted(
        (r for r in records if (not patient_id or r.PatientID == patient_id)),
        key=lambda r: (r.created_at or datetime.min),
        reverse=True,
    )
    return [serialize_record(r) for r in ordered]


def patient_summaries(session: Session) -> list[dict]:
    records: Iterable[PatientRecord] = get_all_records(session)
    buckets: dict[str, list[PatientRecord]] = {}
    for rec in records:
        buckets.setdefault(rec.PatientID, []).append(rec)

    summaries: list[dict] = []
    for patient_id, items in buckets.items():
        latest = max(items, key=lambda r: r.created_at or datetime.min)
        summaries.append(
            {
                "patientId": patient_id,
                "latestStatus": latest.status,
                "latestJobId": str(latest.id) if latest.id is not None else None,
                "recordCount": len(items),
                "lastUpdatedAt": _iso(latest.created_at),
            }
        )
    summaries.sort(key=lambda s: s.get("lastUpdatedAt") or "", reverse=True)
    return summaries
