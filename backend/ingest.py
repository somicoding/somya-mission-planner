import asyncio
import json
import logging
from typing import List, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status, HTTPException
from backend.config import config
from backend.database import db_manager
from backend.models import (
    TelemetryPayload,
    BatchTelemetryPayload,
)
from backend.state_manager import state_manager
from backend.live_ws import live_broadcaster

logger = logging.getLogger("telemetry.backend.ingest")

router = APIRouter(prefix="/api/v1/telemetry", tags=["Ingest"])


class DatabaseBatchWorker:
    """Asynchronous background worker that buffers high-frequency telemetry records

    and commits them to the database in bulk batches for maximum I/O performance.
    """

    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=20000)
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None

    async def start(self):
        self._running = True
        self._worker_task = asyncio.create_task(self._process_loop())
        logger.info("Database batch worker started.")

    async def stop(self):
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        # Flush any remaining items
        await self._flush_remaining()
        logger.info("Database batch worker stopped.")

    async def enqueue(self, payload: TelemetryPayload):
        try:
            self.queue.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("DB buffer queue full! Discarding oldest telemetry point.")
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(payload)
            except Exception:
                pass

    async def _process_loop(self):
        while self._running:
            batch: List[TelemetryPayload] = []
            try:
                item = await asyncio.wait_for(self.queue.get(), timeout=config.DB_FLUSH_INTERVAL_SEC)
                batch.append(item)

                while len(batch) < config.DB_BATCH_SIZE and not self.queue.empty():
                    try:
                        batch.append(self.queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
            except asyncio.TimeoutError:
                pass

            if batch:
                await db_manager.save_telemetry_batch(batch)

    async def _flush_remaining(self):
        batch = []
        while not self.queue.empty():
            try:
                batch.append(self.queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if batch:
            await db_manager.save_telemetry_batch(batch)


db_worker = DatabaseBatchWorker()


# ==============================================================================
# Ingestion Endpoints
# ==============================================================================

@router.websocket("/ws/ingest")
async def websocket_telemetry_ingest(
    websocket: WebSocket,
    drone_id: str = Query(..., description="ID of the reporting drone"),
    token: Optional[str] = Query(None, description="API authorization token"),
):
    """Low-latency WebSocket telemetry ingestion endpoint."""
    if token != config.API_KEY:
        logger.warning("Unauthorized telemetry ingest attempt from drone '%s' (bad token)", drone_id)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    logger.info("Collector connected for drone '%s'", drone_id)

    try:
        while True:
            text_data = await websocket.receive_text()
            try:
                raw_json = json.loads(text_data)
                
                # Check for batch vs single packet
                if "batch" in raw_json and isinstance(raw_json["batch"], list):
                    items = [TelemetryPayload(**item) for item in raw_json["batch"]]
                else:
                    items = [TelemetryPayload(**raw_json)]

                for item in items:
                    # Update in-memory state
                    consolidated_state = await state_manager.update_state(item)
                    
                    # Queue for async DB insertion
                    await db_worker.enqueue(item)
                    
                    # Broadcast live update to dashboards
                    await live_broadcaster.broadcast_telemetry(item, consolidated_state)

            except Exception as e:
                logger.debug("Ingestion decode error: %s (payload: %s)", e, text_data[:100])

    except WebSocketDisconnect:
        logger.info("Collector for drone '%s' disconnected.", drone_id)
    except Exception as e:
        logger.error("Error in telemetry ingest stream for drone '%s': %s", drone_id, e)


@router.post("/batch", status_code=status.HTTP_202_ACCEPTED)
async def http_batch_ingest(
    payload: BatchTelemetryPayload,
    token: Optional[str] = Query(None),
):
    """Optional HTTP REST batch ingestion endpoint."""
    if token != config.API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    for item in payload.batch:
        consolidated = await state_manager.update_state(item)
        await db_worker.enqueue(item)
        await live_broadcaster.broadcast_telemetry(item, consolidated)

    return {"status": "accepted", "count": len(payload.batch)}
