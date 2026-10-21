"""Bootstrap module: initialise the application, load config, wire dependencies.

Call :func:`bootstrap` once at startup.  It returns a :class:`Container` that
holds every shared service the application needs.  The container is also
cached at module level and retrievable via :func:`get_container`.

Adapter classes (:class:`_TracingAdapter`, :class:`_EventAdapter`) bridge
concrete implementations in ``core.tracing`` and ``core.events`` to the
:mod:`core.ports` protocols so that business logic depends only on
abstractions.

:class:`ObservabilityContext` carries per-request identifiers (trace / span)
and lightweight counters (tokens, node visits).
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config import Settings, settings
from core import tracing
from core.ports import (
    CommandExecutor,
    EventPublisher,
    KnowledgeRetriever,
    ObservationCollector,
    TraceWriter,
)

__all__ = [
    "Container",
    "bootstrap",
    "get_container",
    "ObservabilityContext",
]

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adapters – bridge concrete implementations to Protocol interfaces
# ---------------------------------------------------------------------------

class _TracingAdapter:
    """Adapts :func:`core.tracing.write_record` to the :class:`TraceWriter` protocol."""

    def write(self, record: dict, path: Optional[Path] = None) -> None:
        """Append *record* to the trace log.

        Parameters
        ----------
        record:
            Flat dict with W3C-shaped ids and tool-call metadata.
        path:
            Optional override for the default trace-log location.
        """
        from core import tracing as _tracing  # deferred to avoid circular imports
        _tracing.write_record(record, path)


class _EventAdapter:
    """Adapts :func:`core.events.publish` to the :class:`EventPublisher` protocol."""

    def publish(self, event: dict) -> None:
        """Fan-out *event* to all SSE subscribers.

        Parameters
        ----------
        event:
            Envelope dict.  The adapter calls :func:`core.events.publish`
            which redacts the payload before forwarding.
        """
        from core.events import publish as _publish  # deferred
        _publish(event)


# ---------------------------------------------------------------------------
# Dependency-injection container
# ---------------------------------------------------------------------------

@dataclass
class Container:
    """Dependency-injection container.  Initialised once at app startup.

    Required services (``settings``, ``trace_writer``, ``event_publisher``)
    are always present.  Optional services default to ``None`` when the
    underlying module is unavailable (e.g. ``mcp_servers``).
    """

    settings: Settings
    trace_writer: TraceWriter
    event_publisher: EventPublisher
    command_executor: Optional[CommandExecutor] = None
    observation_collector: Optional[ObservationCollector] = None
    knowledge_retriever: Optional[KnowledgeRetriever] = None


# Module-level singleton -----------------------------------------------

_container: Optional[Container] = None


def get_container() -> Container:
    """Return the application container.

    Raises
    ------
    RuntimeError
        If :func:`bootstrap` has not been called yet.
    """
    if _container is None:
        raise RuntimeError(
            "Container not initialised – call bootstrap() at startup."
        )
    return _container


# ---------------------------------------------------------------------------
# Bootstrap entry-point
# ---------------------------------------------------------------------------

def bootstrap(*, load_dotenv_: bool = True) -> Container:
    """Initialise application dependencies.

    Call once at startup.  Loads ``.env`` (if *load_dotenv_* is ``True`` and
    ``python-dotenv`` is installed), configures tracing, and wires all
    adapters into the container.

    Parameters
    ----------
    load_dotenv_:
        When ``True`` (the default) attempt to load ``.env`` via
        ``python-dotenv``.  A missing package is silently ignored,
        matching the pattern used in ``cli.py``.

    Returns
    -------
    Container
        Fully-wired dependency container.
    """
    global _container  # noqa: PLW0603

    # 1. Optionally load .env ------------------------------------------------
    if load_dotenv_:
        try:
            from dotenv import load_dotenv  # type: ignore[import-untyped]

            if settings.env_file.exists():
                load_dotenv(settings.env_file, override=False)
                _log.debug("Loaded .env from %s", settings.env_file)
        except ImportError:
            pass  # python-dotenv not installed – proceed with process env

    # 2. Core adapters -------------------------------------------------------
    trace_writer = _TracingAdapter()
    event_publisher = _EventAdapter()

    # 3. Optional adapters (fail-safe) ---------------------------------------
    command_executor: Optional[CommandExecutor] = None
    observation_collector: Optional[ObservationCollector] = None
    knowledge_retriever: Optional[KnowledgeRetriever] = None

    # 3a. CommandExecutor: wraps mcp_servers.srv_api_gateway_mcp._exec_command
    try:
        from mcp_servers.srv_api_gateway_mcp import _exec_command  # type: ignore[import-untyped]

        class _SrvCommandAdapter:
            """Adapts srv_api_gateway_mcp._exec_command to CommandExecutor."""

            def execute(self, command: str) -> dict:
                return _exec_command(command)

        command_executor = _SrvCommandAdapter()
        _log.debug("CommandExecutor wired via mcp_servers.srv_api_gateway_mcp")
    except Exception as exc:
        _log.warning(
            "Optional dependency 'command_executor' unavailable: %s", exc
        )

    # 3b. ObservationCollector: wraps hub_observability_mcp via fastmcp Client
    try:
        from mcp_servers.hub_observability_mcp import mcp as _obs_mcp  # type: ignore[import-untyped]
        from fastmcp import Client as _FastMCPClient  # type: ignore[import-untyped]

        class _ObservationAdapter:
            """Adapts hub_observability_mcp to ObservationCollector."""

            async def collect(self, environment: str) -> dict:
                async with _FastMCPClient(_obs_mcp) as client:
                    result = await client.call_tool(
                        "observe_hub", {"environment": environment}
                    )
                    if result.is_error:
                        raise RuntimeError("SOURCE_UNAVAILABLE")
                    return result.data

        observation_collector = _ObservationAdapter()
        _log.debug("ObservationCollector wired via mcp_servers.hub_observability_mcp")
    except Exception as exc:
        _log.warning(
            "Optional dependency 'observation_collector' unavailable: %s", exc
        )

    # 3c. KnowledgeRetriever: wraps core.retriever.BrainRetriever
    try:
        from core.retriever import BrainRetriever  # type: ignore[import-untyped]

        knowledge_retriever = BrainRetriever()
        _log.debug("KnowledgeRetriever wired via core.retriever")
    except Exception as exc:
        _log.warning(
            "Optional dependency 'knowledge_retriever' unavailable: %s", exc
        )

    # 4. Assemble container --------------------------------------------------
    _container = Container(
        settings=settings,
        trace_writer=trace_writer,
        event_publisher=event_publisher,
        command_executor=command_executor,
        observation_collector=observation_collector,
        knowledge_retriever=knowledge_retriever,
    )

    _log.info("Bootstrap complete – container ready.")
    return _container


# ---------------------------------------------------------------------------
# Per-request observability context
# ---------------------------------------------------------------------------

@dataclass
class ObservabilityContext:
    """Per-request observability context.

    Each incoming request (or graph traversal) creates an instance with a
    fresh ``trace_id`` and ``span_id``.  Child operations call
    :meth:`new_span` to obtain a derived context that shares the same
    ``trace_id`` but gets its own ``span_id``.
    """

    trace_id: str
    span_id: str
    server: str = "graph"
    started_at: str = field(default_factory=lambda: tracing.now_iso())
    token_count: int = 0
    node_visits: int = 0

    # -- factories -----------------------------------------------------------

    @classmethod
    def create(cls, *, server: str = "graph") -> ObservabilityContext:
        """Factory that generates fresh trace and span ids.

        Returns
        -------
        ObservabilityContext
            Ready-to-use context with cryptographically random ids.
        """
        return cls(
            trace_id=tracing.new_trace_id(),
            span_id=tracing.new_span_id(),
            server=server,
        )

    # -- mutation helpers ----------------------------------------------------

    def new_span(self) -> ObservabilityContext:
        """Create a child context with a new ``span_id`` but the same ``trace_id``."""
        return ObservabilityContext(
            trace_id=self.trace_id,
            span_id=tracing.new_span_id(),
            server=self.server,
            started_at=tracing.now_iso(),
        )

    def record_tokens(self, count: int) -> None:
        """Increment the token counter by *count*."""
        self.token_count += count

    def record_visit(self) -> None:
        """Increment the node-visit counter by one."""
        self.node_visits += 1
