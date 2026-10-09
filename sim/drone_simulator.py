import asyncio
import math
import os
import time
import logging
from typing import Optional
from pymavlink import mavutil

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [SIM] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("drone_simulator")

# Configuration
TARGET_HOST = os.getenv("SIM_TARGET_HOST", "127.0.0.1")
TARGET_PORT = int(os.getenv("SIM_TARGET_PORT", "14550"))
SYSTEM_ID = 1
COMPONENT_ID = 1

# Simulation Origin (e.g. San Francisco or custom)
ORIGIN_LAT = 37.774929
ORIGIN_LON = -122.419416
ORIGIN_ALT = 45.0  # meters MSL


class DroneSimulator:
    """Emulates an active ArduPilot / Pixhawk flight controller,

    broadcasting MAVLink v2 telemetry packets over UDP.
    """

    def __init__(self, host: str = TARGET_HOST, port: int = TARGET_PORT):
        self.host = host
        self.port = port
        self.mav: Optional[mavutil.mavfile] = None
        self.running = False

        # Flight dynamics state
        self.time_elapsed = 0.0
        self.armed = True
        self.flight_mode = 4  # GUIDED
        self.radius = 120.0  # circle radius in meters
        self.angular_velocity = 0.15  # rad/s (~42 sec per orbit)
        self.altitude = 35.0  # meters relative
        self.battery_voltage_mv = 16600  # 4S LiPo initially 16.6V
        self.start_time = time.time()
        self.battery_remaining = 96

    def connect(self):
        # Open UDP outbound stream to collector
        dest = f"udpout:{self.host}:{self.port}"
        logger.info("Initializing simulated MAVLink stream to %s...", dest)
        self.mav = mavutil.mavlink_connection(dest, source_system=SYSTEM_ID, source_component=COMPONENT_ID)

    async def run(self):
        self.connect()
        self.running = True
        logger.info("Simulator running! Broadcasting MAVLink v2 telemetry...")

        # Tasks for various telemetry stream frequencies
        t_1hz = asyncio.create_task(self._loop_1hz())
        t_2hz = asyncio.create_task(self._loop_2hz())
        t_5hz = asyncio.create_task(self._loop_5hz())
        t_10hz = asyncio.create_task(self._loop_10hz())

        try:
            await asyncio.gather(t_1hz, t_2hz, t_5hz, t_10hz)
        except asyncio.CancelledError:
            pass

    def time_boot_ms(self) -> int:
        return int((time.time() - self.start_time) * 1000) & 0xFFFFFFFF

    async def _loop_1hz(self):
        """1 Hz: HEARTBEAT, BATTERY_STATUS"""
        while self.running:
            # HEARTBEAT
            # base_mode: 128 (armed) | 89 (custom mode enabled + stabilized)
            base_mode = mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED | mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
            self.mav.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_QUADROTOR,
                mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
                base_mode,
                self.flight_mode,  # custom_mode (4 = GUIDED)
                mavutil.mavlink.MAV_STATE_ACTIVE,
            )

            # BATTERY_STATUS (4S LiPo)
            cell_v = int(self.battery_voltage_mv / 4)
            voltages = [cell_v, cell_v - 5, cell_v + 3, cell_v - 2] + [65535] * 6
            self.mav.mav.battery_status_send(
                0,  # id
                mavutil.mavlink.MAV_BATTERY_FUNCTION_ALL,
                mavutil.mavlink.MAV_BATTERY_TYPE_LIPO,
                2800,  # 28.0 C
                voltages,
                1450,  # 14.50 A
                1200,  # 1200 mAh consumed
                18000, # energy
                self.battery_remaining,
            )

            # Drain battery slightly
            self.battery_voltage_mv = max(13800, self.battery_voltage_mv - 2)
            if int(self.time_elapsed) % 20 == 0:
                self.battery_remaining = max(10, self.battery_remaining - 1)

            await asyncio.sleep(1.0)

    async def _loop_2hz(self):
        """2 Hz: SYS_STATUS, RC_CHANNELS, NAV_CONTROLLER_OUTPUT"""
        while self.running:
            # SYS_STATUS
            self.mav.mav.sys_status_send(
                0xFFFFFFFF,  # sensors present
                0xFFFFFFFF,  # sensors enabled
                0xFFFFFFFF,  # sensors health
                250,         # 25% CPU load
                self.battery_voltage_mv,
                1450,        # 14.5A
                self.battery_remaining,
                10,          # 0.1% comms drop rate
                0, 0, 0, 0, 0
            )

            # RC_CHANNELS
            self.mav.mav.rc_channels_send(
                self.time_boot_ms(),
                8,   # chancount
                1500, 1520, 1600, 1490, 1800, 1000, 1500, 1500,
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                245  # rssi
            )

            # NAV_CONTROLLER_OUTPUT
            self.mav.mav.nav_controller_output_send(
                -12.5, # nav_roll
                3.2,   # nav_pitch
                int((self.time_elapsed * 15) % 360), # nav_bearing
                int((self.time_elapsed * 15 + 2) % 360), # target_bearing
                85,    # wp_dist
                0.2,   # alt_error
                0.1,   # aspd_error
                0.05   # xtrack_error
            )

            await asyncio.sleep(0.5)

    async def _loop_5hz(self):
        """5 Hz: GPS_RAW_INT, VFR_HUD"""
        while self.running:
            # Update position circle
            angle = self.angular_velocity * self.time_elapsed
            d_north = self.radius * math.cos(angle)
            d_east = self.radius * math.sin(angle)

            lat = ORIGIN_LAT + (d_north / 111320.0)
            lon = ORIGIN_LON + (d_east / (111320.0 * math.cos(math.radians(ORIGIN_LAT))))
            alt_m = ORIGIN_ALT + self.altitude + 2.0 * math.sin(angle * 0.5)

            # GPS_RAW_INT (time_usec is uint64)
            self.mav.mav.gps_raw_int_send(
                int(time.time() * 1e6),
                3,  # 3D Fix
                int(lat * 1e7),
                int(lon * 1e7),
                int(alt_m * 1000),
                80,   # HDOP 0.8
                120,  # VDOP 1.2
                1420, # 14.2 m/s vel
                int((math.degrees(angle) + 90) % 360 * 100), # cog
                14,   # 14 sats
            )

            # VFR_HUD
            self.mav.mav.vfr_hud_send(
                14.5,  # airspeed
                14.2,  # groundspeed
                int((math.degrees(angle) + 90) % 360), # heading
                62,    # throttle 62%
                alt_m, # alt
                0.15 * math.cos(angle * 0.5) # climb rate
            )

            await asyncio.sleep(0.2)

    async def _loop_10hz(self):
        """10 Hz: ATTITUDE, GLOBAL_POSITION_INT"""
        dt = 0.1
        while self.running:
            self.time_elapsed += dt
            angle = self.angular_velocity * self.time_elapsed

            d_north = self.radius * math.cos(angle)
            d_east = self.radius * math.sin(angle)
            lat = ORIGIN_LAT + (d_north / 111320.0)
            lon = ORIGIN_LON + (d_east / (111320.0 * math.cos(math.radians(ORIGIN_LAT))))
            alt_m = ORIGIN_ALT + self.altitude + 2.0 * math.sin(angle * 0.5)

            heading_deg = (math.degrees(angle) + 90) % 360
            v = 14.2
            roll_rad = -math.atan((v * v) / (self.radius * 9.81))
            pitch_rad = math.radians(2.5 * math.sin(angle * 0.3))
            yaw_rad = math.radians(heading_deg)

            # ATTITUDE
            self.mav.mav.attitude_send(
                self.time_boot_ms(),
                roll_rad,
                pitch_rad,
                yaw_rad,
                0.01,
                0.02,
                self.angular_velocity
            )

            # GLOBAL_POSITION_INT
            vx = int(-v * math.sin(yaw_rad) * 100)
            vy = int(v * math.cos(yaw_rad) * 100)
            vz = int(-0.15 * math.cos(angle * 0.5) * 100)

            self.mav.mav.global_position_int_send(
                self.time_boot_ms(),
                int(lat * 1e7),
                int(lon * 1e7),
                int(alt_m * 1000),
                int(self.altitude * 1000),
                vx, vy, vz,
                int(heading_deg * 100)
            )

            await asyncio.sleep(dt)


def main():
    sim = DroneSimulator()
    try:
        asyncio.run(sim.run())
    except KeyboardInterrupt:
        logger.info("Simulator stopped.")


if __name__ == "__main__":
    main()
