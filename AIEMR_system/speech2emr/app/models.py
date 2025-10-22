from typing import Optional
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
import uuid

class Patient(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: str = Field(index=True, unique=True)  # External patient identifier
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    recordings: list["Recording"] = Relationship(back_populates="patient")


class Recording(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patient.id")
    audio_datetime: datetime = Field(default_factory=datetime.utcnow, index=True)  # When audio was recorded
    # Client-provided local time information (optional)
    user_local_datetime: Optional[datetime] = None  # Local time reported by client (naive, in user's timezone)
    user_timezone: Optional[str] = None             # IANA TZ (e.g., "America/New_York") or offset (e.g., "+08:00")
    transcript_path: Optional[str] = None  # Path to the transcription file
    adapter_key: Optional[str] = None  # Which adapter was used for this recording
    status: str = Field(default="pending")  # pending, processing, completed, failed

    patient: Optional[Patient] = Relationship(back_populates="recordings")
    audio: Optional["Audio"] = Relationship(back_populates="recording")



class Audio(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    audio_id: str = Field(default_factory=lambda: f"AUD_{uuid.uuid4().hex[:8]}", index=True, unique=True)  # External audio identifier
    filepath: str
    language: Optional[str]
    duration: Optional[float]
    file_size: Optional[int] = None  # File size in bytes
    recording_id: Optional[int] = Field(default=None, foreign_key="recording.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    recording: Optional[Recording] = Relationship(back_populates="audio")
    transcription: Optional["Transcription"] = Relationship(back_populates="audio")


class Transcription(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    transcript_id: str = Field(default_factory=lambda: f"TXN_{uuid.uuid4().hex[:8]}", index=True, unique=True)  # External transcript identifier
    audio_id: int = Field(foreign_key="audio.id")
    text: str
    confidence_score: Optional[float] = None  # ASR confidence if available
    processing_time: Optional[float] = None  # Time taken to process in seconds
    created_at: datetime = Field(default_factory=datetime.utcnow)

    audio: Optional[Audio] = Relationship(back_populates="transcription")
    emr_documents: list["EMRDocument"] = Relationship(back_populates="transcription")


class EMRDocument(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    file_id: str = Field(default_factory=lambda: uuid.uuid4().hex, index=True, unique=True)
    json_file_id: str = Field(default_factory=lambda: f"JSON_{uuid.uuid4().hex[:8]}", index=True, unique=True)  # External JSON file identifier

    # linkages
    patient_id: str = Field(index=True)                      # from Recording.patient_id
    recording_id: Optional[int] = Field(default=None, foreign_key="recording.id")
    transcription_id: Optional[int] = Field(default=None, foreign_key="transcription.id", unique=True)

    # storage & metadata
    storage_path: str                                        # absolute or relative path to .json on disk
    schema_name: str = Field(default="MenstrualHistory")
    schema_version: str = Field(default="1.0")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="ready")                     # ready | failed
    size_bytes: Optional[int] = None
    checksum_sha256: Optional[str] = None

    # Relationship
    transcription: Optional[Transcription] = Relationship(back_populates="emr_documents")