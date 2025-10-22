"""
Database query helpers for retrieving patient information with all requested tracking fields.
This module provides convenient functions to access:
1. Patient ID
2. Audio date and time  
3. Audio ID
4. Transcript ID
5. JSON file ID
"""

from typing import List, Dict, Optional, Tuple
from sqlmodel import Session, select
from datetime import datetime

from app.models import Patient, Recording, Audio, Transcription, EMRDocument
from app.database import engine

class PatientRecordView:
    """Complete view of patient record with all tracking IDs"""
    
    def __init__(self, 
                 patient_id: str,
                 patient_name: str,
                 audio_datetime: datetime,
                 audio_id: str,
                 transcript_id: str,
                 json_file_id: str,
                 recording_status: str = None,
                 audio_duration: float = None,
                 transcript_text: str = None,
                 json_file_path: str = None):
        self.patient_id = patient_id
        self.patient_name = patient_name
        self.audio_datetime = audio_datetime
        self.audio_id = audio_id
        self.transcript_id = transcript_id
        self.json_file_id = json_file_id
        self.recording_status = recording_status
        self.audio_duration = audio_duration
        self.transcript_text = transcript_text
        self.json_file_path = json_file_path
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for easy serialization"""
        return {
            "patient_id": self.patient_id,
            "patient_name": self.patient_name,
            "audio_datetime": self.audio_datetime.isoformat() if self.audio_datetime else None,
            "audio_id": self.audio_id,
            "transcript_id": self.transcript_id,
            "json_file_id": self.json_file_id,
            "recording_status": self.recording_status,
            "audio_duration": self.audio_duration,
            "transcript_text": self.transcript_text,
            "json_file_path": self.json_file_path
        }

def get_all_patient_records() -> List[PatientRecordView]:
    """
    Retrieve all patient records with complete tracking information.
    Returns a list of PatientRecordView objects.
    """
    with Session(engine) as session:
        # Complex join query to get all related data
        statement = (
            select(
                Patient.patient_id,
                Patient.name,
                Recording.audio_datetime,
                Audio.audio_id,
                Transcription.transcript_id,
                EMRDocument.json_file_id,
                Recording.status,
                Audio.duration,
                Transcription.text,
                EMRDocument.storage_path
            )
            .select_from(Patient)
            .join(Recording, Patient.id == Recording.patient_id)
            .join(Audio, Recording.id == Audio.recording_id)
            .join(Transcription, Audio.id == Transcription.audio_id)
            .join(EMRDocument, Transcription.id == EMRDocument.transcription_id)
            .order_by(Recording.audio_datetime.desc())
        )
        
        results = session.exec(statement).all()
        
        return [
            PatientRecordView(
                patient_id=row.patient_id,
                patient_name=row.name,
                audio_datetime=row.audio_datetime,
                audio_id=row.audio_id,
                transcript_id=row.transcript_id,
                json_file_id=row.json_file_id,
                recording_status=row.status,
                audio_duration=row.duration,
                transcript_text=row.text,
                json_file_path=row.storage_path
            )
            for row in results
        ]

def get_patient_records_by_patient_id(patient_id: str) -> List[PatientRecordView]:
    """
    Get all records for a specific patient ID.
    """
    with Session(engine) as session:
        statement = (
            select(
                Patient.patient_id,
                Patient.name,
                Recording.audio_datetime,
                Audio.audio_id,
                Transcription.transcript_id,
                EMRDocument.json_file_id,
                Recording.status,
                Audio.duration,
                Transcription.text,
                EMRDocument.storage_path
            )
            .select_from(Patient)
            .join(Recording, Patient.id == Recording.patient_id)
            .join(Audio, Recording.id == Audio.recording_id)
            .join(Transcription, Audio.id == Transcription.audio_id)
            .join(EMRDocument, Transcription.id == EMRDocument.transcription_id)
            .where(Patient.patient_id == patient_id)
            .order_by(Recording.audio_datetime.desc())
        )
        
        results = session.exec(statement).all()
        
        return [
            PatientRecordView(
                patient_id=row.patient_id,
                patient_name=row.name,
                audio_datetime=row.audio_datetime,
                audio_id=row.audio_id,
                transcript_id=row.transcript_id,
                json_file_id=row.json_file_id,
                recording_status=row.status,
                audio_duration=row.duration,
                transcript_text=row.text,
                json_file_path=row.storage_path
            )
            for row in results
        ]

def get_patient_record_by_audio_id(audio_id: str) -> Optional[PatientRecordView]:
    """
    Get patient record by audio ID.
    """
    with Session(engine) as session:
        statement = (
            select(
                Patient.patient_id,
                Patient.name,
                Recording.audio_datetime,
                Audio.audio_id,
                Transcription.transcript_id,
                EMRDocument.json_file_id,
                Recording.status,
                Audio.duration,
                Transcription.text,
                EMRDocument.storage_path
            )
            .select_from(Patient)
            .join(Recording, Patient.id == Recording.patient_id)
            .join(Audio, Recording.id == Audio.recording_id)
            .join(Transcription, Audio.id == Transcription.audio_id)
            .join(EMRDocument, Transcription.id == EMRDocument.transcription_id)
            .where(Audio.audio_id == audio_id)
        )
        
        result = session.exec(statement).first()
        
        if result:
            return PatientRecordView(
                patient_id=result.patient_id,
                patient_name=result.name,
                audio_datetime=result.audio_datetime,
                audio_id=result.audio_id,
                transcript_id=result.transcript_id,
                json_file_id=result.json_file_id,
                recording_status=result.status,
                audio_duration=result.duration,
                transcript_text=result.text,
                json_file_path=result.storage_path
            )
        return None

def get_patient_record_by_transcript_id(transcript_id: str) -> Optional[PatientRecordView]:
    """
    Get patient record by transcript ID.
    """
    with Session(engine) as session:
        statement = (
            select(
                Patient.patient_id,
                Patient.name,
                Recording.audio_datetime,
                Audio.audio_id,
                Transcription.transcript_id,
                EMRDocument.json_file_id,
                Recording.status,
                Audio.duration,
                Transcription.text,
                EMRDocument.storage_path
            )
            .select_from(Patient)
            .join(Recording, Patient.id == Recording.patient_id)
            .join(Audio, Recording.id == Audio.recording_id)
            .join(Transcription, Audio.id == Transcription.audio_id)
            .join(EMRDocument, Transcription.id == EMRDocument.transcription_id)
            .where(Transcription.transcript_id == transcript_id)
        )
        
        result = session.exec(statement).first()
        
        if result:
            return PatientRecordView(
                patient_id=result.patient_id,
                patient_name=result.name,
                audio_datetime=result.audio_datetime,
                audio_id=result.audio_id,
                transcript_id=result.transcript_id,
                json_file_id=result.json_file_id,
                recording_status=result.status,
                audio_duration=result.duration,
                transcript_text=result.text,
                json_file_path=result.storage_path
            )
        return None

def get_patient_record_by_json_id(json_file_id: str) -> Optional[PatientRecordView]:
    """
    Get patient record by JSON file ID.
    """
    with Session(engine) as session:
        statement = (
            select(
                Patient.patient_id,
                Patient.name,
                Recording.audio_datetime,
                Audio.audio_id,
                Transcription.transcript_id,
                EMRDocument.json_file_id,
                Recording.status,
                Audio.duration,
                Transcription.text,
                EMRDocument.storage_path
            )
            .select_from(Patient)
            .join(Recording, Patient.id == Recording.patient_id)
            .join(Audio, Recording.id == Audio.recording_id)
            .join(Transcription, Audio.id == Transcription.audio_id)
            .join(EMRDocument, Transcription.id == EMRDocument.transcription_id)
            .where(EMRDocument.json_file_id == json_file_id)
        )
        
        result = session.exec(statement).first()
        
        if result:
            return PatientRecordView(
                patient_id=result.patient_id,
                patient_name=result.name,
                audio_datetime=result.audio_datetime,
                audio_id=result.audio_id,
                transcript_id=result.transcript_id,
                json_file_id=result.json_file_id,
                recording_status=result.status,
                audio_duration=result.duration,
                transcript_text=result.text,
                json_file_path=result.storage_path
            )
        return None

def get_records_by_date_range(start_date: datetime, end_date: datetime) -> List[PatientRecordView]:
    """
    Get all patient records within a date range based on audio_datetime.
    """
    with Session(engine) as session:
        statement = (
            select(
                Patient.patient_id,
                Patient.name,
                Recording.audio_datetime,
                Audio.audio_id,
                Transcription.transcript_id,
                EMRDocument.json_file_id,
                Recording.status,
                Audio.duration,
                Transcription.text,
                EMRDocument.storage_path
            )
            .select_from(Patient)
            .join(Recording, Patient.id == Recording.patient_id)
            .join(Audio, Recording.id == Audio.recording_id)
            .join(Transcription, Audio.id == Transcription.audio_id)
            .join(EMRDocument, Transcription.id == EMRDocument.transcription_id)
            .where(Recording.audio_datetime >= start_date)
            .where(Recording.audio_datetime <= end_date)
            .order_by(Recording.audio_datetime.desc())
        )
        
        results = session.exec(statement).all()
        
        return [
            PatientRecordView(
                patient_id=row.patient_id,
                patient_name=row.name,
                audio_datetime=row.audio_datetime,
                audio_id=row.audio_id,
                transcript_id=row.transcript_id,
                json_file_id=row.json_file_id,
                recording_status=row.status,
                audio_duration=row.duration,
                transcript_text=row.text,
                json_file_path=row.storage_path
            )
            for row in results
        ]

def get_summary_stats() -> Dict:
    """
    Get summary statistics of the database.
    """
    with Session(engine) as session:
        # Count total records
        total_patients = session.exec(select(Patient)).all()
        total_recordings = session.exec(select(Recording)).all()
        total_audio = session.exec(select(Audio)).all()
        total_transcripts = session.exec(select(Transcription)).all()
        total_emr_docs = session.exec(select(EMRDocument)).all()
        
        return {
            "total_patients": len(total_patients),
            "total_recordings": len(total_recordings),
            "total_audio_files": len(total_audio),
            "total_transcripts": len(total_transcripts),
            "total_emr_documents": len(total_emr_docs),
            "last_updated": datetime.utcnow().isoformat()
        }

# Example usage functions
def print_all_records():
    """Print all patient records in a readable format"""
    records = get_all_patient_records()
    
    print("🏥 All Patient Records")
    print("=" * 80)
    
    for i, record in enumerate(records, 1):
        print(f"\n📋 Record {i}:")
        print(f"   Patient ID: {record.patient_id}")
        print(f"   Patient Name: {record.patient_name}")
        print(f"   Audio Date/Time: {record.audio_datetime}")
        print(f"   Audio ID: {record.audio_id}")
        print(f"   Transcript ID: {record.transcript_id}")
        print(f"   JSON File ID: {record.json_file_id}")
        print(f"   Status: {record.recording_status}")
        if record.audio_duration:
            print(f"   Duration: {record.audio_duration:.2f}s")

def print_summary():
    """Print database summary statistics"""
    stats = get_summary_stats()
    
    print("📊 Database Summary")
    print("=" * 40)
    for key, value in stats.items():
        print(f"   {key.replace('_', ' ').title()}: {value}")

if __name__ == "__main__":
    print("🗄️  Patient Database Query Helper")
    print("Testing database queries...")
    
    try:
        print_summary()
        print("\n" + "="*80)
        print_all_records()
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Make sure to run the migration script first!")