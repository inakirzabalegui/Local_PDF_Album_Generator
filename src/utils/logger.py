"""Structured logging system for album generation debugging."""

from __future__ import annotations

import logging
from pathlib import Path


def setup_logger(workspace: Path, mode: str) -> logging.Logger:
    """Set up dual-handler logger: console (INFO) + file (DEBUG).
    
    Args:
        workspace: Workspace directory where log file will be created
        mode: Operation mode ("init" or "render") for context
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("album")
    logger.setLevel(logging.DEBUG)
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Console handler - INFO level, minimal format
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("[%(levelname)s] %(message)s")
    console_handler.setFormatter(console_formatter)
    
    # File handler - DEBUG level, detailed format
    log_file = workspace / "album_debug.log"
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    # Log session start
    logger.info(f"=" * 60)
    logger.info(f"Starting {mode.upper()} mode")
    logger.debug(f"Workspace: {workspace}")
    logger.info(f"=" * 60)
    
    return logger


def get_logger() -> logging.Logger:
    """Get the album logger instance."""
    return logging.getLogger("album")
