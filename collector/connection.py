import asyncio
import logging
import time
from typing import Optional, Callable
from pymavlink import mavutil
from collector.config import config

logger = logging.getLogger("telemetry.collector.connection")


class MavlinkConnection:
    """Manages the MAVLink connection to the flight controller (Serial, UDP, TCP)

    with automatic reconnection, stream rate negotiation, and heartbeat dispatch.
    """

    def __init__(self, connection_string: Optional[str] = None, baud_rate: Optional[int] = None):
        self.connection_string = connection_string or config.FC_CONNECTION_STRING
        self.baud_rate = baud_rate or config.FC_BAUD_RATE
        self.master: Optional[mavutil.mavfile] = None
        self.is_connected = False
        self._running = False
        self.target_system = 1
        self.target_component = 1

    @staticmethod
    def parse_connection_endpoint(conn_str: str, default_baud: int) -> tuple[str, int]:
        """Normalizes and parses connection string into (device, baud_rate).
        
        Specifically prevents pymavlink from treating serial/COM port strings
        (e.g. 'serial:COM5:115200', 'COM5:115200', 'serial:COM5') or tty paths
        as UDP network sockets due to colon separators.
        """
        raw = conn_str.strip()
        baud = default_baud

        # 1. Strip 'serial:' prefix if user specified serial:COM5 or serial:/dev/ttyACM0
        if raw.lower().startswith("serial:"):
            raw = raw[7:].strip()

        # Check for known network protocol prefixes
        network_prefixes = (
            "udpin:", "udpout:", "udpbcast:", "udp:",
            "tcpin:", "tcp:", "uds:", "unix:",
            "ws:", "wss:", "wsserver:", "mcast:"
        )
        if any(raw.lower().startswith(p) for p in network_prefixes):
            return raw, baud

        # 2. Check for port:baud format on serial/COM devices
        # Examples: COM5:115200, COM3:57600, /dev/ttyUSB0:115200
        if ":" in raw:
            parts = raw.split(":")
            # If the last segment is all digits, it represents the baud rate
            if len(parts) == 2 and parts[1].isdigit():
                port = parts[0]
                baud = int(parts[1])
                return port, baud

        # 3. Plain device string: 'COM5', '/dev/ttyUSB0', etc.
        return raw, baud

    def connect(self) -> bool:
        """Attempts a connection to the flight controller."""
        try:
            device, baud = self.parse_connection_endpoint(self.connection_string, self.baud_rate)
            logger.info("Connecting to flight controller at '%s' (baud=%s)...", device, baud)
            
            # mavutil accepts baud rate directly
            self.master = mavutil.mavlink_connection(
                device,
                baud=baud,
                autoreconnect=True
            )
            
            logger.info("Connection initiated to %s. Waiting for vehicle heartbeat...", device)
            msg = self.master.wait_heartbeat(timeout=5)
            if msg:
                self.target_system = self.master.target_system
                self.target_component = self.master.target_component
                self.is_connected = True
                logger.info(
                    "Vehicle connected! System ID: %d, Component ID: %d, Autopilot: %d, Type: %d",
                    self.target_system,
                    self.target_component,
                    msg.autopilot,
                    msg.type
                )
                self.request_data_streams()
                return True
            else:
                logger.warning("No heartbeat received within 5s from %s", device)
                self.is_connected = False
                return False
        except Exception as e:
            logger.error("Failed to connect to %s: %s", self.connection_string, e)
            self.is_connected = False
            return False

    def request_data_streams(self):
        """Requests high-frequency telemetry streams from ArduPilot / PX4."""
        if not self.master:
            return

        try:
            logger.info("Negotiating stream rates with flight controller...")
            # ArduPilot standard data stream requests
            streams = [
                (mavutil.mavlink.MAV_DATA_STREAM_ALL, 4),
                (mavutil.mavlink.MAV_DATA_STREAM_RAW_SENSORS, 2),
                (mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS, config.STREAM_RATE_STATUS_HZ),
                (mavutil.mavlink.MAV_DATA_STREAM_RC_CHANNELS, config.STREAM_RATE_RC_HZ),
                (mavutil.mavlink.MAV_DATA_STREAM_POSITION, config.STREAM_RATE_POSITION_HZ),
                (mavutil.mavlink.MAV_DATA_STREAM_EXTRA1, config.STREAM_RATE_ATTITUDE_HZ),  # Attitude
                (mavutil.mavlink.MAV_DATA_STREAM_EXTRA2, config.STREAM_RATE_VFR_HZ),       # VFR_HUD
                (mavutil.mavlink.MAV_DATA_STREAM_EXTRA3, 2),
            ]
            for stream_id, rate in streams:
                self.master.mav.request_data_stream_send(
                    self.target_system,
                    self.target_component,
                    stream_id,
                    rate,
                    1  # start stream
                )

            # Modern MAVLink v2 interval commands (MAV_CMD_SET_MESSAGE_INTERVAL)
            # Intervals are in microseconds (1 / rate * 1e6)
            msg_intervals = [
                (mavutil.mavlink.MAVLINK_MSG_ID_HEARTBEAT, 1.0),
                (mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE, config.STREAM_RATE_ATTITUDE_HZ),
                (mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT, config.STREAM_RATE_POSITION_HZ),
                (mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT, 5.0),
                (mavutil.mavlink.MAVLINK_MSG_ID_VFR_HUD, config.STREAM_RATE_VFR_HZ),
                (mavutil.mavlink.MAVLINK_MSG_ID_SYS_STATUS, config.STREAM_RATE_STATUS_HZ),
                (mavutil.mavlink.MAVLINK_MSG_ID_BATTERY_STATUS, 2.0),
                (mavutil.mavlink.MAVLINK_MSG_ID_RC_CHANNELS, config.STREAM_RATE_RC_HZ),
            ]

            for msg_id, rate_hz in msg_intervals:
                interval_us = int(1e6 / rate_hz) if rate_hz > 0 else -1
                self.master.mav.command_long_send(
                    self.target_system,
                    self.target_component,
                    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL,
                    0,  # confirmation
                    msg_id,
                    interval_us,
                    0, 0, 0, 0, 0
                )
            logger.info("Stream rate negotiation complete.")
        except Exception as e:
            logger.warning("Stream rate negotiation warning: %s", e)

    def send_gcs_heartbeat(self):
        """Sends GCS heartbeat to vehicle so autopilot knows ground station is alive."""
        if not self.master:
            return
        try:
            self.master.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_GCS,
                mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                0, 0, 0
            )
        except Exception as e:
            logger.debug("Failed sending GCS heartbeat: %s", e)

    def read_message(self, timeout: float = 0.5):
        """Reads the next MAVLink message (blocking up to timeout seconds)."""
        if not self.master:
            return None
        try:
            return self.master.recv_msg()
        except Exception as e:
            logger.debug("Error reading message: %s", e)
            return None

    def close(self):
        """Closes the MAVLink connection."""
        self._running = False
        self.is_connected = False
        if self.master:
            try:
                self.master.close()
            except Exception:
                pass
            self.master = None
            logger.info("MAVLink connection closed.")
