import asyncio
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional
from backend.config import config
from backend.models import DroneConsolidatedState, TelemetryPayload

logger = logging.getLogger("telemetry.backend.state_manager")


class DroneStateManager:
    """Maintains in-memory consolidated telemetry state per drone,

    computes packet throughput (Hz), and marks offline state on heartbeat timeout.
    """

    def __init__(self):
        self._states: Dict[str, DroneConsolidatedState] = {}
        self._packet_counts: Dict[str, int] = {}
        self._last_hz_calc: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        self._running = True
        self._monitor_task = asyncio.create_task(self._liveness_loop())

    async def stop(self):
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

    def get_or_create_state(self, drone_id: str) -> DroneConsolidatedState:
        if drone_id not in self._states:
            self._states[drone_id] = DroneConsolidatedState(
                drone_id=drone_id,
                status="OFFLINE",
                last_seen=None,
            )
            self._packet_counts[drone_id] = 0
            self._last_hz_calc[drone_id] = asyncio.get_event_loop().time()
        return self._states[drone_id]

    async def update_state(self, payload: TelemetryPayload) -> DroneConsolidatedState:
        """Updates the drone consolidated state based on incoming telemetry."""
        async with self._lock:
            state = self.get_or_create_state(payload.drone_id)
            state.last_seen = payload.timestamp
            state.status = "ONLINE"
            
            # Packet rate counter
            self._packet_counts[payload.drone_id] = self._packet_counts.get(payload.drone_id, 0) + 1
            now_sec = asyncio.get_event_loop().time()
            prev_sec = self._last_hz_calc.get(payload.drone_id, now_sec)
            elapsed = now_sec - prev_sec
            if elapsed >= 1.0:
                count = self._packet_counts[payload.drone_id]
                state.packet_rate_hz = round(count / elapsed, 1)
                self._packet_counts[payload.drone_id] = 0
                self._last_hz_calc[payload.drone_id] = now_sec

            msg_type = payload.msg_type.upper()
            data = payload.data

            if msg_type == "HEARTBEAT":
                state.armed = bool(data.get("armed", state.armed))
                state.flight_mode = data.get("flight_mode", state.flight_mode)
                state.system_status = data.get("system_status_name", state.system_status)

            elif msg_type == "GLOBAL_POSITION_INT":
                state.lat = data.get("lat", state.lat)
                state.lon = data.get("lon", state.lon)
                state.alt_msl = data.get("alt_msl", state.alt_msl)
                state.relative_alt = data.get("relative_alt", state.relative_alt)
                state.heading = data.get("heading", state.heading)

            elif msg_type == "GPS_RAW_INT":
                state.gps_fix_type = data.get("fix_type_name", state.gps_fix_type)
                state.satellites = data.get("satellites_visible", state.satellites)
                state.hdop = data.get("eph", state.hdop)
                if state.lat is None:
                    state.lat = data.get("lat")
                if state.lon is None:
                    state.lon = data.get("lon")

            elif msg_type == "ATTITUDE":
                state.roll = data.get("roll", state.roll)
                state.pitch = data.get("pitch", state.pitch)
                state.yaw = data.get("yaw", state.yaw)
                state.roll_deg = data.get("roll_deg", state.roll_deg)
                state.pitch_deg = data.get("pitch_deg", state.pitch_deg)
                state.yaw_deg = data.get("yaw_deg", state.yaw_deg)

            elif msg_type == "VFR_HUD":
                state.airspeed = data.get("airspeed", state.airspeed)
                state.groundspeed = data.get("groundspeed", state.groundspeed)
                state.climb = data.get("climb", state.climb)
                state.throttle = data.get("throttle", state.throttle)
                if state.heading is None:
                    state.heading = float(data.get("heading", 0))

            elif msg_type == "SYS_STATUS":
                state.voltage = data.get("voltage_battery", state.voltage)
                state.current = data.get("current_battery", state.current)
                if data.get("battery_remaining") is not None:
                    state.battery_pct = data.get("battery_remaining")

            elif msg_type == "BATTERY_STATUS":
                if data.get("total_voltage") is not None:
                    state.voltage = data.get("total_voltage")
                if data.get("current_battery") is not None:
                    state.current = data.get("current_battery")
                if data.get("battery_remaining") is not None:
                    state.battery_pct = data.get("battery_remaining")
                if data.get("cell_voltages"):
                    state.cell_voltages = data.get("cell_voltages")

            elif msg_type == "RC_CHANNELS":
                state.rc_rssi = data.get("rssi_pct", state.rc_rssi)

            elif msg_type == "EXTENDED_SYS_STATE":
                state.landed_state = data.get("landed_state_name", state.landed_state)

            return state

    def get_state(self, drone_id: str) -> Optional[DroneConsolidatedState]:
        return self._states.get(drone_id)

    def get_all_states(self) -> Dict[str, DroneConsolidatedState]:
        return dict(self._states)

    async def _liveness_loop(self):
        """Monitors heartbeat timeout and marks offline."""
        while self._running:
            await asyncio.sleep(1.0)
            now = datetime.now(timezone.utc)
            async with self._lock:
                for drone_id, state in self._states.items():
                    if state.last_seen:
                        diff = (now - state.last_seen).total_seconds()
                        if diff > config.HEARTBEAT_TIMEOUT_SEC:
                            if state.status != "OFFLINE":
                                logger.info(
                                    "Drone %s marked OFFLINE (no telemetry for %.1fs)", drone_id, diff
                                )
                                state.status = "OFFLINE"
                                state.packet_rate_hz = 0.0


# Global singleton instance
state_manager = DroneStateManager()
