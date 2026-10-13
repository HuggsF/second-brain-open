"""FastMCP middleware that records one trace record per tool call (see core/tracing.py)."""
import sys
import time
from pathlib import Path
from typing import Optional

from fastmcp.server.middleware import Middleware

from core import tracing


def _caller(context) -> str:
    try:
        return context.fastmcp_context.session.client_params.client_info.name or "unknown"
    except Exception:
        return "unknown"


class TraceMiddleware(Middleware):
    def __init__(self, server_name: str, path: Optional[Path] = None,
                 content_args: frozenset = frozenset()):
        self.server_name = server_name
        self.path = path
        # Arguments that are the content of the call: logged as {"chars": n}, never the text.
        self.content_args = frozenset(content_args)

    def _begin(self, context) -> Optional[tracing.CallState]:
        try:
            arguments = context.message.arguments or {}
            trace_id, label = tracing.derive_trace_id(arguments.get("task_id"))
            return tracing.CallState(
                trace_id=trace_id,
                span_id=tracing.new_span_id(),
                server=self.server_name,
                tool=context.message.name,
                path=self.path or tracing.TRACE_LOG,
                caller=_caller(context),
                task_label=label,
                started_at=tracing.now_iso(),
            )
        except Exception as exc:
            print(f"trace: could not start record ({type(exc).__name__})", file=sys.stderr)
            return None

    def _finish(self, context, state: tracing.CallState, started: float, error_type: Optional[str]) -> None:
        try:
            status = "error" if error_type else ("refused" if state.refused else "ok")
            tracing.write_record(
                {
                    "schema_version": 1,
                    "ts": state.started_at,  # when the call started; child events are later
                    "trace_id": state.trace_id,
                    "span_id": state.span_id,
                    "parent_span_id": None,
                    "task_label": state.task_label,
                    "server": state.server,
                    "tool": state.tool,
                    "event": "call",
                    "status": status,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "caller": state.caller,
                    "args": tracing.redact_args(context.message.arguments, self.content_args),
                    "error_type": error_type,
                },
                state.path,
            )
        except Exception as exc:
            print(f"trace: could not finish record ({type(exc).__name__})", file=sys.stderr)

    async def on_call_tool(self, context, call_next):
        state = self._begin(context)
        if state is None:
            return await call_next(context)
        token = tracing.current_call.set(state)
        started = time.perf_counter()
        error_type = None
        try:
            return await call_next(context)
        except BaseException as exc:
            # FastMCP wraps a tool's own exception in ToolError; the original is the useful type.
            error_type = type(exc.__cause__ or exc).__name__
            raise
        finally:
            tracing.current_call.reset(token)
            self._finish(context, state, started, error_type)
