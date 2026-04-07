import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import broker_alpaca


@patch("broker_alpaca.submit_market_order")
@patch("broker_alpaca.submit_bracket_order")
def test_execute_trade_uses_bracket_for_new_position_with_protection(mock_bracket, mock_market):
    mock_bracket.return_value = {
        "order_id": "bracket-123",
        "status": "pending_new",
        "filled_avg_price": None,
    }

    result = broker_alpaca.execute_trade(
        symbol="AAPL",
        side="BUY",
        quantity=10,
        price=200.0,
        api_key="paper-key",
        api_secret="paper-secret",
        strategy="MARKET",
        stop_loss=180.0,
        take_profit=220.0,
        attach_protection=True,
    )

    assert result is not None
    assert result["main"]["order_id"] == "bracket-123"
    assert "stop_loss" not in result
    assert "take_profit" not in result
    mock_bracket.assert_called_once_with(
        "AAPL",
        10,
        "BUY",
        180.0,
        220.0,
        "paper-key",
        "paper-secret",
    )
    mock_market.assert_not_called()


@patch("broker_alpaca.submit_market_order")
@patch("broker_alpaca.submit_oto_order")
def test_execute_trade_uses_oto_for_single_protective_leg(mock_oto, mock_market):
    mock_oto.return_value = {
        "order_id": "oto-123",
        "status": "pending_new",
        "filled_avg_price": None,
    }

    result = broker_alpaca.execute_trade(
        symbol="AAPL",
        side="BUY",
        quantity=10,
        price=200.0,
        api_key="paper-key",
        api_secret="paper-secret",
        strategy="MARKET",
        stop_loss=180.0,
        take_profit=None,
        attach_protection=True,
    )

    assert result is not None
    assert result["main"]["order_id"] == "oto-123"
    mock_oto.assert_called_once_with(
        "AAPL",
        10,
        "BUY",
        "paper-key",
        "paper-secret",
        stop_price=180.0,
        limit_price=None,
    )
    mock_market.assert_not_called()


@patch("broker_alpaca.submit_stop_order")
@patch("broker_alpaca.submit_limit_order")
@patch("broker_alpaca.submit_market_order")
@patch("broker_alpaca.submit_bracket_order")
def test_execute_trade_skips_protection_when_attach_protection_false(
    mock_bracket,
    mock_market,
    mock_limit,
    mock_stop,
):
    mock_market.return_value = {
        "order_id": "main-123",
        "status": "pending_new",
        "filled_avg_price": None,
    }

    result = broker_alpaca.execute_trade(
        symbol="AAPL",
        side="SELL",
        quantity=10,
        price=200.0,
        api_key="paper-key",
        api_secret="paper-secret",
        strategy="MARKET",
        stop_loss=210.0,
        take_profit=190.0,
        attach_protection=False,
    )

    assert result is not None
    assert result["main"]["order_id"] == "main-123"
    mock_market.assert_called_once()
    mock_bracket.assert_not_called()
    mock_stop.assert_not_called()
    mock_limit.assert_not_called()


@patch("broker_alpaca.submit_stop_order")
@patch("broker_alpaca.submit_limit_order")
@patch("broker_alpaca.submit_market_order")
@patch("broker_alpaca.submit_oto_order")
@patch("broker_alpaca.submit_bracket_order")
def test_execute_trade_fallbacks_to_manual_protection_for_non_market_strategy(
    mock_bracket,
    mock_oto,
    mock_market,
    mock_limit,
    mock_stop,
):
    mock_limit.return_value = {
        "order_id": "limit-123",
        "status": "pending_new",
        "filled_avg_price": None,
    }
    mock_stop.return_value = {
        "order_id": "stop-123",
        "status": "pending_new",
        "filled_avg_price": None,
    }

    result = broker_alpaca.execute_trade(
        symbol="AAPL",
        side="BUY",
        quantity=10,
        price=200.0,
        api_key="paper-key",
        api_secret="paper-secret",
        strategy="LIMIT",
        stop_loss=180.0,
        take_profit=None,
        attach_protection=True,
    )

    assert result is not None
    assert result["main"]["order_id"] == "limit-123"
    assert result["stop_loss"]["order_id"] == "stop-123"
    mock_limit.assert_called_once_with("AAPL", 10, "BUY", 200.0, "paper-key", "paper-secret")
    mock_stop.assert_called_once_with("AAPL", 10, "SELL", 180.0, "paper-key", "paper-secret")
    mock_bracket.assert_not_called()
    mock_oto.assert_not_called()
    mock_market.assert_not_called()


@patch("broker_alpaca.submit_stop_order", side_effect=RuntimeError("wash trade detected"))
@patch("broker_alpaca.submit_limit_order")
def test_execute_trade_keeps_main_order_when_manual_protection_fails(mock_limit, mock_stop):
    mock_limit.return_value = {
        "order_id": "main-123",
        "status": "pending_new",
        "filled_avg_price": None,
    }

    result = broker_alpaca.execute_trade(
        symbol="AAPL",
        side="BUY",
        quantity=10,
        price=200.0,
        api_key="paper-key",
        api_secret="paper-secret",
        strategy="LIMIT",
        stop_loss=180.0,
        attach_protection=True,
    )

    assert result is not None
    assert result["main"]["order_id"] == "main-123"
    assert "stop_loss" not in result
    mock_limit.assert_called_once_with("AAPL", 10, "BUY", 200.0, "paper-key", "paper-secret")
    mock_stop.assert_called_once()


@patch("broker_alpaca.submit_market_order", side_effect=RuntimeError("unauthorized"))
def test_execute_trade_returns_none_when_main_order_fails(mock_market):
    result = broker_alpaca.execute_trade(
        symbol="AAPL",
        side="BUY",
        quantity=10,
        price=0.0,
        api_key="paper-key",
        api_secret="paper-secret",
        strategy="MARKET",
        stop_loss=None,
        take_profit=None,
    )

    assert result is None
    mock_market.assert_called_once()
