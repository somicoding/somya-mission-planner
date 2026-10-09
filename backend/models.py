from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ==============================================================================
# Pydantic Schemas for Ingestion, API & Consolidated State
# ==============================================================================

class TelemetryPayload(BaseModel):
    drone_id: str = Field(..., min_length=1, max_length=64)
    timestamp: datetime
    msg_type: str = Field(..., min_length=1, max_length=32)
    data: Dict[str, Any]


class BatchTelemetryPayload(BaseModel):
    batch: List[TelemetryPayload]


class DroneResponse(BaseModel):
    id: str
    name: str
    model: str
    hardware_type: str
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    is_active: bool
    status: str = "OFFLINE"  # ONLINE, OFFLINE, ARMED, DISARMED


class DroneConsolidatedState(BaseModel):
    drone_id: str
    status: str = "OFFLINE"  # ONLINE / OFFLINE
    last_seen: Optional[datetime] = None
    
    # Flight State
    armed: bool = False
    flight_mode: str = "UNKNOWN"
    system_status: str = "STANDBY"
    landed_state: str = "UNKNOWN"
    
    # Position
    lat: Optional[float] = None
    lon: Optional[float] = None
    alt_msl: Optional[float] = None
    relative_alt: Optional[float] = None
    heading: Optional[float] = None
    
    # Attitude
    roll: Optional[float] = None
    pitch: Optional[float] = None
    yaw: Optional[float] = None
    roll_deg: Optional[float] = None
    pitch_deg: Optional[float] = None
    yaw_deg: Optional[float] = None
    
    # Dynamics (VFR HUD)
    airspeed: Optional[float] = None
    groundspeed: Optional[float] = None
    climb: Optional[float] = None
    throttle: Optional[int] = None
    
    # Battery & Power
    voltage: Optional[float] = None
    current: Optional[float] = None
    battery_pct: Optional[int] = None
    cell_voltages: Optional[List[float]] = None
    
    # GPS Health
    gps_fix_type: Optional[str] = "NO_GPS"
    satellites: Optional[int] = 0
    hdop: Optional[float] = None
    
    # RC & Link
    rc_rssi: Optional[int] = 0
    packet_rate_hz: Optional[float] = 0.0


class TelemetryHistoryItem(BaseModel):
    id: int
    drone_id: str
    timestamp: datetime
    msg_type: str
    data: Dict[str, Any]
    lat: Optional[float] = None
    lon: Optional[float] = None
    alt: Optional[float] = None
    roll: Optional[float] = None
    pitch: Optional[float] = None
    yaw: Optional[float] = None
    battery_pct: Optional[int] = None
    voltage: Optional[float] = None
    groundspeed: Optional[float] = None
    flight_mode: Optional[str] = None
    armed: Optional[bool] = None


class TelemetryHistoryResponse(BaseModel):
    drone_id: str
    total_records: int
    items: List[TelemetryHistoryItem]


class FlightStatsResponse(BaseModel):
    drone_id: str
    first_record: Optional[datetime] = None
    last_record: Optional[datetime] = None
    duration_seconds: float = 0.0
    total_points: int = 0
    max_altitude_m: float = 0.0
    max_groundspeed_mps: float = 0.0
    min_battery_pct: Optional[int] = None
    max_battery_pct: Optional[int] = None
    average_voltage: Optional[float] = None
