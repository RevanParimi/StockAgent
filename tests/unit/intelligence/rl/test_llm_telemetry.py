"""
tests/unit/intelligence/rl/test_llm_telemetry.py
=================================================
Unit tests for LLM telemetry recording (record_llm_call function).
"""

import json
from pathlib import Path
from unittest.mock import patch


def test_record_llm_call_writes_jsonl(tmp_path):
    """record_llm_call appends a valid JSON line to outputs/llm_log/{date}.jsonl."""
    with patch("services.clients.llm_client._LLM_LOG_DIR", tmp_path):
        from services.clients.llm_client import record_llm_call
        record_llm_call(
            caller="FeedbackAgent",
            model="qwen/qwen-2.5-72b-instruct",
            input_tokens=1420,
            output_tokens=380,
            latency_ms=2341,
            success=True,
        )

    log_files = list(tmp_path.glob("*.jsonl"))
    assert len(log_files) == 1
    line = json.loads(log_files[0].read_text().strip())
    assert line["caller"] == "FeedbackAgent"
    assert line["input_tokens"] == 1420
    assert line["success"] is True
    assert "ts" in line


def test_record_llm_call_is_nonfatal_on_bad_path():
    """record_llm_call never raises even with a bad path."""
    with patch("services.clients.llm_client._LLM_LOG_DIR", Path("/nonexistent/path/xyz")):
        from services.clients.llm_client import record_llm_call
        record_llm_call("test", "model", 0, 0, 0, False)  # must not raise
