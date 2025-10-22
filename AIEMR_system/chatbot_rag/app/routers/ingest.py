from fastapi import APIRouter, Depends
from app.deps import get_driver
from app.services.syncer import sync_once

router = APIRouter(prefix="/ingest", tags=["ingest"])

@router.post("/sync", summary="Run one sync pass over the EMR directory")
async def run_sync(driver = Depends(get_driver)):
    await sync_once(driver)
    return {"status": "ok"}
