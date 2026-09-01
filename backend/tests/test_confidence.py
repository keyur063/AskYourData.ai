"""
Tests for app.llm.confidence — L5.3 acceptance criteria.

Accept: a deliberately ambiguous fixture question triggers the fallback
message, not a silent wrong answer.
"""
from __future__ import annotations

import os
os.environ.setdefault("ENCRYPTION_KEY", "test")
from cryptography.fernet import Fernet
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

from app.llm.confidence import check_confidence, CONFIDENCE_THRESHOLD, FALLBACK_MESSAGE


class TestConfidenceFallback:
    """check_confidence returns fallback or None based on score."""

    def test_high_confidence_passes(self):
        """Confidence above threshold should return None (proceed)."""
        ir = {"ir_version": "1.2", "kind": "structured", "source": "s",
              "operation": "preview", "confidence": 0.9}
        assert check_confidence(ir) is None

    def test_exactly_at_threshold_passes(self):
        """Confidence exactly at threshold should return None."""
        ir = {"ir_version": "1.2", "kind": "structured", "source": "s",
              "operation": "preview", "confidence": CONFIDENCE_THRESHOLD}
        assert check_confidence(ir) is None

    def test_below_threshold_returns_fallback(self):
        """Confidence below threshold should return the fallback dict."""
        ir = {"ir_version": "1.2", "kind": "structured", "source": "s",
              "operation": "aggregation", "confidence": 0.3}
        result = check_confidence(ir)
        assert result is not None
        assert result["fallback"] is True
        assert "rephrase" in result["message"]
        assert result["confidence"] == 0.3

    def test_zero_confidence_returns_fallback(self):
        ir = {"ir_version": "1.2", "kind": "structured", "source": "s",
              "operation": "preview", "confidence": 0.0}
        result = check_confidence(ir)
        assert result is not None
        assert result["fallback"] is True

    def test_missing_confidence_returns_fallback(self):
        """IR with no confidence field defaults to 0.0 → fallback."""
        ir = {"ir_version": "1.2", "kind": "structured", "source": "s",
              "operation": "preview"}
        result = check_confidence(ir)
        assert result is not None
        assert result["fallback"] is True

    def test_fallback_message_is_user_friendly(self):
        """The fallback message should be helpful, not technical."""
        assert "rephrase" in FALLBACK_MESSAGE.lower() or "specific" in FALLBACK_MESSAGE.lower()
        # Should NOT contain technical terms
        assert "schema" not in FALLBACK_MESSAGE.lower()
        assert "error" not in FALLBACK_MESSAGE.lower()

    def test_ambiguous_question_scenario(self):
        """Simulate: planner produces low confidence for an ambiguous question."""
        # This is the L5.3 accept criteria — an ambiguous question produces
        # low confidence, and check_confidence catches it.
        ir_from_ambiguous_question = {
            "ir_version": "1.2", "kind": "structured",
            "source": "sales", "operation": "aggregation",
            "metrics": [{"column": "value", "aggregation": "SUM"}],
            "confidence": 0.35,  # Planner isn't sure what "value" means
        }
        result = check_confidence(ir_from_ambiguous_question)
        assert result is not None
        assert result["fallback"] is True
        assert result["message"] == FALLBACK_MESSAGE
