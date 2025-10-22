from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime

class PatientRecord(SQLModel, table=True):
    """Single table containing all patient recording information"""
    __tablename__ = "patient_record"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Patient identification
    PatientID: str = Field(index=True)  # The ID of this patient in the EMR system
    
    # User timezone date and time (separate columns as requested)
    Date: str = Field(index=True)  # Date in user's timezone (YYYY-MM-DD format)
    Time: str = Field(index=True)  # Time in user's timezone (HH:MM:SS format)
    
    # File IDs that match actual filenames
    Transcript_file_ID: Optional[str] = Field(default=None, index=True)  # Matches transcript filename
    JSON_file_ID: Optional[str] = Field(default=None, index=True)        # Matches JSON filename
    
    # Internal tracking (optional, for system use)
    user_timezone: Optional[str] = None  # Store the user's timezone for reference
    adapter_key: Optional[str] = None  # Track which adapter/model was used for transcription
    internal_recording_id: Optional[int] = None  # Link to original recording if needed during migration
    status: str = Field(default="uploaded")  # uploaded, transcribed, emr_generated
    created_at: datetime = Field(default_factory=datetime.utcnow)  # System timestamp in UTC