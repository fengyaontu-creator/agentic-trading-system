"""
logging_utils.py -- Centralized logging configuration and utilities.

Provides standardized logging setup for all modules in the trading system.
Logs are written to both console and file outputs for debugging and monitoring.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime


def setup_logging(
    module_name: str = "__main__",
    log_dir: str = "logs",
    log_level: int = logging.INFO,
    max_bytes: int = 10_485_760,  # 10 MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    Configure logging for a module with both console and file handlers.

    Args:
        module_name: The name of the module (typically __name__)
        log_dir: Directory where log files will be stored
        log_level: Logging level (e.g., logging.INFO, logging.DEBUG)
        max_bytes: Maximum size of a single log file before rotation
        backup_count: Number of backup log files to keep

    Returns:
        A configured logger instance for the module
    """
    # Ensure log directory exists
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(module_name)
    logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Format: timestamp [level] module_name - message
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler with rotation
    log_filename = os.path.join(log_dir, f"{module_name.replace('.', '_')}.log")
    file_handler = RotatingFileHandler(
        log_filename,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def setup_global_logging(
    log_dir: str = "logs",
    log_level: int = logging.INFO,
    max_bytes: int = 10_485_760,  # 10 MB
    backup_count: int = 5,
) -> None:
    """
    Configure the root logger for the entire application.

    Args:
        log_dir: Directory where log files will be stored
        log_level: Logging level for the application
        max_bytes: Maximum size of a single log file before rotation
        backup_count: Number of backup log files to keep

    This should typically be called once at application startup
    (e.g., in src/scheduler.py before running sessions).
    """
    os.makedirs(log_dir, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler with rotation
    log_filename = os.path.join(log_dir, "trading_system.log")
    file_handler = RotatingFileHandler(
        log_filename,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


class TradeLogger:
    """Helper class for structured trade logging."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def log_trade_execution(
        self,
        user_id: str,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        order_id: str,
        status: str = "PENDING",
    ) -> None:
        """Log a trade execution event."""
        self.logger.info(
            f"[TRADE] {user_id}/{symbol} | side={side} qty={quantity} price={price} "
            f"order_id={order_id} status={status}"
        )

    def log_trade_failure(
        self,
        user_id: str,
        symbol: str,
        side: str,
        quantity: int,
        reason: str,
        error: Exception = None,
    ) -> None:
        """Log a trade failure with detailed context."""
        if error:
            self.logger.error(
                f"[TRADE_FAIL] {user_id}/{symbol} | side={side} qty={quantity} | "
                f"reason={reason} | error={error}",
                exc_info=True,
            )
        else:
            self.logger.error(
                f"[TRADE_FAIL] {user_id}/{symbol} | side={side} qty={quantity} | reason={reason}"
            )

    def log_signal_generated(
        self,
        user_id: str,
        symbol: str,
        signal: str,
        confidence: float,
        technical_score: float = None,
        sentiment_score: float = None,
    ) -> None:
        """Log a trading signal generation."""
        msg = f"[SIGNAL] {user_id}/{symbol} | signal={signal} confidence={confidence:.0%}"
        if technical_score is not None:
            msg += f" technical={technical_score:.2f}"
        if sentiment_score is not None:
            msg += f" sentiment={sentiment_score:.2f}"
        self.logger.info(msg)

    def log_risk_assessment(
        self,
        user_id: str,
        symbol: str,
        should_trade: bool,
        risk_score: float = None,
        position_size: int = None,
        stop_loss: float = None,
        take_profit: float = None,
    ) -> None:
        """Log risk assessment result."""
        msg = f"[RISK] {user_id}/{symbol} | should_trade={should_trade}"
        if risk_score is not None:
            msg += f" risk_score={risk_score:.2f}"
        if position_size is not None:
            msg += f" position_size={position_size}"
        if stop_loss is not None:
            msg += f" stop_loss={stop_loss:.2f}"
        if take_profit is not None:
            msg += f" take_profit={take_profit:.2f}"
        self.logger.info(msg)

    def log_reconciliation_issue(
        self, user_id: str, symbol: str, broker_qty: int, db_qty: int
    ) -> None:
        """Log a position reconciliation discrepancy."""
        self.logger.warning(
            f"[RECONCILE] {user_id}/{symbol} | broker_qty={broker_qty} db_qty={db_qty}"
        )


# Example usage:
# from logging_utils import setup_logging, TradeLogger
# log = setup_logging(__name__)
# trade_log = TradeLogger(log)
# trade_log.log_trade_execution(user_id="user123", symbol="AAPL", side="BUY", quantity=10, price=150.25, order_id="ord_123")
