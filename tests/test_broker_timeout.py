"""Tests for F-BR-01: Tool timeout via asyncio.wait_for."""
import asyncio
import pytest
from unittest import mock
from core import broker
from core.policy import Decision, Reason, Verdict


@pytest.mark.asyncio
async def test_tool_timeout_returns_error():
    """Tool that exceeds timeout returns ToolTimeout error (INV-N06)."""
    async def _slow_execute(tool, args):
        await asyncio.sleep(0.5)
        return {"result": "never"}, None

    _original_wait_for = asyncio.wait_for

    async def _patched_wait_for(coro, timeout=None):
        """Forces a short timeout for test speed."""
        return await _original_wait_for(coro, timeout=0.05)

    approve_verdict = Verdict(Decision.APPROVE, Reason.read_auto, "approved for test")

    with mock.patch.object(broker, "_execute", side_effect=_slow_execute), \
         mock.patch.object(broker, "decide", return_value=approve_verdict), \
         mock.patch.object(broker.asyncio, "wait_for", side_effect=_patched_wait_for):
        result = await broker.call("agent:researcher", "slow_tool", {}, approved=True)
    assert result.get("error") == "ToolTimeout"
    assert result.get("timed_out") is True


@pytest.mark.asyncio
async def test_tool_within_timeout_succeeds():
    """Tool completing before timeout returns normally."""
    async def _fast_tool(tool, args):
        return {"result": "ok"}, None

    approve_verdict = Verdict(Decision.APPROVE, Reason.read_auto, "approved for test")

    with mock.patch.object(broker, "_execute", side_effect=_fast_tool), \
         mock.patch.object(broker, "decide", return_value=approve_verdict):
        result = await broker.call("agent:researcher", "fast_tool", {}, approved=True)
    assert result.get("error") != "ToolTimeout"
    assert result.get("timed_out") is not True
