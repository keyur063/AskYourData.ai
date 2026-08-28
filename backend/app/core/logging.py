"""
Structured logging for AskYourData.ai.

Every request gets a unique request_id that flows through all log lines.
Use get_logger(__name__) in each module — don't configure handlers yourself.
"""
import logging
import sys
from contextvars import ContextVar

# Context variable so request_id propagates across async awaits automatically.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    """Injects request_id from context into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get("-")
        return True


def _configure_root_logger() -> None:
    root = logging.getLogger()
    if root.handlers:
        return  # already configured (e.g. by uvicorn)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s - %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    handler.addFilter(_RequestIdFilter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)


_configure_root_logger()


def get_logger(name: str) -> logging.Logger:
    """Return a module logger that automatically includes request_id."""
    logger = logging.getLogger(name)
    # Ensure the filter is on this logger too (root handler picks it up,
    # but belt-and-suspenders in case callers add their own handlers later).
    for h in logger.handlers:
        h.addFilter(_RequestIdFilter())
    return logger
