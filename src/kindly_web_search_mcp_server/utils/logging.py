from __future__ import annotations

import logging
import os


class ClosedResourceFilter(logging.Filter):
    """Filter out expected ClosedResourceError messages from SSE transport."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "ClosedResourceError" in msg or "Unexpected ASGI message" in msg:
            return False
        return True


def configure_logging() -> None:
    """
    Configure logging defaults for both local runs and MCP stdio hosts.

    Goals:
    - Avoid noisy third-party logs during tool execution (especially `httpx` request logs).
    - Keep configuration idempotent so hosts can override it safely.
    - Filter expected SSE transport errors that occur during normal concurrent operation.
    """
    root = logging.getLogger()

    # Only set up basicConfig if nothing configured yet (common for scripts).
    if not root.handlers:
        level = os.environ.get("LOG_LEVEL", "WARNING").upper()
        logging.basicConfig(level=getattr(logging, level, logging.WARNING))

    # Silence common noisy libraries unless the host explicitly configures them.
    noisy_loggers = (
        "httpx",
        "httpcore",
        "urllib3",
        "asyncio",
        "nodriver",
        "undetected_chromedriver",
    )
    for name in noisy_loggers:
        # `asyncio` can emit noisy warnings about slow callbacks in some environments.
        level = logging.ERROR if name == "asyncio" else logging.WARNING
        logging.getLogger(name).setLevel(level)

    # Filter expected SSE transport errors from starlette/mcp server
    mcp_logger = logging.getLogger("mcp.server.streamable_http")
    mcp_logger.addFilter(ClosedResourceFilter())
    starlette_logger = logging.getLogger("starlette.middleware.errors")
    starlette_logger.addFilter(ClosedResourceFilter())
