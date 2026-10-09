import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root or current dir
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

class CollectorConfig:
    DRONE_ID: str = os.getenv("DRONE_ID", "DRONE-ALPHA-01")
    COLLECTOR_NAME: str = os.getenv("COLLECTOR_NAME", "Apex Scout Quad")
    
    # Flight Controller connection (serial port / UDP / TCP)
    FC_CONNECTION_STRING: str = os.getenv("FC_CONNECTION_STRING", "udpin:0.0.0.0:14550")
    FC_BAUD_RATE: int = int(os.getenv("FC_BAUD_RATE", "57600"))
    
    # Backend WebSocket URL
    BACKEND_WS_URL: str = os.getenv("BACKEND_WS_URL", "ws://127.0.0.1:8000/api/v1/telemetry/ws/ingest")
    API_KEY: str = os.getenv("API_KEY", "drone_telemetry_secure_token_2026")
    
    # Stream request rates (Hz)
    STREAM_RATE_POSITION_HZ: int = int(os.getenv("STREAM_RATE_POSITION_HZ", "10"))
    STREAM_RATE_ATTITUDE_HZ: int = int(os.getenv("STREAM_RATE_ATTITUDE_HZ", "10"))
    STREAM_RATE_VFR_HZ: int = int(os.getenv("STREAM_RATE_VFR_HZ", "5"))
    STREAM_RATE_STATUS_HZ: int = int(os.getenv("STREAM_RATE_STATUS_HZ", "2"))
    STREAM_RATE_RC_HZ: int = int(os.getenv("STREAM_RATE_RC_HZ", "2"))
    
    # Resilience & backoff
    WS_RECONNECT_MIN_DELAY: float = float(os.getenv("WS_RECONNECT_MIN_DELAY", "1.0"))
    WS_RECONNECT_MAX_DELAY: float = float(os.getenv("WS_RECONNECT_MAX_DELAY", "15.0"))
    QUEUE_MAX_SIZE: int = int(os.getenv("QUEUE_MAX_SIZE", "5000"))
    
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

config = CollectorConfig()
