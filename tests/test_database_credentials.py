"""
Regression tests for Alpaca credential persistence semantics.
"""

import os
import sys
import importlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_remove_alpaca_credentials_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test_trading.db"))
    monkeypatch.setenv("DB_ENCRYPTION_KEY", "R1QqOX1D0r7e6T7x3t4w1L4RKe0K1cW8mWG4Pzv9hQ8=")

    import database
    importlib.reload(database)

    database.init_db()
    database.create_user("u1", "user1", "pw")

    database.save_alpaca_credentials("u1", "key123", "secret123")
    assert database.get_alpaca_credentials("u1") == {
        "api_key": "key123",
        "api_secret": "secret123",
    }

    database.save_alpaca_credentials("u1", "", "")
    assert database.get_alpaca_credentials("u1") is None
