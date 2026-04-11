import importlib
import os
import sys
from datetime import datetime, timezone

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _load_modules(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("DB_ENCRYPTION_KEY", "R1QqOX1D0r7e6T7x3t4w1L4RKe0K1cW8mWG4Pzv9hQ8=")

    import database
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "api_control_mode.db"))
    importlib.reload(database)
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "api_control_mode.db"))
    database.init_db()

    import api
    importlib.reload(api)
    monkeypatch.setattr(api.db, "DB_PATH", str(tmp_path / "api_control_mode.db"))
    api.db.init_db()
    return api, database


def _auth_headers(client: TestClient, username: str = "alice", password: str = "pw"):
    resp = client.post("/api/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 200
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_control_mode_round_trip(tmp_path, monkeypatch):
    api, database = _load_modules(tmp_path, monkeypatch)
    client = TestClient(api.app)
    headers = _auth_headers(client)

    get_resp = client.get("/api/control_mode", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json() == {"mode": None}

    put_resp = client.put("/api/control_mode", json={"mode": "manual"}, headers=headers)
    assert put_resp.status_code == 200
    assert put_resp.json()["mode"] == "manual"
    assert database.get_control_mode("alice") == "manual"

    settings_resp = client.get("/api/settings", headers=headers)
    assert settings_resp.status_code == 200
    assert settings_resp.json()["control_mode"] == "manual"


def test_signal_approval_endpoint_updates_today_signal(tmp_path, monkeypatch):
    api, database = _load_modules(tmp_path, monkeypatch)
    client = TestClient(api.app)
    headers = _auth_headers(client)
    database.set_control_mode("alice", "manual")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    database.save_signal("alice", "AAPL", today, "BUY", 0.7, approved=0)

    resp = client.put("/api/signals/AAPL/approval", json={"approved": True}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["approved"] is True

    signals = database.get_signals("alice", date=today)
    assert len(signals) == 1
    assert signals[0]["approved"] == 1


def test_position_close_approval_endpoint_updates_position(tmp_path, monkeypatch):
    api, database = _load_modules(tmp_path, monkeypatch)
    client = TestClient(api.app)
    headers = _auth_headers(client)
    database.set_control_mode("alice", "auto")
    database.save_position("alice", "AAPL", 5, 100.0, 101.0, datetime.now(timezone.utc).isoformat())

    resp = client.put("/api/positions/AAPL/close_approval", json={"approved": False}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["approved"] is False

    positions = database.load_positions("alice")
    assert len(positions) == 1
    assert positions[0]["close_approved"] == 0
