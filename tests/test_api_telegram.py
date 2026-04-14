import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _load_modules(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret")
    monkeypatch.setenv("DB_ENCRYPTION_KEY", "R1QqOX1D0r7e6T7x3t4w1L4RKe0K1cW8mWG4Pzv9hQ8=")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:test-token")

    import database
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "api_telegram.db"))
    importlib.reload(database)
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "api_telegram.db"))
    database.init_db()

    import telegram_service
    importlib.reload(telegram_service)

    import api
    importlib.reload(api)
    monkeypatch.setattr(api.db, "DB_PATH", str(tmp_path / "api_telegram.db"))
    api.db.init_db()
    return api, database


def _auth_headers(client: TestClient, username: str = "alice", password: str = "pw"):
    resp = client.post("/api/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 200
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_telegram_bind_code_returns_pending_status(tmp_path, monkeypatch):
    api, database = _load_modules(tmp_path, monkeypatch)
    client = TestClient(api.app)
    headers = _auth_headers(client)

    with patch.object(api.telegram_service, "get_bot_username", return_value="tradebot"):
        resp = client.post("/api/settings/telegram/bind", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert body["telegram"]["configured"] is True
    assert body["telegram"]["connected"] is False
    assert body["telegram"]["bot_username"] == "tradebot"
    assert len(body["telegram"]["pending_code"]) == 8
    assert database.get_telegram_bind_code("alice")["code"] == body["telegram"]["pending_code"]


def test_verify_telegram_bind_links_chat(tmp_path, monkeypatch):
    api, database = _load_modules(tmp_path, monkeypatch)
    client = TestClient(api.app)
    headers = _auth_headers(client)

    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    database.save_telegram_bind_code("alice", "ABCD2345", expires_at)

    with patch.object(api.telegram_service, "get_bot_username", return_value="tradebot"), \
         patch.object(api.telegram_service, "send_binding_success_message", return_value={"ok": True}), \
         patch.object(api.telegram_service, "_find_chat_for_code", return_value={
             "chat_id": "987654321",
             "chat_username": "alice_tg",
             "chat_first_name": "Alice",
         }):
        resp = client.post("/api/settings/telegram/verify", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "linked"
    assert body["detail"] == "Telegram connected. A confirmation message was sent to your chat."
    assert body["telegram"]["connected"] is True
    assert body["telegram"]["chat_username"] == "alice_tg"
    assert database.get_telegram_binding("alice") == {
        "chat_id": "987654321",
        "chat_username": "alice_tg",
        "chat_first_name": "Alice",
    }


def test_verify_telegram_bind_returns_pending_when_message_missing(tmp_path, monkeypatch):
    api, database = _load_modules(tmp_path, monkeypatch)
    client = TestClient(api.app)
    headers = _auth_headers(client)

    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    database.save_telegram_bind_code("alice", "ABCD2345", expires_at)

    with patch.object(api.telegram_service, "get_bot_username", return_value="tradebot"), \
         patch.object(api.telegram_service, "_find_chat_for_code", return_value=None):
        resp = client.post("/api/settings/telegram/verify", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
    assert "No matching Telegram /start code found yet." in body["detail"]
    assert body["telegram"]["pending_code"] == "ABCD2345"
    assert database.get_telegram_binding("alice") is None


def test_send_telegram_test_message(tmp_path, monkeypatch):
    api, database = _load_modules(tmp_path, monkeypatch)
    client = TestClient(api.app)
    headers = _auth_headers(client)
    database.save_telegram_binding("alice", "987654321", "alice_tg", "Alice")

    with patch.object(api.telegram_service, "get_bot_username", return_value="tradebot"), \
         patch.object(api.telegram_service, "send_test_message", return_value={"ok": True}):
        resp = client.post("/api/settings/telegram/test", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "sent"
    assert body["detail"] == "Test message sent to your Telegram chat."
    assert body["telegram"]["connected"] is True
    assert body["telegram"]["chat_username"] == "alice_tg"


def test_app_url_normalizes_bare_host(tmp_path, monkeypatch):
    _load_modules(tmp_path, monkeypatch)

    import telegram_service

    monkeypatch.setenv("APP_URL", "5.223.57.12")
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)

    assert telegram_service._app_url() == "http://5.223.57.12"


def test_app_url_keeps_full_url(tmp_path, monkeypatch):
    _load_modules(tmp_path, monkeypatch)

    import telegram_service

    monkeypatch.setenv("APP_URL", "https://app.example.com")
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)

    assert telegram_service._app_url() == "https://app.example.com"
