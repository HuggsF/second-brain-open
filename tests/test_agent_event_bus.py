"""Tests for the inter-agent communication infrastructure.

Covers:
- TopicRouter: subscribe, publish, pattern matching, PII sanitisation,
  backward compat with ``events.publish``.
- EventAccumulator: window close by count, window close by timeout,
  reset, topic filter, edge cases.
- AgentListener: lifecycle, event processing, publish result.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from core.topic_router import TopicRouter, _matches_topic, _sanitise_value
from core.event_accumulator import EventAccumulator
from core.agent_listener import AgentListener


# ═══════════════════════════════════════════════════════════════════════════
# TopicRouter
# ═══════════════════════════════════════════════════════════════════════════


class TestMatchesTopic:
    """Unit tests for glob-like topic matching."""

    def test_exact_match(self) -> None:
        assert _matches_topic("diagnostic.evidence", "diagnostic.evidence")

    def test_wildcard_single_level(self) -> None:
        assert _matches_topic("diagnostic.*", "diagnostic.evidence")
        assert _matches_topic("diagnostic.*", "diagnostic.tool_result")

    def test_wildcard_matches_across_dots(self) -> None:
        # fnmatch treats * as matching any character including dots,
        # so "diagnostic.*" matches multi-level topics too.
        assert _matches_topic("diagnostic.*", "diagnostic.deep.nested")

    def test_no_match(self) -> None:
        assert not _matches_topic("tool.*", "diagnostic.evidence")

    def test_star_matches_all_single_level(self) -> None:
        assert _matches_topic("*", "anything")

    def test_double_star(self) -> None:
        """Double-star should work for multi-level (fnmatch behaviour)."""
        # fnmatch treats * as matching anything including dots in a flat string
        # so "**" is effectively the same as "*" for fnmatch
        assert _matches_topic("*", "diagnostic.evidence")


class TestPIISanitisation:
    """Unit tests for PII stripping in payloads."""

    def test_cpf_stripped(self) -> None:
        assert _sanitise_value("CPF: 123.456.789-00") == "CPF: [CPF]"

    def test_cpf_no_punctuation(self) -> None:
        assert _sanitise_value("CPF: 12345678900") == "CPF: [CPF]"

    def test_email_stripped(self) -> None:
        assert _sanitise_value("email: user@example.com") == "email: [EMAIL]"

    def test_phone_stripped(self) -> None:
        result = _sanitise_value("tel: +55 11 99999-1234")
        assert "[PHONE]" in result

    def test_cep_stripped(self) -> None:
        assert _sanitise_value("CEP: 01310-100") == "CEP: [CEP]"

    def test_nested_dict_sanitised(self) -> None:
        data = {"name": "test", "doc": "123.456.789-00", "inner": {"email": "a@b.com"}}
        result = _sanitise_value(data)
        assert result["doc"] == "[CPF]"
        assert result["inner"]["email"] == "[EMAIL]"

    def test_list_sanitised(self) -> None:
        data = ["user@test.com", "normal text"]
        result = _sanitise_value(data)
        assert result[0] == "[EMAIL]"
        assert result[1] == "normal text"

    def test_non_string_passthrough(self) -> None:
        assert _sanitise_value(42) == 42
        assert _sanitise_value(None) is None
        assert _sanitise_value(3.14) == 3.14


class TestTopicRouterSubscribePublish:
    """Integration tests for TopicRouter subscribe/publish flow."""

    @pytest.mark.asyncio
    async def test_subscriber_receives_matching_event(self) -> None:
        router = TopicRouter()
        q = router.subscribe("diagnostic.*")

        router.publish("diagnostic.evidence", {
            "agentId": "researcher",
            "missionId": "M42",
            "payload": {"tool": "search", "results": ["item1"]},
        })

        event = q.get_nowait()
        assert event["topic"] == "diagnostic.evidence"
        assert event["agentId"] == "researcher"
        assert event["missionId"] == "M42"
        assert "sequence" in event
        assert "timestamp" in event
        assert event["payload"]["tool"] == "search"

    @pytest.mark.asyncio
    async def test_subscriber_does_not_receive_non_matching(self) -> None:
        router = TopicRouter()
        q = router.subscribe("tool.*")

        router.publish("diagnostic.evidence", {
            "agentId": "researcher",
            "missionId": "M1",
            "payload": {},
        })

        assert q.empty()

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self) -> None:
        router = TopicRouter()
        q1 = router.subscribe("diagnostic.*")
        q2 = router.subscribe("diagnostic.evidence")
        q3 = router.subscribe("tool.*")

        router.publish("diagnostic.evidence", {
            "agentId": "r",
            "missionId": "M1",
            "payload": {},
        })

        assert not q1.empty()
        assert not q2.empty()
        assert q3.empty()

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_queue(self) -> None:
        router = TopicRouter()
        q = router.subscribe("diagnostic.*")
        assert router.subscriber_count == 1

        router.unsubscribe(q)
        assert router.subscriber_count == 0

        router.publish("diagnostic.evidence", {
            "agentId": "r",
            "missionId": "M1",
            "payload": {},
        })
        assert q.empty()

    @pytest.mark.asyncio
    async def test_pii_sanitised_in_published_event(self) -> None:
        router = TopicRouter()
        q = router.subscribe("test.*")

        router.publish("test.data", {
            "agentId": "agent1",
            "missionId": "M1",
            "payload": {"cpf": "123.456.789-00", "email": "user@example.com"},
        })

        event = q.get_nowait()
        assert event["payload"]["cpf"] == "[CPF]"
        assert event["payload"]["email"] == "[EMAIL]"

    @pytest.mark.asyncio
    async def test_backward_compat_calls_events_publish(self) -> None:
        router = TopicRouter()

        with patch("core.topic_router.events.publish") as mock_pub:
            router.publish("test.compat", {
                "agentId": "agent1",
                "missionId": "M1",
                "payload": {},
            })

            mock_pub.assert_called_once()
            call_arg = mock_pub.call_args[0][0]
            assert call_arg["topic"] == "test.compat"

    @pytest.mark.asyncio
    async def test_enrichment_adds_missing_fields(self) -> None:
        router = TopicRouter()
        q = router.subscribe("*")

        result = router.publish("my.topic", {"payload": {"data": 1}})

        assert result["topic"] == "my.topic"
        assert result["agentId"] == "unknown"
        assert result["missionId"] == "unknown"
        assert isinstance(result["sequence"], int)
        assert isinstance(result["timestamp"], int)
        assert "id" in result

    @pytest.mark.asyncio
    async def test_full_queue_evicts_subscriber(self) -> None:
        router = TopicRouter(maxsize=1)
        q = router.subscribe("test.*")

        # Fill the queue
        router.publish("test.a", {"agentId": "a", "missionId": "M", "payload": {}})
        # This should cause eviction since queue is full
        router.publish("test.b", {"agentId": "a", "missionId": "M", "payload": {}})

        assert router.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_close_clears_subscribers(self) -> None:
        router = TopicRouter()
        router.subscribe("test.*")
        router.subscribe("other.*")
        assert router.subscriber_count == 2

        router.close()
        assert router.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_persist_creates_file(self, tmp_path) -> None:
        log_path = tmp_path / "agent-events.jsonl"
        router = TopicRouter(log_path=log_path)

        router.publish("test.persist", {
            "agentId": "a",
            "missionId": "M1",
            "payload": {"key": "value"},
        })

        assert log_path.exists()
        import json
        line = log_path.read_text().strip()
        data = json.loads(line)
        assert data["topic"] == "test.persist"


# ═══════════════════════════════════════════════════════════════════════════
# EventAccumulator
# ═══════════════════════════════════════════════════════════════════════════


class TestEventAccumulatorCount:
    """Tests for window-close by event count."""

    def test_returns_none_until_full(self) -> None:
        acc = EventAccumulator(window_size=3)
        assert acc.ingest({"topic": "a", "n": 1}) is None
        assert acc.ingest({"topic": "a", "n": 2}) is None
        assert acc.pending_count == 2

    def test_returns_batch_at_window_size(self) -> None:
        acc = EventAccumulator(window_size=3)
        acc.ingest({"topic": "a", "n": 1})
        acc.ingest({"topic": "a", "n": 2})
        batch = acc.ingest({"topic": "a", "n": 3})

        assert batch is not None
        assert len(batch) == 3
        assert [e["n"] for e in batch] == [1, 2, 3]

    def test_window_resets_after_flush(self) -> None:
        acc = EventAccumulator(window_size=2)
        batch1 = acc.ingest({"n": 1})
        assert batch1 is None
        batch1 = acc.ingest({"n": 2})
        assert batch1 is not None

        # Second window
        assert acc.pending_count == 0
        assert acc.ingest({"n": 3}) is None
        batch2 = acc.ingest({"n": 4})
        assert batch2 is not None
        assert len(batch2) == 2

    def test_window_size_one(self) -> None:
        acc = EventAccumulator(window_size=1)
        batch = acc.ingest({"n": 1})
        assert batch is not None
        assert len(batch) == 1


class TestEventAccumulatorTimeout:
    """Tests for window-close by timeout."""

    @pytest.mark.asyncio
    async def test_timeout_flushes_partial_window(self) -> None:
        batches: List[List[Dict[str, Any]]] = []

        async def on_closed(batch: List[Dict[str, Any]]) -> None:
            batches.append(batch)

        acc = EventAccumulator(
            window_size=10,
            timeout_seconds=0.1,
            on_window_closed=on_closed,
        )

        acc.ingest({"n": 1})
        acc.ingest({"n": 2})

        # Wait for timeout
        await asyncio.sleep(0.3)

        assert len(batches) == 1
        assert len(batches[0]) == 2

    @pytest.mark.asyncio
    async def test_count_flush_cancels_timeout(self) -> None:
        timeout_fired = []

        async def on_closed(batch: List[Dict[str, Any]]) -> None:
            timeout_fired.append(batch)

        acc = EventAccumulator(
            window_size=2,
            timeout_seconds=0.1,
            on_window_closed=on_closed,
        )

        acc.ingest({"n": 1})
        batch = acc.ingest({"n": 2})
        assert batch is not None

        # Wait to ensure timeout doesn't fire after count flush
        await asyncio.sleep(0.3)
        assert len(timeout_fired) == 0


class TestEventAccumulatorTopicFilter:
    """Tests for topic_filter option."""

    def test_matching_topic_accepted(self) -> None:
        acc = EventAccumulator(window_size=1, topic_filter="diagnostic.*")
        batch = acc.ingest({"topic": "diagnostic.evidence", "n": 1})
        assert batch is not None

    def test_non_matching_topic_rejected(self) -> None:
        acc = EventAccumulator(window_size=1, topic_filter="diagnostic.*")
        batch = acc.ingest({"topic": "tool.start", "n": 1})
        assert batch is None
        assert acc.pending_count == 0

    def test_no_filter_accepts_all(self) -> None:
        acc = EventAccumulator(window_size=1)
        batch = acc.ingest({"topic": "anything", "n": 1})
        assert batch is not None


class TestEventAccumulatorEdgeCases:
    """Edge case tests for EventAccumulator."""

    def test_reset_clears_buffer(self) -> None:
        acc = EventAccumulator(window_size=5)
        acc.ingest({"n": 1})
        acc.ingest({"n": 2})
        assert acc.pending_count == 2

        acc.reset()
        assert acc.pending_count == 0

    def test_invalid_window_size(self) -> None:
        with pytest.raises(ValueError, match="window_size"):
            EventAccumulator(window_size=0)

    def test_invalid_timeout(self) -> None:
        with pytest.raises(ValueError, match="timeout_seconds"):
            EventAccumulator(timeout_seconds=0)

    def test_close_prevents_ingestion(self) -> None:
        acc = EventAccumulator(window_size=1)
        acc.close()
        assert acc.ingest({"n": 1}) is None


# ═══════════════════════════════════════════════════════════════════════════
# AgentListener
# ═══════════════════════════════════════════════════════════════════════════


class ConcreteListener(AgentListener):
    """Test implementation of AgentListener."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.received_batches: List[List[Dict[str, Any]]] = []
        self.return_event: Optional[Dict[str, Any]] = None

    async def on_window_closed(self, events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        self.received_batches.append(events)
        return self.return_event


class TestAgentListenerLifecycle:
    """Tests for AgentListener start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_sets_alive(self) -> None:
        router = TopicRouter()
        listener = ConcreteListener(
            agent_id="test-agent",
            listen_topics=["test.*"],
            router=router,
            window_size=2,
        )

        listener.start()
        assert listener.is_alive
        assert listener.agent_id == "test-agent"

        await listener.stop()
        assert not listener.is_alive

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self) -> None:
        router = TopicRouter()
        listener = ConcreteListener(
            agent_id="test-agent",
            listen_topics=["test.*"],
            router=router,
        )

        listener.start()
        listener.start()  # should warn but not crash
        assert listener.is_alive

        await listener.stop()

    @pytest.mark.asyncio
    async def test_stop_without_start_is_safe(self) -> None:
        router = TopicRouter()
        listener = ConcreteListener(
            agent_id="test-agent",
            listen_topics=["test.*"],
            router=router,
        )
        await listener.stop()  # should not raise
        assert not listener.is_alive


class TestAgentListenerProcessing:
    """Tests for event processing through AgentListener."""

    @pytest.mark.asyncio
    async def test_receives_and_processes_events(self) -> None:
        router = TopicRouter()
        listener = ConcreteListener(
            agent_id="test-agent",
            listen_topics=["diagnostic.*"],
            router=router,
            window_size=2,
        )

        listener.start()

        # Publish 2 events to trigger window
        router.publish("diagnostic.evidence", {
            "agentId": "researcher",
            "missionId": "M1",
            "payload": {"data": "a"},
        })
        router.publish("diagnostic.tool_result", {
            "agentId": "researcher",
            "missionId": "M1",
            "payload": {"data": "b"},
        })

        # Allow processing time
        await asyncio.sleep(0.2)

        await listener.stop()

        assert len(listener.received_batches) == 1
        assert len(listener.received_batches[0]) == 2
        assert listener.events_processed == 2

    @pytest.mark.asyncio
    async def test_publish_result_from_on_window_closed(self) -> None:
        router = TopicRouter()

        # Subscribe to the result topic
        result_q = router.subscribe("test-agent.output")

        listener = ConcreteListener(
            agent_id="test-agent",
            listen_topics=["input.*"],
            router=router,
            window_size=1,
        )
        listener.return_event = {
            "topic": "test-agent.output",
            "payload": {"summary": "processed"},
        }

        listener.start()

        router.publish("input.data", {
            "agentId": "source",
            "missionId": "M1",
            "payload": {"raw": "content"},
        })

        await asyncio.sleep(0.2)
        await listener.stop()

        # The listener should have published a result
        assert not result_q.empty()
        result_event = result_q.get_nowait()
        assert result_event["payload"]["summary"] == "processed"
        assert result_event["agentId"] == "test-agent"

    @pytest.mark.asyncio
    async def test_publish_result_convenience(self) -> None:
        router = TopicRouter()
        result_q = router.subscribe("my.result")

        listener = ConcreteListener(
            agent_id="agent-x",
            listen_topics=["trigger.*"],
            router=router,
        )

        listener.start()

        result = listener.publish_result("my.result", {"status": "ok"})
        assert result["agentId"] == "agent-x"
        assert result["payload"]["status"] == "ok"

        event = result_q.get_nowait()
        assert event["topic"] == "my.result"

        await listener.stop()

    @pytest.mark.asyncio
    async def test_events_processed_counter(self) -> None:
        router = TopicRouter()
        listener = ConcreteListener(
            agent_id="counter-agent",
            listen_topics=["count.*"],
            router=router,
            window_size=1,
        )

        listener.start()
        assert listener.events_processed == 0

        for i in range(3):
            router.publish("count.event", {
                "agentId": "src",
                "missionId": "M",
                "payload": {"i": i},
            })

        await asyncio.sleep(0.3)
        await listener.stop()

        assert listener.events_processed == 3

    @pytest.mark.asyncio
    async def test_on_window_closed_exception_does_not_crash(self) -> None:
        """If on_window_closed raises, the listener should keep running."""

        class FailingListener(AgentListener):
            call_count: int = 0

            async def on_window_closed(self, events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
                self.call_count += 1
                if self.call_count == 1:
                    raise ValueError("boom")
                return None

        router = TopicRouter()
        listener = FailingListener(
            agent_id="fail-agent",
            listen_topics=["err.*"],
            router=router,
            window_size=1,
        )

        listener.start()

        # First event: on_window_closed raises
        router.publish("err.first", {"agentId": "s", "missionId": "M", "payload": {}})
        await asyncio.sleep(0.1)

        # Second event: should still be processed
        router.publish("err.second", {"agentId": "s", "missionId": "M", "payload": {}})
        await asyncio.sleep(0.1)

        await listener.stop()

        assert listener.call_count == 2
