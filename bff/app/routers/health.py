from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session, text

from ..dependencies import speech_session, neo4j_driver

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(
    session: Session = Depends(speech_session),
):
    deps = []
    try:
        session.exec(text("SELECT 1"))
        deps.append({"name": "speech-db", "status": "up"})
    except Exception as exc:
        deps.append({"name": "speech-db", "status": "down", "details": str(exc)})

    try:
        async with neo4j_driver() as driver:
            with driver.session() as s:
                s.run("RETURN 1").consume()
            deps.append({"name": "neo4j", "status": "up"})
    except Exception as exc:
        deps.append({"name": "neo4j", "status": "warning", "details": str(exc)})

    overall = "ready" if all(d["status"] == "up" for d in deps) else "degraded"
    return {"status": overall, "dependencies": deps}
