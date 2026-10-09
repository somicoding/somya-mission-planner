import asyncio
import json
import logging
from typing import Any, Dict, Optional
import websockets
from collector.config import config

logger = logging.getLogger("telemetry.collector.sender")


class WebSocketSender:
    """Manages high-throughput, low-latency WebSocket telemetry transmission

    to the backend with exponential backoff and a bounded memory queue.
    """

    def __init__(self, ws_url: Optional[str] = None, api_key: Optional[str] = None):
        self.ws_url = ws_url or config.BACKEND_WS_URL
        self.api_key = api_key or config.API_KEY
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=config.QUEUE_MAX_SIZE)
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        self._running = False
        self._send_task: Optional[asyncio.Task] = None
        self._connect_task: Optional[asyncio.Task] = None
        self.stats = {
            "queued": 0,
            "sent": 0,
            "dropped": 0,
            "reconnects": 0,
        }

    async def enqueue(self, payload: Dict[str, Any]):
        """Pushes parsed telemetry payload to queue. Drops oldest if full."""
        self.stats["queued"] += 1
        if self.queue.full():
            try:
                # Discard oldest to keep fresh telemetry
                _ = self.queue.get_nowait()
                self.stats["dropped"] += 1
            except asyncio.QueueEmpty:
                pass
        await self.queue.put(payload)

    async def start(self):
        """Starts connection and dispatch loop."""
        self._running = True
        self._send_task = asyncio.create_task(self._dispatch_loop())

    async def stop(self):
        """Gracefully terminates sender."""
        self._running = False
        if self.ws:
            await self.ws.close()
        if self._send_task:
            self._send_task.cancel()
            try:
                await self._send_task
            except asyncio.CancelledError:
                pass

    async def _dispatch_loop(self):
        """Main connection and dispatch supervisor with exponential backoff."""
        delay = config.WS_RECONNECT_MIN_DELAY

        while self._running:
            url_with_auth = f"{self.ws_url}?drone_id={config.DRONE_ID}&token={self.api_key}"
            try:
                logger.info("Connecting to backend WebSocket at %s...", self.ws_url)
                async with websockets.connect(
                    url_with_auth,
                    ping_interval=10,
                    ping_timeout=10,
                    max_size=10 * 1024 * 1024,
                ) as ws:
                    self.ws = ws
                    self.is_connected = True
                    delay = config.WS_RECONNECT_MIN_DELAY  # Reset backoff on successful connect
                    logger.info("Connected to backend ingestion endpoint.")

                    # Drain queue and stream messages
                    while self._running:
                        # Wait for first item
                        item = await self.queue.get()
                        batch = [item]

                        # Opportunistically drain up to 25 items if queued during reconnect
                        while not self.queue.empty() and len(batch) < 25:
                            try:
                                batch.append(self.queue.get_nowait())
                            except asyncio.QueueEmpty:
                                break

                        # Send single item or batch array
                        if len(batch) == 1:
                            await ws.send(json.dumps(batch[0]))
                            self.stats["sent"] += 1
                        else:
                            await ws.send(json.dumps({"batch": batch}))
                            self.stats["sent"] += len(batch)

            except (websockets.exceptions.ConnectionClosed, OSError, Exception) as e:
                self.is_connected = False
                self.ws = None
                self.stats["reconnects"] += 1
                if not self._running:
                    break

                logger.warning(
                    "WebSocket disconnected (%s). Reconnecting in %.1fs (Queued items: %d)...",
                    e,
                    delay,
                    self.queue.qsize(),
                )
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, config.WS_RECONNECT_MAX_DELAY)
