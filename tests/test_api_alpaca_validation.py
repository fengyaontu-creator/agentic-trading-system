import importlib
import os
import sys
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _load_modules(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("DB_ENCRYPTION_KEY", "R1QqOX1D0r7e6T7x3t4w1L4RKe0K1cW8mWG4Pzv9hQ8=")

    import database
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "api_validation.db"))
    importlib.reload(database)
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "api_validation.db"))
    database.init_db()

    import api
    importlib.reload(api)
    monkeypatch.setattr(api.db, "DB_PATH", str(tmp_path / "api_validation.db"))
    api.db.init_db()
    return api, database


def _auth_headers(client: TestClient, username: str = "alice", password: str = "pw"):
    resp = client.post("/api/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 200
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_update_alpaca_rejects_invalid_credentials(tmp_path, monkeypatch):
    api, database = _load_modules(tmp_path, monkeypatch)
    client = TestClient(api.app)
    headers = _auth_headers(client)

    with patch.object(api, "_alpaca_status_for_credentials", return_value=api.AlpacaStatus(
        saved=True,
        valid=False,
        detail="unauthorized",
    )):
        resp = client.put(
            "/api/settings/alpaca",
            json={"api_key": "bad-key", "api_secret": "bad-secret"},
            headers=headers,
        )

    assert resp.status_code == 400
    assert "validation failed" in resp.json()["detail"].lower()
    assert database.get_alpaca_credentials("alice") is None


def test_settings_reports_invalid_saved_credentials(tmp_path, monkeypatch):
    api, database = _load_modules(tmp_path, monkeypatch)
    client = TestClient(api.app)
    headers = _auth_headers(client)
    database.save_alpaca_credentials("alice", "saved-key", "saved-secret")

    with patch.object(api, "_alpaca_status_for_credentials", return_value=api.AlpacaStatus(
        saved=True,
        valid=False,
        detail="unauthorized",
    )):
        resp = client.get("/api/settings", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["has_alpaca"] is True
    assert body["alpaca"] == {
        "saved": True,
        "valid": False,
        "detail": "unauthorized",
    }


def test_update_alpaca_saves_and_returns_verified_status(tmp_path, monkeypatch):
    api, database = _load_modules(tmp_path, monkeypatch)
    client = TestClient(api.app)
    headers = _auth_headers(client)

    with patch.object(api, "_alpaca_status_for_credentials", return_value=api.AlpacaStatus(
        saved=True,
        valid=True,
        detail="Connected to Alpaca paper account (ACTIVE).",
    )):
        resp = client.put(
            "/api/settings/alpaca",
            json={"api_key": "good-key", "api_secret": "good-secret"},
            headers=headers,
        )

    assert resp.status_code == 200
    assert resp.json()["alpaca"]["valid"] is True
    assert database.get_alpaca_credentials("alice") == {
        "api_key": "good-key",
        "api_secret": "good-secret",
    }
