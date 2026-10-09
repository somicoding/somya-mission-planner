import pytest
import asyncio
from datetime import datetime, timezone
from backend.models import TelemetryPayload
from backend.state_manager import DroneStateManager


@pytest.mark.anyio
async def test_state_manager_multi_drone_updates():
    sm = DroneStateManager()

    # Update Drone 1
    p1 = TelemetryPayload(
        drone_id="DRONE-01",
        timestamp=datetime.now(timezone.utc),
        msg_type="HEARTBEAT",
        data={"armed": True, "flight_mode": "AUTO", "system_status_name": "ACTIVE"},
    )
    s1 = await sm.update_state(p1)
    assert s1.drone_id == "DRONE-01"
    assert s1.armed is True
    assert s1.flight_mode == "AUTO"
    assert s1.status == "ONLINE"

    # Update Drone 2
    p2 = TelemetryPayload(
        drone_id="DRONE-02",
        timestamp=datetime.now(timezone.utc),
        msg_type="GLOBAL_POSITION_INT",
        data={"lat": 12.9716, "lon": 77.5946, "alt_msl": 920.0, "relative_alt": 15.0, "heading": 180.0},
    )
    s2 = await sm.update_state(p2)
    assert s2.drone_id == "DRONE-02"
    assert s2.lat == 12.9716
    assert s2.relative_alt == 15.0

    # Verify isolation
    assert sm.get_state("DRONE-01").flight_mode == "AUTO"
    assert sm.get_state("DRONE-02").flight_mode == "UNKNOWN"


@pytest.mark.anyio
async def test_attitude_and_battery_state_updates():
    sm = DroneStateManager()

    att_payload = TelemetryPayload(
        drone_id="DRONE-01",
        timestamp=datetime.now(timezone.utc),
        msg_type="ATTITUDE",
        data={"roll_deg": 12.5, "pitch_deg": -3.2, "yaw_deg": 270.0},
    )
    st = await sm.update_state(att_payload)
    assert st.roll_deg == 12.5
    assert st.pitch_deg == -3.2
    assert st.yaw_deg == 270.0

    bat_payload = TelemetryPayload(
        drone_id="DRONE-01",
        timestamp=datetime.now(timezone.utc),
        msg_type="SYS_STATUS",
        data={"voltage_battery": 16.2, "current_battery": 10.5, "battery_remaining": 78},
    )
    st = await sm.update_state(bat_payload)
    assert st.voltage == 16.2
    assert st.current == 10.5
    assert st.battery_pct == 78
