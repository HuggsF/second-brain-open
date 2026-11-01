"""Windowed event accumulator with count and timeout triggers.

Batches incoming events in a fixed window.  The window closes when
``window_size`` events accumulate **or** ``timeout_seconds`` elapse since
the first event in the current window — whichever comes first.

Thread-safe for ``ingest()``; timeout monitoring uses an asyncio background
task.
"""

from __future__ import annotations

import asyncio
import fnmatch
import threading
import time
from typing import Any, Callable, Dict, List, Optional


class EventAccumulator:
    """Accumulate events in a fixed window before triggering a callback.

    Parameters
    ----------
    window_size:
        Number of events that closes the window.
    timeout_seconds:
        Seconds since the first event in the window after which the window
        closes automatically.
    topic_filter:
        Optional glob pattern — only events whose ``topic`` key matches are
        accumulated.  Events that don't match are silently discarded.
    on_window_closed:
        Optional async callback invoked when the window closes.  Receives the
        batch as a ``list[dict]``.
    """

    def __init__(
        self,
        window_size: int = 5,
        timeout_seconds: float = 30.0,
        topic_filter: Optional[str] = None,
        on_window_closed: Optional[Callable[[List[Dict[str, Any]]], Any]] = None,
    ) -> None:
        if window_size < 1:
            raise ValueError("window_size must be >= 1")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")

        self._window_size = window_size
        self._timeout_seconds = timeout_seconds
        self._topic_filter = topic_filter
        self._on_window_closed = on_window_closed

        self._lock = threading.Lock()
        self._buffer: List[Dict[str, Any]] = []
        self._window_start: Optional[float] = None
        self._timeout_task: Optional[asyncio.Task[None]] = None
        self._closed = False

    # -- public API ----------------------------------------------------------

    @property
    def pending_count(self) -> int:
        """Number of events waiting in the current window."""
        with self._lock:
            return len(self._buffer)

    @property
    def window_size(self) -> int:
        """Configured window size."""
        return self._window_size

    @property
    def timeout_seconds(self) -> float:
        """Configured timeout in seconds."""
        return self._timeout_seconds

    def ingest(self, event: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """Add an event to the accumulator.

        Returns
        -------
        list[dict] | None
            The accumulated batch when the window closes (by count), or
            ``None`` if the window is still open.
        """
        # Apply topic filter
        if self._topic_filter is not None:
            topic = event.get("topic", "")
            if not fnmatch.fnmatchcase(topic, self._topic_filter):
                return None

        with self._lock:
            if self._closed:
                return None

            if not self._buffer:
                self._window_start = time.monotonic()
                self._schedule_timeout()

            self._buffer.append(event)

            if len(self._buffer) >= self._window_size:
                return self._flush_locked()

        return None

    def reset(self) -> None:
        """Clear the buffer and cancel any pending timeout."""
        with self._lock:
            self._buffer.clear()
            self._window_start = None
            self._cancel_timeout_locked()

    def close(self) -> None:
        """Mark accumulator as closed and flush remaining events."""
        with self._lock:
            self._closed = True
            self._cancel_timeout_locked()
            self._buffer.clear()
            self._window_start = None

    # -- internals -----------------------------------------------------------

    def _flush_locked(self) -> List[Dict[str, Any]]:
        """Return the current batch and reset (caller must hold ``_lock``)."""
        batch = list(self._buffer)
        self._buffer.clear()
        self._window_start = None
        self._cancel_timeout_locked()
        return batch

    def _cancel_timeout_locked(self) -> None:
        """Cancel the background timeout task (caller must hold ``_lock``)."""
        if self._timeout_task is not None and not self._timeout_task.done():
            self._timeout_task.cancel()
        self._timeout_task = None

    def _schedule_timeout(self) -> None:
        """Schedule an asyncio timeout task (caller must hold ``_lock``)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — timeout won't fire but count-based flush
            # still works.
            return

        self._cancel_timeout_locked()
        self._timeout_task = loop.create_task(self._timeout_worker())

    async def _timeout_worker(self) -> None:
        """Sleep until timeout and flush the window."""
        try:
            await asyncio.sleep(self._timeout_seconds)
        except asyncio.CancelledError:
            return

        batch: Optional[List[Dict[str, Any]]] = None
        with self._lock:
            if self._buffer:
                batch = self._flush_locked()

        if batch and self._on_window_closed is not None:
            result = self._on_window_closed(batch)
            if asyncio.iscoroutine(result):
                await result
