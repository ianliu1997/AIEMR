from typing import Optional
from datetime import datetime
from sqlmodel import Session, select
from app import models
from app.settings import settings


def get_patient_by_id(session: Session, patient_id: int) -> Optional[models.Patient]:
    try:
        # Try with new schema (after migration)
        return session.exec(
            select(models.Patient).where(models.Patient.id == patient_id)
        ).first()
    except Exception as e:
        # Handle case where database hasn't been migrated yet
        if "no such column" in str(e):
            # Fallback: use raw SQL to get patient with old schema
            import sqlite3
            from pathlib import Path
            
            db_path = Path("patient.db")
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()
                try:
                    cursor.execute("SELECT id, name FROM patient WHERE id = ?", (patient_id,))
                    result = cursor.fetchone()
                    if result:
                        # Create minimal Patient object - we'll update schema later
                        patient = models.Patient(name=result[1], patient_id=f"PAT_{result[0]:08d}")
                        patient.id = result[0]
                        return patient
                finally:
                    conn.close()
        raise e


def create_patient(session: Session, name: str) -> models.Patient:
    import uuid
    # Generate a unique patient_id for new patients
    patient_id = f"PAT_{uuid.uuid4().hex[:8]}"
    patient = models.Patient(name=name, patient_id=patient_id)
    session.add(patient)
    session.commit()
    session.refresh(patient)
    return patient




def create_recording(
    session: Session,
    patient_id: int,
    *,
    audio_datetime: Optional[datetime] = None,
    user_local_datetime: Optional[datetime] = None,
    user_timezone: Optional[str] = None,
) -> models.Recording:
    if audio_datetime is None:
        audio_datetime = datetime.utcnow()
    recording = models.Recording(
        patient_id=patient_id,
        audio_datetime=audio_datetime,
        user_local_datetime=user_local_datetime,
        user_timezone=user_timezone,
    )
    session.add(recording)
    session.commit()
    session.refresh(recording)
    return recording


def create_audio(
    session: Session,
    filepath: str,
    recording_id: int,
    language: Optional[str] = None,
    duration: Optional[float] = None
) -> models.Audio:
    audio = models.Audio(
        filepath=filepath,
        language=language,
        duration=duration,
        recording_id=recording_id,
    )
    session.add(audio)
    session.commit()
    session.refresh(audio)
    return audio


def create_transcription(
    session: Session, audio_id: int, text: str
) -> models.Transcription:
    transcription = models.Transcription(audio_id=audio_id, text=text)
    session.add(transcription)
    session.commit()
    session.refresh(transcription)
    return transcription


def get_audio_by_id(session: Session, audio_id: int) -> Optional[models.Audio]:
    return session.exec(
        select(models.Audio).where(models.Audio.id == audio_id)
    ).first()


def get_or_create_patient(session: Session, name: str) -> models.Patient:
    patient = session.exec(select(models.Patient).where(models.Patient.name == name)).first()
    if patient:
        return patient
    return create_patient(session, name)


def add_recording(
    session: Session,
    patient: models.Patient,
    filename: str,
    adapter_key: Optional[str] | None,
    *,
    audio_datetime: Optional["datetime"] = None,
    user_local_datetime: Optional["datetime"] = None,
    user_timezone: Optional[str] = None,
):
    if patient.id is not None:
        recording = create_recording(
            session,
            patient.id,
            audio_datetime=audio_datetime,
            user_local_datetime=user_local_datetime,
            user_timezone=user_timezone,
        )
        recording.adapter_key = adapter_key
        session.add(recording)
        session.commit()
        if recording.id is not None:
            create_audio(session, filepath=str(settings.UPLOAD_DIR / filename), recording_id=recording.id)
        return recording
    else:
        raise ValueError("Patient ID cannot be None")


def set_transcript_path(session: Session, recording_id: int, path: str):
    recording = session.get(models.Recording, recording_id)
    if recording:
        recording.transcript_path = path
        session.add(recording)
        session.commit()
