"""Protocol interfaces (ports) for dependency inversion.

This module defines the abstract boundaries between the **core** domain layer
and the **infrastructure** layer (MCP servers, file I/O, network calls).

Motivation – Dependency Inversion Principle (DIP)
--------------------------------------------------
Without explicit ports the dependency graph contains two layer inversions:

1. ``core/tools.py`` → ``mcp_servers/command_gateway_mcp``  (core depends on infra)
2. ``backend/server.py`` → ``mcp_servers/observability_mcp`` (backend depends on infra)

By introducing Protocol-based ports **here in core**, we invert those arrows:

* The core layer depends only on these thin protocols.
* Infrastructure adapters implement the protocols and are injected at
  composition time (``main``, DI container, or test fixtures).

All protocols are ``@runtime_checkable`` so that ``isinstance`` guards work
at adapter registration time without requiring explicit subclassing.

Only stdlib and ``typing`` imports are used — this module has **zero**
project dependencies by design.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

__all__ = [
    "CommandExecutor",
    "EventPublisher",
    "KnowledgeRetriever",
    "ObservationCollector",
    "TraceWriter",
]


# ---------------------------------------------------------------------------
# CommandExecutor
# ---------------------------------------------------------------------------

@runtime_checkable
class CommandExecutor(Protocol):
    """Port for executing shell commands on a remote server.

    Replaces the direct import of
    ``mcp_servers.command_gateway_mcp._exec_command`` that previously coupled
    ``core/tools.py`` to a concrete MCP server implementation.

    Implementors must return a dictionary with at least the following keys:

    * **success** (``bool``) – whether the command exited cleanly.
    * **exit_code** (``int``) – process exit code.
    * **stdout** (``str``) – captured standard output.
    * **stderr** (``str``) – captured standard error.
    """

    def execute(self, command: str) -> dict:
        """Execute *command* and return a result dictionary.

        Parameters
        ----------
        command:
            The shell command string to execute.

        Returns
        -------
        dict
            A mapping containing ``success``, ``exit_code``, ``stdout``, and
            ``stderr`` entries.
        """
        ...


# ---------------------------------------------------------------------------
# ObservationCollector
# ---------------------------------------------------------------------------

@runtime_checkable
class ObservationCollector(Protocol):
    """Port for collecting observation data from environments.

    Replaces the direct import of ``mcp_servers.observability_mcp`` that
    previously coupled ``backend/server.py`` to a concrete MCP server
    implementation.

    Implementations typically gather metrics, logs, or health-check results
    from one or more monitored environments.
    """

    async def collect(self, environment: str) -> dict:
        """Collect observation data for *environment*.

        Parameters
        ----------
        environment:
            Logical name of the target environment (e.g. ``"production"``,
            ``"staging"``).

        Returns
        -------
        dict
            Environment-specific observation payload.  The exact schema is
            defined by the concrete adapter.
        """
        ...


# ---------------------------------------------------------------------------
# EventPublisher
# ---------------------------------------------------------------------------

@runtime_checkable
class EventPublisher(Protocol):
    """Port for publishing domain events.

    Abstracts the ``events.publish`` pattern so that the core domain can emit
    events without knowing whether they are dispatched in-process, queued to a
    broker, or simply logged.
    """

    def publish(self, event: dict) -> None:
        """Publish *event* to all registered subscribers.

        Parameters
        ----------
        event:
            A dictionary representing a domain event.  By convention it should
            contain at least ``type`` and ``timestamp`` keys.
        """
        ...


# ---------------------------------------------------------------------------
# TraceWriter
# ---------------------------------------------------------------------------

@runtime_checkable
class TraceWriter(Protocol):
    """Port for writing trace records.

    Abstracts ``tracing.write_record`` so that the core layer can persist
    trace data without depending on a concrete file/database writer.

    **Contract**: implementations **must never raise**.  Tracing is a
    cross-cutting concern that should not interrupt business logic.
    """

    def write(self, record: dict, path: Optional[Path] = None) -> None:
        """Write a trace *record*, optionally to a specific *path*.

        Parameters
        ----------
        record:
            Structured trace data to persist.
        path:
            Optional filesystem path override.  When ``None`` the
            implementation should use its default destination.
        """
        ...


# ---------------------------------------------------------------------------
# KnowledgeRetriever
# ---------------------------------------------------------------------------

@runtime_checkable
class KnowledgeRetriever(Protocol):
    """Port for querying the knowledge base.

    Abstracts ``BrainRetriever`` so that tools and backend handlers can search
    the knowledge graph without coupling to a specific storage engine or
    embedding model.
    """

    def query(
        self,
        query: str,
        limit: int = 5,
        category: str | None = None,
        include_content: bool = True,
    ) -> dict:
        """Search the knowledge base.

        Parameters
        ----------
        query:
            Natural-language search query.
        limit:
            Maximum number of results to return.
        category:
            Optional category filter (e.g. ``"runbook"``, ``"architecture"``).
        include_content:
            When ``True`` the full document content is returned alongside
            metadata; when ``False`` only metadata/scores are included.

        Returns
        -------
        dict
            Search results whose schema is defined by the concrete adapter
            (typically contains ``results``, ``total``, and ``query`` keys).
        """
        ...
