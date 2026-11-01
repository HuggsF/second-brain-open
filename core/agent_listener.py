"""Base class for agents that listen to topics and react to windowed events.

Provides an automatic lifecycle: listen → accumulate → ``on_window_closed``
→ publish result → repeat.

Subclasses implement :meth:`on_window_closed` to process a batch of events
and optionally return a result event to publish back to the router.
"""

from __future__ import annotations

import abc
import asyncio
import logging
from typing import Any, Dict, List, Optional

from core.event_accumulator import EventAccumulator
from core.topic_router import TopicRouter

logger = logging.getLogger(__name__)


class AgentListener(abc.ABC):
    """Abstract base class for topic-listening agents.

    Parameters
    ----------
    agent_id:
        Unique identifier for this agent (e.g. ``"researcher"``).
    listen_topics:
        List of glob patterns to subscribe to (e.g. ``["diagnostic.*"]``).
    window_size:
        Number of events to accumulate before triggering
        :meth:`on_window_closed`.
    timeout_seconds:
        Maximum seconds to wait for a full window before flushing.
    router:
        The :class:`TopicRouter` instance to subscribe to and publish on.
    """

    def __init__(
        self,
        agent_id: str,
        listen_topics: List[str],
        router: TopicRouter,
        window_size: int = 5,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._agent_id = agent_id
        self._listen_topics = listen_topics
        self._router = router
        self._window_size = window_size
        self._timeout_seconds = timeout_seconds

        self._queues: List[asyncio.Queue[Dict[str, Any]]] = []
        self._tasks: List[asyncio.Task[None]] = []
        self._accumulator = EventAccumulator(
            window_size=window_size,
            timeout_seconds=timeout_seconds,
            on_window_closed=self._handle_timeout_batch,
        )
        self._events_processed: int = 0
        self._running = False
        self._stop_event = asyncio.Event()

    # -- properties ----------------------------------------------------------

    @property
    def agent_id(self) -> str:
        """The unique agent identifier."""
        return self._agent_id

    @property
    def is_alive(self) -> bool:
        """``True`` if the listener loop is running."""
        return self._running and not self._stop_event.is_set()

    @property
    def events_processed(self) -> int:
        """Total number of events processed through ``on_window_closed``."""
        return self._events_processed

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        """Begin listening on all configured topics.

        Subscribes to each topic pattern via the router and starts an
        asyncio task per subscription to drain the queue.
        """
        if self._running:
            logger.warning("AgentListener %s is already running", self._agent_id)
            return

        self._running = True
        self._stop_event.clear()

        for pattern in self._listen_topics:
            q = self._router.subscribe(pattern)
            self._queues.append(q)
            loop = asyncio.get_running_loop()
            task = loop.create_task(
                self._listen_loop(q),
                name=f"agent-listener-{self._agent_id}-{pattern}",
            )
            self._tasks.append(task)

        logger.info(
            "AgentListener %s started on topics %s (window=%d, timeout=%.1fs)",
            self._agent_id,
            self._listen_topics,
            self._window_size,
            self._timeout_seconds,
        )

    async def stop(self) -> None:
        """Gracefully stop all listener tasks and unsubscribe."""
        if not self._running:
            return

        self._stop_event.set()

        for task in self._tasks:
            task.cancel()

        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

        for q in self._queues:
            self._router.unsubscribe(q)

        self._tasks.clear()
        self._queues.clear()
        self._accumulator.close()
        self._running = False

        logger.info(
            "AgentListener %s stopped (processed %d events)",
            self._agent_id,
            self._events_processed,
        )

    # -- abstract method -----------------------------------------------------

    @abc.abstractmethod
    async def on_window_closed(self, events: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Process a batch of accumulated events.

        Subclasses **must** implement this method.  Return a ``dict`` to
        publish a result event back to the router, or ``None`` to stay silent.

        Parameters
        ----------
        events:
            The batch of events accumulated in the window.

        Returns
        -------
        dict | None
            An event dict to publish (must include ``topic`` and ``payload``),
            or ``None``.
        """
        ...

    # -- convenience ---------------------------------------------------------

    def publish_result(self, topic: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Convenience method to publish a result back to the router.

        Automatically populates ``agentId`` from this listener's id.

        Parameters
        ----------
        topic:
            Topic to publish to.
        payload:
            Event payload dictionary.

        Returns
        -------
        dict
            The enriched, sanitised event as returned by
            :meth:`TopicRouter.publish`.
        """
        return self._router.publish(topic, {
            "agentId": self._agent_id,
            "payload": payload,
        })

    # -- internals -----------------------------------------------------------

    async def _listen_loop(self, q: asyncio.Queue[Dict[str, Any]]) -> None:
        """Drain a subscriber queue, accumulate, and dispatch windows."""
        try:
            while not self._stop_event.is_set():
                try:
                    event = await asyncio.wait_for(q.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                batch = self._accumulator.ingest(event)
                if batch is not None:
                    await self._dispatch_batch(batch)
        except asyncio.CancelledError:
            return

    async def _dispatch_batch(self, batch: List[Dict[str, Any]]) -> None:
        """Invoke ``on_window_closed`` and publish any result."""
        self._events_processed += len(batch)
        try:
            result = await self.on_window_closed(batch)
        except Exception:
            logger.exception(
                "AgentListener %s: on_window_closed raised", self._agent_id
            )
            return

        if result is not None:
            topic = result.pop("topic", f"{self._agent_id}.result")
            result.setdefault("agentId", self._agent_id)
            self._router.publish(topic, result)

    async def _handle_timeout_batch(self, batch: List[Dict[str, Any]]) -> None:
        """Callback for :class:`EventAccumulator` timeout flushes."""
        await self._dispatch_batch(batch)
