import math
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pymavlink import mavutil

# ArduPilot Copter Flight Modes lookup table
ARDUPILOT_COPTER_MODES = {
    0: "STABILIZE",
    1: "ACRO",
    2: "ALT_HOLD",
    3: "AUTO",
    4: "GUIDED",
    5: "LOITER",
    6: "RTL",
    7: "CIRCLE",
    9: "LAND",
    11: "DRIFT",
    13: "SPORT",
    14: "FLIP",
    15: "AUTOTUNE",
    16: "POSHOLD",
    17: "BRAKE",
    18: "THROW",
    19: "AVOID_ADSB",
    20: "GUIDED_NOGPS",
    21: "SMART_RTL",
    22: "FLOWHOLD",
    23: "FOLLOW",
    24: "ZIGZAG",
    25: "SYSTEMID",
    26: "AUTOROTATE",
    27: "AUTO_RTL",
}

# GPS Fix Type lookup
GPS_FIX_TYPES = {
    0: "NO_GPS",
    1: "NO_FIX",
    2: "2D_FIX",
    3: "3D_FIX",
    4: "DGPS",
    5: "RTK_FLOAT",
    6: "RTK_FIXED",
    7: "STATIC",
    8: "PPP",
}

# MAV_STATE lookup
MAV_STATES = {
    0: "UNINIT",
    1: "BOOT",
    2: "CALIBRATING",
    3: "STANDBY",
    4: "ACTIVE",
    5: "CRITICAL",
    6: "EMERGENCY",
    7: "POWEROFF",
    8: "FLIGHT_TERMINATION",
}

# Landed state lookup
LANDED_STATES = {
    0: "UNDEFINED",
    1: "ON_GROUND",
    2: "IN_AIR",
    3: "TAKEOFF",
    4: "LANDING",
}


class MavlinkTelemetryParser:
    """Parses and normalizes raw MAVLink v1/v2 messages into unified schemas."""

    def __init__(self, drone_id: str):
        self.drone_id = drone_id

    def get_iso_timestamp(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def parse_message(self, msg: Any) -> Optional[Dict[str, Any]]:
        """Parses a MAVLink message object into a normalized dictionary."""
        if msg is None:
            return None

        msg_type = msg.get_type()
        handler = getattr(self, f"_parse_{msg_type.lower()}", None)

        if not handler:
            return None

        parsed_data = handler(msg)
        if parsed_data is None:
            return None

        return {
            "drone_id": self.drone_id,
            "timestamp": self.get_iso_timestamp(),
            "msg_type": msg_type,
            "data": parsed_data,
        }

    def _parse_heartbeat(self, msg: Any) -> Dict[str, Any]:
        # Armed flag is bit 7 (0x80) of base_mode (MAV_MODE_FLAG_SAFETY_ARMED = 128)
        is_armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)

        # Autopilot and vehicle type
        autopilot_type = mavutil.mavlink.enums["MAV_AUTOPILOT"].get(
            msg.autopilot, mavutil.mavlink.enums["MAV_AUTOPILOT"].get(msg.autopilot, None)
        )
        autopilot_str = autopilot_type.name if hasattr(autopilot_type, "name") else str(msg.autopilot)

        vehicle_type = mavutil.mavlink.enums["MAV_TYPE"].get(
            msg.type, mavutil.mavlink.enums["MAV_TYPE"].get(msg.type, None)
        )
        type_str = vehicle_type.name if hasattr(vehicle_type, "name") else str(msg.type)

        # Mode string resolution
        custom_mode_num = int(msg.custom_mode)
        flight_mode = ARDUPILOT_COPTER_MODES.get(custom_mode_num)
        if not flight_mode:
            try:
                flight_mode = mavutil.mode_string_v10(msg)
            except Exception:
                flight_mode = f"MODE_{custom_mode_num}"

        system_status_str = MAV_STATES.get(msg.system_status, f"STATE_{msg.system_status}")

        return {
            "custom_mode": custom_mode_num,
            "flight_mode": flight_mode,
            "base_mode": int(msg.base_mode),
            "armed": is_armed,
            "system_status": msg.system_status,
            "system_status_name": system_status_str,
            "mavlink_version": getattr(msg, "mavlink_version", 2),
            "autopilot": autopilot_str,
            "vehicle_type": type_str,
        }

    def _parse_global_position_int(self, msg: Any) -> Dict[str, Any]:
        return {
            "lat": msg.lat / 1e7,  # degrees
            "lon": msg.lon / 1e7,  # degrees
            "alt_msl": msg.alt / 1000.0,  # meters MSL
            "relative_alt": msg.relative_alt / 1000.0,  # meters AGL
            "vx": msg.vx / 100.0,  # m/s ground velocity X (North)
            "vy": msg.vy / 100.0,  # m/s ground velocity Y (East)
            "vz": msg.vz / 100.0,  # m/s ground velocity Z (Down)
            "heading": msg.hdg / 100.0 if msg.hdg != 65535 else 0.0,  # degrees (0..359.99)
        }

    def _parse_gps_raw_int(self, msg: Any) -> Dict[str, Any]:
        fix_type_int = int(msg.fix_type)
        return {
            "fix_type": fix_type_int,
            "fix_type_name": GPS_FIX_TYPES.get(fix_type_int, "UNKNOWN"),
            "satellites_visible": int(msg.satellites_visible),
            "lat": msg.lat / 1e7,
            "lon": msg.lon / 1e7,
            "alt": msg.alt / 1000.0,
            "eph": msg.eph / 100.0 if msg.eph != 65535 else None,  # HDOP
            "epv": msg.epv / 100.0 if msg.epv != 65535 else None,  # VDOP
            "vel": msg.vel / 100.0 if msg.vel != 65535 else None,  # ground speed in m/s
            "cog": msg.cog / 100.0 if msg.cog != 65535 else None,  # course over ground in deg
        }

    def _parse_attitude(self, msg: Any) -> Dict[str, Any]:
        roll_deg = math.degrees(msg.roll)
        pitch_deg = math.degrees(msg.pitch)
        yaw_deg = math.degrees(msg.yaw)
        if yaw_deg < 0:
            yaw_deg += 360.0

        return {
            "roll": msg.roll,  # radians (-pi..+pi)
            "pitch": msg.pitch,  # radians (-pi..+pi)
            "yaw": msg.yaw,  # radians (-pi..+pi)
            "roll_deg": round(roll_deg, 2),  # degrees
            "pitch_deg": round(pitch_deg, 2),  # degrees
            "yaw_deg": round(yaw_deg, 2),  # degrees (0..360)
            "rollspeed": msg.rollspeed,  # rad/s
            "pitchspeed": msg.pitchspeed,  # rad/s
            "yawspeed": msg.yawspeed,  # rad/s
        }

    def _parse_vfr_hud(self, msg: Any) -> Dict[str, Any]:
        return {
            "airspeed": round(msg.airspeed, 2),  # m/s
            "groundspeed": round(msg.groundspeed, 2),  # m/s
            "heading": int(msg.heading),  # degrees (0..360)
            "throttle": int(msg.throttle),  # percentage (0..100)
            "alt": round(msg.alt, 2),  # meters
            "climb": round(msg.climb, 2),  # m/s (vertical speed)
        }

    def _parse_sys_status(self, msg: Any) -> Dict[str, Any]:
        voltage_v = msg.voltage_battery / 1000.0 if msg.voltage_battery != 65535 else 0.0
        current_a = msg.current_battery / 100.0 if msg.current_battery != -1 else 0.0
        remaining_pct = msg.battery_remaining if msg.battery_remaining != -1 else None

        drop_rate = msg.drop_rate_comm / 100.0 if hasattr(msg, "drop_rate_comm") else 0.0
        errors_comm = getattr(msg, "errors_comm", 0)

        return {
            "voltage_battery": round(voltage_v, 2),  # Volts
            "current_battery": round(current_a, 2),  # Amperes
            "battery_remaining": remaining_pct,  # %
            "drop_rate_comm": round(drop_rate, 2),  # %
            "errors_comm": int(errors_comm),
            "onboard_control_sensors_present": getattr(msg, "onboard_control_sensors_present", 0),
            "onboard_control_sensors_enabled": getattr(msg, "onboard_control_sensors_enabled", 0),
            "onboard_control_sensors_health": getattr(msg, "onboard_control_sensors_health", 0),
        }

    def _parse_battery_status(self, msg: Any) -> Dict[str, Any]:
        # voltages is an array of cell voltages in millivolts (up to 10 or 14 cells)
        voltages_mv = getattr(msg, "voltages", [])
        cell_voltages = [
            round(v / 1000.0, 3) for v in voltages_mv if v not in (0, 65535)
        ]

        temp_c = None
        if hasattr(msg, "temperature") and msg.temperature != 32767:
            temp_c = round(msg.temperature / 100.0, 1)

        current_a = None
        if hasattr(msg, "current_battery") and msg.current_battery != -1:
            current_a = round(msg.current_battery / 100.0, 2)

        return {
            "id": getattr(msg, "id", 0),
            "battery_function": getattr(msg, "battery_function", 0),
            "type": getattr(msg, "type", 0),
            "temperature_c": temp_c,
            "cell_voltages": cell_voltages,
            "total_voltage": round(sum(cell_voltages), 2) if cell_voltages else None,
            "current_battery": current_a,
            "current_consumed_mah": getattr(msg, "current_consumed", 0),
            "energy_consumed_hj": getattr(msg, "energy_consumed", 0),
            "battery_remaining": msg.battery_remaining if msg.battery_remaining != -1 else None,
        }

    def _parse_rc_channels(self, msg: Any) -> Dict[str, Any]:
        # RSSI: 0..255 or percentage (255 = 100% or unspecified)
        rssi = getattr(msg, "rssi", 0)
        rssi_pct = round((rssi / 255.0) * 100) if rssi <= 255 else 0

        # Collect channel pwm values (chan1_raw .. chan18_raw)
        channels = {}
        for i in range(1, 19):
            attr = f"chan{i}_raw"
            if hasattr(msg, attr):
                val = getattr(msg, attr)
                if val != 65535 and val > 0:
                    channels[f"ch{i}"] = val

        return {
            "rssi_raw": rssi,
            "rssi_pct": rssi_pct,
            "channel_count": getattr(msg, "chancount", len(channels)),
            "channels": channels,
        }

    def _parse_nav_controller_output(self, msg: Any) -> Dict[str, Any]:
        return {
            "nav_roll": round(msg.nav_roll, 2),
            "nav_pitch": round(msg.nav_pitch, 2),
            "nav_bearing": int(msg.nav_bearing),
            "target_bearing": int(msg.target_bearing),
            "wp_dist": int(msg.wp_dist),  # meters
            "alt_error": round(msg.alt_error, 2),  # meters
            "aspd_error": round(msg.aspd_error, 2),  # m/s
            "xtrack_error": round(msg.xtrack_error, 2),  # meters
        }

    def _parse_extended_sys_state(self, msg: Any) -> Dict[str, Any]:
        landed_state_int = int(getattr(msg, "landed_state", 0))
        return {
            "vtol_state": int(getattr(msg, "vtol_state", 0)),
            "landed_state": landed_state_int,
            "landed_state_name": LANDED_STATES.get(landed_state_int, "UNDEFINED"),
        }
