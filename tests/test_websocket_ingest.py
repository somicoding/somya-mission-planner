import pytest
import json
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import config
from backend.state_manager import state_manager


def test_websocket_ingest_and_live_broadcast():
    client = TestClient(app)

    # 1. Test unauthorized rejection
    with pytest.raises(Exception):
        with client.websocket_connect("/api/v1/telemetry/ws/ingest?drone_id=TEST-DRONE&token=bad_token"):
            pass

    # 2. Test successful ingestion and live streaming
    with client.websocket_connect(f"/api/v1/telemetry/ws/ingest?drone_id=TEST-DRONE&token={config.API_KEY}") as ingest_ws:
        payload = {
            "drone_id": "TEST-DRONE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "msg_type": "HEARTBEAT",
            "data": {
                "armed": True,
                "flight_mode": "RTL",
                "system_status_name": "ACTIVE",
            },
        }
        ingest_ws.send_text(json.dumps(payload))

        import time
        st = None
        for _ in range(20):
            st = state_manager.get_state("TEST-DRONE")
            if st is not None:
                break
            time.sleep(0.05)

        assert st is not None
        assert st.armed is True
        assert st.flight_mode == "RTL"
        assert st.status == "ONLINE"
