import pytest
import math
from collector.parser import MavlinkTelemetryParser


class MockMavMessage:
    def __init__(self, msg_type: str, **kwargs):
        self._msg_type = msg_type
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get_type(self):
        return self._msg_type


def test_heartbeat_parsing():
    parser = MavlinkTelemetryParser(drone_id="TEST-UAV")
    # base_mode: 128 (MAV_MODE_FLAG_SAFETY_ARMED)
    msg = MockMavMessage(
        "HEARTBEAT",
        custom_mode=4,  # GUIDED
        base_mode=128,
        system_status=4,  # ACTIVE
        autopilot=3,      # ARDUPILOTMEGA
        type=2,           # QUADROTOR
        mavlink_version=2,
    )
    result = parser.parse_message(msg)
    assert result is not None
    assert result["drone_id"] == "TEST-UAV"
    assert result["msg_type"] == "HEARTBEAT"
    assert result["data"]["armed"] is True
    assert result["data"]["flight_mode"] == "GUIDED"
    assert result["data"]["system_status_name"] == "ACTIVE"


def test_global_position_int_parsing():
    parser = MavlinkTelemetryParser(drone_id="TEST-UAV")
    msg = MockMavMessage(
        "GLOBAL_POSITION_INT",
        lat=377749290,
        lon=-1224194160,
        alt=55000,
        relative_alt=35000,
        vx=1400,
        vy=-200,
        vz=-50,
        hdg=9000,
    )
    result = parser.parse_message(msg)
    assert result is not None
    data = result["data"]
    assert pytest.approx(data["lat"], 0.00001) == 37.774929
    assert pytest.approx(data["lon"], 0.00001) == -122.419416
    assert data["alt_msl"] == 55.0
    assert data["relative_alt"] == 35.0
    assert data["vx"] == 14.0
    assert data["heading"] == 90.0


def test_attitude_parsing():
    parser = MavlinkTelemetryParser(drone_id="TEST-UAV")
    msg = MockMavMessage(
        "ATTITUDE",
        roll=0.174533,   # ~10 deg
        pitch=-0.087266, # ~-5 deg
        yaw=1.570796,    # ~90 deg
        rollspeed=0.01,
        pitchspeed=0.02,
        yawspeed=0.15,
    )
    result = parser.parse_message(msg)
    assert result is not None
    data = result["data"]
    assert pytest.approx(data["roll_deg"], 0.1) == 10.0
    assert pytest.approx(data["pitch_deg"], 0.1) == -5.0
    assert pytest.approx(data["yaw_deg"], 0.1) == 90.0


def test_vfr_hud_parsing():
    parser = MavlinkTelemetryParser(drone_id="TEST-UAV")
    msg = MockMavMessage(
        "VFR_HUD",
        airspeed=16.2,
        groundspeed=15.8,
        heading=180,
        throttle=65,
        alt=42.5,
        climb=1.2,
    )
    result = parser.parse_message(msg)
    assert result is not None
    data = result["data"]
    assert data["airspeed"] == 16.2
    assert data["groundspeed"] == 15.8
    assert data["heading"] == 180
    assert data["throttle"] == 65
    assert data["climb"] == 1.2


def test_sys_status_and_battery():
    parser = MavlinkTelemetryParser(drone_id="TEST-UAV")
    msg = MockMavMessage(
        "SYS_STATUS",
        voltage_battery=15800,  # 15.8 V
        current_battery=1250,   # 12.5 A
        battery_remaining=84,
        drop_rate_comm=15,
        errors_comm=0,
    )
    result = parser.parse_message(msg)
    assert result is not None
    data = result["data"]
    assert data["voltage_battery"] == 15.8
    assert data["current_battery"] == 12.5
    assert data["battery_remaining"] == 84


def test_battery_status_cells():
    parser = MavlinkTelemetryParser(drone_id="TEST-UAV")
    msg = MockMavMessage(
        "BATTERY_STATUS",
        id=0,
        battery_function=1,
        type=1,
        temperature=2750,
        voltages=[4150, 4140, 4160, 4150, 65535, 65535],
        current_battery=1420,
        current_consumed=850,
        energy_consumed=12000,
        battery_remaining=88,
    )
    result = parser.parse_message(msg)
    assert result is not None
    data = result["data"]
    assert data["temperature_c"] == 27.5
    assert data["cell_voltages"] == [4.15, 4.14, 4.16, 4.15]
    assert pytest.approx(data["total_voltage"], 0.01) == 16.60


def test_unsupported_message_returns_none():
    parser = MavlinkTelemetryParser(drone_id="TEST-UAV")
    msg = MockMavMessage("PARAM_VALUE", param_id="ARMING_CHECK", param_value=1.0)
    assert parser.parse_message(msg) is None
