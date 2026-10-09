import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
else:
    load_dotenv()

class BackendConfig:
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
    API_KEY: str = os.getenv("API_KEY", "drone_telemetry_secure_token_2026")
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./telemetry.db")
    
    # Heartbeat timeout (seconds after which drone marked OFFLINE)
    HEARTBEAT_TIMEOUT_SEC: float = float(os.getenv("HEARTBEAT_TIMEOUT_SEC", "5.0"))
    
    # DB Ingestion Worker
    DB_BATCH_SIZE: int = int(os.getenv("DB_BATCH_SIZE", "50"))
    DB_FLUSH_INTERVAL_SEC: float = float(os.getenv("DB_FLUSH_INTERVAL_SEC", "0.2"))

config = BackendConfig()
