import pytest
from datetime import datetime, timezone
import httpx
from backend.main import app
from backend.database import init_db
from backend.state_manager import state_manager
from backend.config import config


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.anyio
async def test_health_check_endpoint():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] in ("ok", "degraded")
        assert "database" in data
        assert "active_drones_count" in data


@pytest.mark.anyio
async def test_telemetry_batch_and_state_query():
    drone_id = "DRONE-UNIT-TEST-1"
    now_iso = datetime.now(timezone.utc).isoformat()

    payload = {
        "batch": [
            {
                "drone_id": drone_id,
                "timestamp": now_iso,
                "msg_type": "HEARTBEAT",
                "data": {
                    "armed": True,
                    "flight_mode": "LOITER",
                    "system_status_name": "ACTIVE",
                },
            },
            {
                "drone_id": drone_id,
                "timestamp": now_iso,
                "msg_type": "GLOBAL_POSITION_INT",
                "data": {
                    "lat": 37.7749,
                    "lon": -122.4194,
                    "alt_msl": 50.0,
                    "relative_alt": 25.0,
                    "heading": 120.0,
                },
            },
            {
                "drone_id": drone_id,
                "timestamp": now_iso,
                "msg_type": "VFR_HUD",
                "data": {
                    "airspeed": 12.5,
                    "groundspeed": 12.1,
                    "heading": 120,
                    "throttle": 55,
                    "alt": 50.0,
                    "climb": 0.5,
                },
            },
        ]
    }

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # Ingest batch
        ingest_res = await client.post(
            f"/api/v1/telemetry/batch?token={config.API_KEY}",
            json=payload,
        )
        assert ingest_res.status_code == 202
        assert ingest_res.json()["count"] == 3

        # Query state
        state_res = await client.get(f"/api/v1/drones/{drone_id}/state")
        assert state_res.status_code == 200
        state = state_res.json()
        assert state["drone_id"] == drone_id
        assert state["armed"] is True
        assert state["flight_mode"] == "LOITER"
        assert state["lat"] == 37.7749
        assert state["lon"] == -122.4194
        assert state["relative_alt"] == 25.0
        assert state["groundspeed"] == 12.1

        # Query drones list
        drones_res = await client.get("/api/v1/drones")
        assert drones_res.status_code == 200
        drones = drones_res.json()
        assert any(d["id"] == drone_id for d in drones)

        # Query stats
        stats_res = await client.get(f"/api/v1/drones/{drone_id}/stats")
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert stats["drone_id"] == drone_id
