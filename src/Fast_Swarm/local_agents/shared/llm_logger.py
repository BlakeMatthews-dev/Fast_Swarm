"""
LLM Response Logger.

Dedicated logging for ALL LLM responses (both parsed and unparsed).
Writes to a separate log file for debugging AI zone decisions.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

# Dedicated logger - writes to logs/llm_responses.log (separate from main app log)
llm_logger = logging.getLogger("llm_responses")


@dataclass
class LLMResponseRecord:
    """Record of a single LLM response for logging."""

    timestamp: datetime
    agent_id: str | None
    pattern_name: str
    confidence: float
    raw_content: str  # FULL raw response text
    parsed_successfully: bool
    parsed_decision: str | None  # "TAKE" / "SKIP" / None
    reasoning: str | None
    trade_outcome: str | None = None  # Set later: "win" / "loss" / "hold"
    latency_ms: int = 0
    model: str = ""


def log_llm_response(record: LLMResponseRecord):
    """Log an LLM response to the dedicated llm_responses logger."""
    status = "PARSED" if record.parsed_successfully else "PARSE_FAIL"
    llm_logger.info(
        "[%s] agent=%s pattern=%s conf=%.2f decision=%s latency=%dms | RAW: %s | REASON: %s",
        status,
        record.agent_id or "unknown",
        record.pattern_name,
        record.confidence,
        record.parsed_decision or "NONE",
        record.latency_ms,
        record.raw_content[:2000],  # Cap at 2000 chars
        record.reasoning or "N/A",
    )
