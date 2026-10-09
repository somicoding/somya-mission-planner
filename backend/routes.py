from datetime import datetime, timezone
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from backend.database import db_manager
from backend.models import (
    DroneResponse,
    DroneConsolidatedState,
    TelemetryHistoryResponse,
    TelemetryHistoryItem,
    FlightStatsResponse,
)
from backend.state_manager import state_manager
from backend.live_ws import live_broadcaster

logger = logging.getLogger("telemetry.backend.routes")

router = APIRouter(prefix="/api/v1", tags=["Telemetry API"])


# ==============================================================================
# Health Probe
# ==============================================================================

@router.get("/health", tags=["System"])
async def health_check():
    """Health status probe checking database and state cache."""
    db_health = await db_manager.health_check()
    active_drones = [
        d_id for d_id, st in state_manager.get_all_states().items() if st.status == "ONLINE"
    ]

    return {
        "status": "ok" if db_health.get("status") == "healthy" else "degraded",
        "database": db_health,
        "active_drones_count": len(active_drones),
        "active_drones": active_drones,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ==============================================================================
# Drone Fleet Management
# ==============================================================================

@router.get("/drones", response_model=List[DroneResponse])
async def list_drones():
    """Returns a list of all registered and discovered drones with their live status."""
    drones_db = await db_manager.get_drones()
    response: List[DroneResponse] = []
    seen_ids = set()

    for d in drones_db:
        seen_ids.add(d["id"])
        current_state = state_manager.get_state(d["id"])
        status_str = current_state.status if current_state else "OFFLINE"
        
        last_seen_dt = None
        if current_state and current_state.last_seen:
            last_seen_dt = current_state.last_seen
        elif d.get("last_seen"):
            try:
                last_seen_dt = datetime.fromisoformat(d["last_seen"])
            except Exception:
                pass

        first_seen_dt = None
        if d.get("first_seen"):
            try:
                first_seen_dt = datetime.fromisoformat(d["first_seen"])
            except Exception:
                pass

        response.append(
            DroneResponse(
                id=d["id"],
                name=d["name"],
                model=d.get("model", "UAV"),
                hardware_type=d.get("hardware_type", "Pixhawk"),
                first_seen=first_seen_dt,
                last_seen=last_seen_dt,
                is_active=bool(d.get("is_active", 1)),
                status=status_str,
            )
        )

    # Include any drones currently in state cache that might not yet be committed to DB
    for drone_id, st in state_manager.get_all_states().items():
        if drone_id not in seen_ids:
            response.append(
                DroneResponse(
                    id=drone_id,
                    name=f"Vehicle {drone_id}",
                    model="UAV",
                    hardware_type="Pixhawk",
                    first_seen=st.last_seen,
                    last_seen=st.last_seen,
                    is_active=True,
                    status=st.status,
                )
            )

    return response


@router.get("/drones/{drone_id}/state", response_model=DroneConsolidatedState)
async def get_drone_state(drone_id: str):
    """Retrieves the latest consolidated real-time state for a specific drone."""
    state = state_manager.get_state(drone_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Drone '{drone_id}' not found or no telemetry received yet")
    return state


# ==============================================================================
# Historical Telemetry Queries
# ==============================================================================

@router.get("/drones/{drone_id}/history", response_model=TelemetryHistoryResponse)
async def get_drone_history(
    drone_id: str,
    msg_type: Optional[str] = Query(None, description="Filter by message type (e.g., ATTITUDE, GLOBAL_POSITION_INT)"),
    start_time: Optional[datetime] = Query(None, description="Start timestamp (ISO 8601)"),
    end_time: Optional[datetime] = Query(None, description="End timestamp (ISO 8601)"),
    limit: int = Query(500, ge=1, le=5000, description="Max rows to return"),
    downsample_step: int = Query(1, ge=1, le=100, description="Downsample step (e.g. 5 = take every 5th record)"),
):
    """Queries time-series telemetry history with timestamp range and message filters."""
    items = await db_manager.get_drone_history(
        drone_id=drone_id,
        msg_type=msg_type,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        downsample_step=downsample_step,
    )
    return TelemetryHistoryResponse(
        drone_id=drone_id,
        total_records=len(items),
        items=items,
    )


@router.get("/drones/{drone_id}/stats", response_model=FlightStatsResponse)
async def get_drone_stats(drone_id: str):
    """Computes summary metrics for a drone (max speed, max altitude, battery range, duration)."""
    return await db_manager.get_drone_stats(drone_id)


# ==============================================================================
# Live Web Dashboard WebSocket Streams
# ==============================================================================

@router.websocket("/telemetry/ws/live")
async def live_telemetry_stream_all(websocket: WebSocket):
    """Live stream for all drones."""
    await live_broadcaster.connect(websocket, drone_id=None)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await live_broadcaster.disconnect(websocket)
    except Exception:
        await live_broadcaster.disconnect(websocket)


@router.websocket("/telemetry/ws/live/{drone_id}")
async def live_telemetry_stream_single(websocket: WebSocket, drone_id: str):
    """Live stream for a specific drone."""
    await live_broadcaster.connect(websocket, drone_id=drone_id)
    try:
        # Immediately send current state if available
        state = state_manager.get_state(drone_id)
        if state:
            await websocket.send_json({
                "type": "INITIAL_STATE",
                "drone_id": drone_id,
                "state": state.model_dump(mode="json"),
            })

        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await live_broadcaster.disconnect(websocket)
    except Exception:
        await live_broadcaster.disconnect(websocket)
