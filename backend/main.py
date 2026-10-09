import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.config import config
from backend.database import init_db
from backend.state_manager import state_manager
from backend.ingest import db_worker, router as ingest_router
from backend.routes import router as telemetry_router

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("telemetry.backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup sequence
    logger.info("Initializing Telemetry Backend...")
    await init_db()
    await db_worker.start()
    await state_manager.start()
    logger.info("Backend services ready on %s:%s", config.HOST, config.PORT)
    yield
    # Shutdown sequence
    logger.info("Shutting down Telemetry Backend...")
    await db_worker.stop()
    await state_manager.stop()
    logger.info("Backend shutdown complete.")


app = FastAPI(
    title="UAV Telemetry Collection API",
    description="High-frequency telemetry ingestion, time-series storage, and live telemetry streaming for UAVs/Drones.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(ingest_router)
app.include_router(telemetry_router)

# Mount Frontend static files if directory exists
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=config.HOST, port=config.PORT, reload=True)
