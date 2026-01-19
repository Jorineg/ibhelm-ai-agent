"""Logging configuration with optional BetterStack integration."""

import logging
import sys

from src.settings import settings

logger = logging.getLogger("ai_agent")


class FlushingStreamHandler(logging.StreamHandler):
    """StreamHandler that flushes after every emit."""
    def emit(self, record):
        super().emit(record)
        self.flush()


def setup_logging():
    """Configure logging with optional BetterStack."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    
    # Console handler with immediate flushing
    console = FlushingStreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    
    logger.setLevel(level)
    logger.addHandler(console)
    
    # BetterStack handler (optional)
    if settings.betterstack_source_token:
        try:
            from logtail import LogtailHandler
            logtail = LogtailHandler(source_token=settings.betterstack_source_token)
            logtail.setLevel(level)
            logger.addHandler(logtail)
            logger.info("BetterStack logging enabled")
        except ImportError:
            logger.warning("logtail-python not installed, skipping BetterStack")
    
    return logger

