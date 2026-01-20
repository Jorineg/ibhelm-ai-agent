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
            handler_kwargs = {"source_token": settings.betterstack_source_token}
            if settings.betterstack_ingest_host:
                handler_kwargs["host"] = settings.betterstack_ingest_host
            logtail = LogtailHandler(**handler_kwargs)
            logtail.setLevel(level)
            logger.addHandler(logtail)
            host_info = settings.betterstack_ingest_host or "in.logs.betterstack.com"
            logger.info(f"BetterStack logging enabled (host: {host_info})")
        except ImportError:
            logger.warning("logtail-python not installed, skipping BetterStack")
    
    return logger

