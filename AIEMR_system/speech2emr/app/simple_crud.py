from typing import Optional
from sqlmodel import Session, select
from app.simple_models import PatientRecord
from datetime import datetime, timezone


def create_patient_record(
    session: Session,
    patient_id: str,
    user_local_datetime: Optional[datetime] = None,
    user_timezone: Optional[str] = None,
    adapter_key: Optional[str] = None,
) -> PatientRecord:
    """Create a new patient record with user timezone date/time"""
    
    # Use provided user local time or fall back to UTC
    if user_local_datetime:
        # Split user local datetime into Date and Time strings
        date_str = user_local_datetime.strftime("%Y-%m-%d")
        time_str = user_local_datetime.strftime("%H:%M:%S")
    else:
        # Fallback to current UTC time
        utc_now = datetime.utcnow()
        date_str = utc_now.strftime("%Y-%m-%d")
        time_str = utc_now.strftime("%H:%M:%S")
        user_timezone = "UTC"
    
    record = PatientRecord(
        PatientID=patient_id,
        Date=date_str,
        Time=time_str,
        user_timezone=user_timezone,
        adapter_key=adapter_key,
        status="uploaded"
    )
    
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def update_transcript_file_id(session: Session, record_id: int, transcript_file_id: str):
    """Update the Transcript_file_ID when transcription is complete"""
    record = session.get(PatientRecord, record_id)
    if record:
        record.Transcript_file_ID = transcript_file_id
        record.status = "transcribed"
        session.add(record)
        session.commit()


def update_json_file_id(session: Session, record_id: int, json_file_id: str):
    """Update the JSON_file_ID when EMR processing is complete"""
    record = session.get(PatientRecord, record_id)
    if record:
        record.JSON_file_ID = json_file_id
        record.status = "emr_generated"
        session.add(record)
        session.commit()


def get_patient_records(session: Session, patient_id: str):
    """Get all records for a specific patient"""
    return list(session.exec(
        select(PatientRecord).where(PatientRecord.PatientID == patient_id)
    ).all())


def get_record_by_id(session: Session, record_id: int) -> Optional[PatientRecord]:
    """Get a specific patient record by ID"""
    return session.get(PatientRecord, record_id)


def get_record_by_transcript_id(session: Session, transcript_id: str) -> Optional[PatientRecord]:
    """Find record by transcript file ID"""
    return session.exec(
        select(PatientRecord).where(PatientRecord.Transcript_file_ID == transcript_id)
    ).first()


def get_record_by_json_id(session: Session, json_id: str) -> Optional[PatientRecord]:
    """Find record by JSON file ID"""
    return session.exec(
        select(PatientRecord).where(PatientRecord.JSON_file_ID == json_id)
    ).first()


def get_all_records(session: Session):
    """Get all patient records"""
    return list(session.exec(select(PatientRecord)).all())