from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from AIEMR_system.speech2emr.app.database import engine
from AIEMR_system.speech2emr.app import models as speech_models
from AIEMR_system.speech2emr.app.simple_models import PatientRecord
from AIEMR_system.chatbot_rag.app.deps import close_driver

from .config import settings
from .routers import health, speech, rag


def problem_response(status: int, title: str, detail: str | None = None, instance: str | None = None) -> JSONResponse:
    payload: Dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
    }
    if detail:
        payload["detail"] = detail
    if instance:
        payload["instance"] = instance
    return JSONResponse(status_code=status, content=payload, media_type="application/problem+json")


@asynccontextmanager
async def lifespan(app: FastAPI):
    speech_models.SQLModel.metadata.create_all(engine)
    PatientRecord.metadata.create_all(engine)
    yield
    close_driver()


app = FastAPI(
    title="AIEMR Gateway",
    description="BFF for Speech-to-EMR and Graph RAG demo",
    version="0.1.0",
    lifespan=lifespan,
)


if settings.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-correlation-id"],
    )


@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("x-correlation-id") or uuid.uuid4().hex
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["x-correlation-id"] = correlation_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail if isinstance(exc.detail, str) else None
    return problem_response(exc.status_code, title=detail or "HTTP error", detail=detail)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return problem_response(400, title="Validation error", detail=str(exc.errors()))


app.include_router(health.router)
app.include_router(speech.router)
app.include_router(rag.router)


@app.get("/")
async def root():
    return {"message": "AIEMR Gateway is running"}
