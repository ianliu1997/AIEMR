from pydantic import Field
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # Neo4j
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASS: str
    EMR_DIR: Path = Field(default=Path("data"))
    STATIC_DIR: Path = Field(default=Path("static"))
    GRAPH_HTML_DIR: Path = Field(default_factory=lambda: Path("static/graphs"))
    SYNC_INTERVAL_SEC: int = 60  # poll interval for directory sync

    # Qdrant / Embeddings / Privacy
    QDRANT_URL: str
    QDRANT_API_KEY: str
    QDRANT_COLLECTION: str = "patient_transcript"
    OPENAI_API_KEY: str
    EMBED_MODEL: str = "text-embedding-3-small"
    EMBED_DIM: int = 1536
    CHAT_MODEL: str = "gpt-5-mini"
    PATIENT_SALT: str = "AIEMR"

    class Config:
        env_file = ".env"

settings = Settings()
settings.GRAPH_HTML_DIR.mkdir(parents=True, exist_ok=True)
