import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.deps import get_driver, close_driver
from app.routers import ingest, patients
from app.services.syncer import periodic_sync
from app.config import settings
from app.routers import rag


app = FastAPI(title="GraphRAG for EMR")

# static mount so /static/graphs/<file>.html is served
app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")

app.include_router(ingest.router)
app.include_router(patients.router)
app.include_router(rag.router)

@app.on_event("startup")
async def on_startup():
    get_driver()  # initialize
    # fire-and-forget periodic sync
    asyncio.create_task(periodic_sync(get_driver()))

@app.on_event("shutdown")
async def on_shutdown():
    close_driver()
