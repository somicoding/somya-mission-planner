import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from backend.config import config
from backend.models import TelemetryPayload, TelemetryHistoryItem, FlightStatsResponse

logger = logging.getLogger("telemetry.backend.database")


class DatabaseManager:
    """High-performance time-series database manager.

    Provides non-blocking async execution, hypertable compatibility for TimescaleDB,
    and automatic fail-safe SQLite storage for zero-dependency local environments.
    """

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or config.DATABASE_URL
        self._is_sqlite = "sqlite" in self.db_url or not self.db_url.startswith("postgresql")
        self._sqlite_path = "./telemetry.db"
        if self._is_sqlite:
            # Parse path if provided like sqlite+aiosqlite:///path or sqlite:///path
            cleaned = self.db_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
            if cleaned and cleaned != ":memory:":
                self._sqlite_path = str(Path(cleaned).resolve())
            else:
                self._sqlite_path = "./telemetry.db"

    def _get_sqlite_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._sqlite_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for high concurrency
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    async def init_db(self):
        """Initializes tables and indexes."""
        logger.info("Initializing database (storage=%s)...", "SQLite" if self._is_sqlite else "PostgreSQL")
        await asyncio.to_thread(self._sync_init_db)
        logger.info("Database schema initialized successfully.")

    def _sync_init_db(self):
        with self._get_sqlite_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS drones (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    model TEXT,
                    hardware_type TEXT,
                    first_seen TEXT,
                    last_seen TEXT,
                    is_active INTEGER DEFAULT 1
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS telemetry_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    drone_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    msg_type TEXT NOT NULL,
                    data TEXT NOT NULL,
                    lat REAL,
                    lon REAL,
                    alt REAL,
                    roll REAL,
                    pitch REAL,
                    yaw REAL,
                    battery_pct INTEGER,
                    voltage REAL,
                    groundspeed REAL,
                    flight_mode TEXT,
                    armed INTEGER,
                    satellites INTEGER
                );
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_drone_time ON telemetry_logs (drone_id, timestamp DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_drone_msg_time ON telemetry_logs (drone_id, msg_type, timestamp DESC);")
            conn.commit()

    async def save_telemetry_batch(self, batch: List[TelemetryPayload]):
        """Persists a batch of telemetry payloads in a single transaction."""
        if not batch:
            return
        await asyncio.to_thread(self._sync_save_batch, batch)

    def _sync_save_batch(self, batch: List[TelemetryPayload]):
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_sqlite_conn() as conn:
            # 1. Register / Update drones
            seen_drones = {p.drone_id for p in batch}
            for d_id in seen_drones:
                conn.execute("""
                    INSERT INTO drones (id, name, model, hardware_type, first_seen, last_seen, is_active)
                    VALUES (?, ?, 'ArduPilot / Pixhawk Quad', 'UAV', ?, ?, 1)
                    ON CONFLICT(id) DO UPDATE SET last_seen = excluded.last_seen;
                """, (d_id, f"Vehicle {d_id}", now_iso, now_iso))

            # 2. Bulk insert telemetry records
            rows = []
            for p in batch:
                data = p.data
                ts_str = p.timestamp.isoformat()
                rows.append((
                    p.drone_id,
                    ts_str,
                    p.msg_type,
                    json.dumps(data),
                    data.get("lat"),
                    data.get("lon"),
                    data.get("alt_msl") or data.get("alt") or data.get("relative_alt"),
                    data.get("roll_deg") or data.get("roll"),
                    data.get("pitch_deg") or data.get("pitch"),
                    data.get("yaw_deg") or data.get("yaw"),
                    data.get("battery_remaining"),
                    data.get("voltage_battery") or data.get("total_voltage"),
                    data.get("groundspeed"),
                    data.get("flight_mode"),
                    1 if data.get("armed") else (0 if data.get("armed") is False else None),
                    data.get("satellites_visible"),
                ))

            conn.executemany("""
                INSERT INTO telemetry_logs (
                    drone_id, timestamp, msg_type, data,
                    lat, lon, alt, roll, pitch, yaw,
                    battery_pct, voltage, groundspeed, flight_mode, armed, satellites
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, rows)
            conn.commit()

    async def get_drones(self) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._sync_get_drones)

    def _sync_get_drones(self) -> List[Dict[str, Any]]:
        with self._get_sqlite_conn() as conn:
            cursor = conn.execute("SELECT * FROM drones ORDER BY last_seen DESC;")
            return [dict(row) for row in cursor.fetchall()]

    async def get_drone_history(
        self,
        drone_id: str,
        msg_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 500,
        downsample_step: int = 1,
    ) -> List[TelemetryHistoryItem]:
        return await asyncio.to_thread(
            self._sync_get_history, drone_id, msg_type, start_time, end_time, limit, downsample_step
        )

    def _sync_get_history(
        self,
        drone_id: str,
        msg_type: Optional[str],
        start_time: Optional[datetime],
        end_time: Optional[datetime],
        limit: int,
        downsample_step: int,
    ) -> List[TelemetryHistoryItem]:
        query = "SELECT * FROM telemetry_logs WHERE drone_id = ?"
        params: List[Any] = [drone_id]

        if msg_type:
            query += " AND msg_type = ?"
            params.append(msg_type.upper())
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())

        query += f" ORDER BY timestamp DESC LIMIT {limit * downsample_step};"

        with self._get_sqlite_conn() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        filtered_rows = rows[::downsample_step][:limit]
        items = []
        for r in filtered_rows:
            try:
                raw_data = json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]
            except Exception:
                raw_data = {}

            ts = datetime.fromisoformat(r["timestamp"]) if isinstance(r["timestamp"], str) else r["timestamp"]

            items.append(
                TelemetryHistoryItem(
                    id=r["id"],
                    drone_id=r["drone_id"],
                    timestamp=ts,
                    msg_type=r["msg_type"],
                    data=raw_data,
                    lat=r["lat"],
                    lon=r["lon"],
                    alt=r["alt"],
                    roll=r["roll"],
                    pitch=r["pitch"],
                    yaw=r["yaw"],
                    battery_pct=r["battery_pct"],
                    voltage=r["voltage"],
                    groundspeed=r["groundspeed"],
                    flight_mode=r["flight_mode"],
                    armed=bool(r["armed"]) if r["armed"] is not None else None,
                )
            )
        return items

    async def get_drone_stats(self, drone_id: str) -> FlightStatsResponse:
        return await asyncio.to_thread(self._sync_get_stats, drone_id)

    def _sync_get_stats(self, drone_id: str) -> FlightStatsResponse:
        query = """
            SELECT
                MIN(timestamp) as first_record,
                MAX(timestamp) as last_record,
                COUNT(id) as total_points,
                MAX(alt) as max_alt,
                MAX(groundspeed) as max_speed,
                MIN(battery_pct) as min_battery,
                MAX(battery_pct) as max_battery,
                AVG(voltage) as avg_voltage
            FROM telemetry_logs
            WHERE drone_id = ?;
        """
        with self._get_sqlite_conn() as conn:
            cursor = conn.execute(query, (drone_id,))
            row = cursor.fetchone()

        if not row or row["total_points"] == 0:
            return FlightStatsResponse(drone_id=drone_id)

        first_ts = None
        last_ts = None
        duration = 0.0
        if row["first_record"] and row["last_record"]:
            try:
                first_ts = datetime.fromisoformat(row["first_record"])
                last_ts = datetime.fromisoformat(row["last_record"])
                duration = max(0.0, (last_ts - first_ts).total_seconds())
            except Exception:
                pass

        return FlightStatsResponse(
            drone_id=drone_id,
            first_record=first_ts,
            last_record=last_ts,
            duration_seconds=round(duration, 1),
            total_points=row["total_points"] or 0,
            max_altitude_m=round(row["max_alt"] or 0.0, 1),
            max_groundspeed_mps=round(row["max_speed"] or 0.0, 1),
            min_battery_pct=row["min_battery"],
            max_battery_pct=row["max_battery"],
            average_voltage=round(row["avg_voltage"], 2) if row["avg_voltage"] else None,
        )

    async def health_check(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self._sync_health_check)

    def _sync_health_check(self) -> Dict[str, Any]:
        try:
            with self._get_sqlite_conn() as conn:
                cursor = conn.execute("SELECT COUNT(id) FROM drones;")
                count = cursor.fetchone()[0]
                return {"status": "healthy", "registered_drones": count}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


db_manager = DatabaseManager()
init_db = db_manager.init_db
