import asyncio
import json
import logging
from typing import Dict, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect
from backend.models import DroneConsolidatedState, TelemetryPayload

logger = logging.getLogger("telemetry.backend.live_ws")


class LiveBroadcastManager:
    """Manages connected web dashboard clients and broadcasts real-time telemetry."""

    def __init__(self):
        # Maps drone_id -> Set[WebSocket] (or "" -> all)
        self._connections: Set[WebSocket] = set()
        self._drone_filters: Dict[WebSocket, Optional[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, drone_id: Optional[str] = None):
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
            self._drone_filters[websocket] = drone_id
        logger.info("Dashboard client connected (filter=%s). Total clients: %d", drone_id, len(self._connections))

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
            if websocket in self._drone_filters:
                del self._drone_filters[websocket]
        logger.info("Dashboard client disconnected. Remaining clients: %d", len(self._connections))

    async def broadcast_telemetry(self, payload: TelemetryPayload, state: DroneConsolidatedState):
        """Broadcasts both the raw payload and the consolidated state update."""
        if not self._connections:
            return

        message = {
            "type": "TELEMETRY_UPDATE",
            "drone_id": payload.drone_id,
            "timestamp": payload.timestamp.isoformat(),
            "msg_type": payload.msg_type,
            "data": payload.data,
            "state": state.model_dump(mode="json"),
        }
        json_str = json.dumps(message)

        dead_sockets = []
        async with self._lock:
            for ws in self._connections:
                filter_drone = self._drone_filters.get(ws)
                if filter_drone is None or filter_drone == payload.drone_id:
                    try:
                        await ws.send_text(json_str)
                    except Exception:
                        dead_sockets.append(ws)

            for ws in dead_sockets:
                if ws in self._connections:
                    self._connections.remove(ws)
                if ws in self._drone_filters:
                    del self._drone_filters[ws]


live_broadcaster = LiveBroadcastManager()
