import asyncio
import logging
import signal
import sys
import time
from typing import Optional
from collector.config import config
from collector.connection import MavlinkConnection
from collector.parser import MavlinkTelemetryParser
from collector.sender import WebSocketSender

# Setup logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("telemetry.collector")


class TelemetryCollectorService:
    def __init__(self):
        self.connection = MavlinkConnection()
        self.parser = MavlinkTelemetryParser(drone_id=config.DRONE_ID)
        self.sender = WebSocketSender()
        self.running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stats = {"messages_parsed": 0, "messages_ignored": 0}

    async def run(self):
        self.running = True
        self._loop = asyncio.get_running_loop()

        logger.info("==================================================")
        logger.info("Starting Drone Telemetry Collector Service")
        logger.info("Drone ID: %s", config.DRONE_ID)
        logger.info("FC Connection: %s (baud: %s)", config.FC_CONNECTION_STRING, config.FC_BAUD_RATE)
        logger.info("Backend WS: %s", config.BACKEND_WS_URL)
        logger.info("==================================================")

        # Start WebSocket sender worker
        await self.sender.start()

        # Start GCS Heartbeat sender loop
        gcs_heartbeat_task = asyncio.create_task(self._gcs_heartbeat_loop())
        # Start Telemetry reading loop
        mavlink_reader_task = asyncio.create_task(self._mavlink_ingestion_loop())
        # Start Periodic status report loop
        stats_task = asyncio.create_task(self._stats_reporter_loop())

        try:
            await asyncio.gather(gcs_heartbeat_task, mavlink_reader_task, stats_task)
        except asyncio.CancelledError:
            logger.info("Collector service received cancellation.")
        finally:
            await self.shutdown()

    async def _gcs_heartbeat_loop(self):
        """Sends GCS heartbeat to vehicle every second to keep stream alive."""
        while self.running:
            try:
                if self.connection.is_connected:
                    self.connection.send_gcs_heartbeat()
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("Heartbeat loop error: %s", e)
                await asyncio.sleep(1.0)

    async def _mavlink_ingestion_loop(self):
        """Monitors and reads MAVLink packets from flight controller."""
        while self.running:
            if not self.connection.is_connected:
                logger.info("Attempting connection to flight controller...")
                connected = await self._loop.run_in_executor(None, self.connection.connect)
                if not connected:
                    logger.warning("Retrying FC connection in 3 seconds...")
                    await asyncio.sleep(3.0)
                    continue

            # Read messages in non-blocking thread executor
            msg = await self._loop.run_in_executor(None, self.connection.read_message, 0.2)
            if msg is None:
                await asyncio.sleep(0.01)
                continue

            try:
                parsed = self.parser.parse_message(msg)
                if parsed:
                    self._stats["messages_parsed"] += 1
                    await self.sender.enqueue(parsed)
                else:
                    self._stats["messages_ignored"] += 1
            except Exception as e:
                logger.error("Error parsing message %s: %s", getattr(msg, "get_type", lambda: "UNKNOWN")(), e)

    async def _stats_reporter_loop(self):
        """Logs periodic telemetry throughput."""
        while self.running:
            await asyncio.sleep(10.0)
            logger.info(
                "[Status Report] Parsed: %d | Ignored: %d | Sent: %d | Queue: %d | Dropped: %d | FC: %s | WS: %s",
                self._stats["messages_parsed"],
                self._stats["messages_ignored"],
                self.sender.stats["sent"],
                self.sender.queue.qsize(),
                self.sender.stats["dropped"],
                "CONNECTED" if self.connection.is_connected else "DISCONNECTED",
                "CONNECTED" if self.sender.is_connected else "DISCONNECTED",
            )

    async def shutdown(self):
        logger.info("Shutting down Telemetry Collector Service...")
        self.running = False
        await self.sender.stop()
        self.connection.close()
        logger.info("Collector shutdown complete.")


def handle_exit(signum, frame):
    logger.info("Signal %s received. Exiting...", signum)
    sys.exit(0)


def main():
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    collector = TelemetryCollectorService()
    try:
        asyncio.run(collector.run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Service interrupted by user.")


if __name__ == "__main__":
    main()
