from contextlib import asynccontextmanager
from typing import AsyncIterator, Iterator
from sqlmodel import Session
from fastapi import Request
from AIEMR_system.speech2emr.app.database import get_session as get_speech_session
from AIEMR_system.chatbot_rag.app.deps import get_driver, close_driver


def speech_session() -> Iterator[Session]:
  """Reuse the speech-to-EMR session generator."""
  yield from get_speech_session()


@asynccontextmanager
async def neo4j_driver() -> AsyncIterator:
  driver = get_driver()
  try:
    yield driver
  finally:
    # keep driver open globally – actual shutdown handled in lifespan
    pass


def correlation_id(request: Request) -> str:
  return getattr(request.state, "correlation_id")
