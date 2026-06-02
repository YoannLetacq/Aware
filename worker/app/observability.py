"""Logging configuration and failure observability helpers.

Phase 2 ships structlog JSON configuration mirroring the bot's pipeline.
Phase 3 will extend this module with screenshot, DOM dump, and HAR capture
on Playwright exceptions.
"""

import logging
import sys

import structlog


def configure_logging() -> None:
    """Configure structlog to emit JSON logs to stdout (docker json-file driver)."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
