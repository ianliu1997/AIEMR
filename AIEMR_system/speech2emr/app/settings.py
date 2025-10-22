from pathlib import Path
import logging
from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    # ---------- model / paths ----------
    STT_MODEL_NAME: str = "Na0s/Medical-Whisper-Large-v3"
    UPLOAD_DIR: Path = Path("uploads")
    TRANSCRIPT_DIR: Path = Path("transcripts")

    # ---------- Update fine-tuned LoRA adapter ----------
    STT_ADAPTERS_DIR: Path = Path("adapters")
    DEFAULT_ADAPTER: str | None = None  # Optional default adapter to load on startup
    ALLOW_MODEL_SWITCH_PER_REQUEST: bool = True
    STT_MERGE_LORA: bool = True  # Default: merge adapters into base at load (faster inference)
    STT_TASK: str = "transcribe"
    STT_LANGUAGE: str = "en"

    # ---------- audio settings ----------
    STT_TARGET_SR: int = 16000
    STT_CHUNK_LENGTH_S: int = 30   # seconds
    STT_STRIDE_LENGTH_S: int = 0   # seconds (no overlap)
    STT_ENFORCE_TRAIN_PREPROC: bool = True

    # Backward-compat (if anything still imports the old names)
    @property
    def STT_CHUNK_LENGTHS(self) -> int:
        return self.STT_CHUNK_LENGTH_S

    @property
    def STT_STRIDE_LENGTHS(self) -> int:
        return self.STT_STRIDE_LENGTH_S


    # ---------- database ----------
    DB_URL: str = "sqlite:///./patient.db"

    # ---------- EMR conversion ----------
    EMR_DIR: str = os.getenv("EMR_DIR", "emr/")


    # ---------- celery (optional) ----------
    CELERY_BROKER_URL: str = "redis://localhost/0"
    USE_CELERY: bool = False  # Default: off for local development

    class Config:
        env_file = ".env"        # let users override defaults

settings = Settings()

# ---------- one-time folder creation ----------
settings.UPLOAD_DIR.mkdir(exist_ok=True)
settings.TRANSCRIPT_DIR.mkdir(exist_ok=True)

# ---------- logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
