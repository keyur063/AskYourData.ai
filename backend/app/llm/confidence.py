"""
Low-confidence fallback — L5.3 (Session 5).

If the planner's confidence score is below the threshold, return a polite
"I'm not confident" message instead of guessing and silently producing a
wrong answer.

No structured clarification UI — just a plain-text message for lean scope.
"""
from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# Confidence threshold — below this, we bail out with a fallback message.
CONFIDENCE_THRESHOLD = 0.5

FALLBACK_MESSAGE = (
    "I'm not confident I understood your question correctly — "
    "could you rephrase or be more specific? "
    "Try mentioning specific column names or metrics you're interested in."
)


def check_confidence(ir: dict[str, Any]) -> dict[str, Any] | None:
    """Check if the planner's IR has sufficient confidence.

    Args:
        ir: The planner output dict (must include a ``confidence`` field).

    Returns:
        None if confidence is sufficient (proceed with execution).
        A fallback response dict ``{"fallback": True, "message": "..."}``
        if confidence is too low.
    """
    confidence = ir.get("confidence", 0.0)

    if confidence < CONFIDENCE_THRESHOLD:
        logger.info(
            "Low confidence (%.2f < %.2f) — returning fallback. IR operation=%s",
            confidence, CONFIDENCE_THRESHOLD, ir.get("operation"),
        )
        return {
            "fallback": True,
            "message": FALLBACK_MESSAGE,
            "confidence": confidence,
        }

    return None
