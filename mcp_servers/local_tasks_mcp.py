import sys
from pathlib import Path
from typing import Any, Dict, Optional

from fastmcp import Context, FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings

try:
    from dotenv import load_dotenv
    if settings.env_file.exists():
        load_dotenv(settings.env_file, override=False)
except ImportError:
    pass

from core import tracing
from core.local_tasks import router
from core.trace_middleware import TraceMiddleware

mcp = FastMCP("Local tasks")
# Os argumentos destas ferramentas são o conteúdo da tarefa: o trace guarda só o tamanho.
mcp.add_middleware(TraceMiddleware("Local tasks", content_args=frozenset({"text", "document", "source"})))


def _sender(ctx: Optional[Context]) -> str:
    try:
        return ctx.session.client_params.client_info.name or "unknown"
    except Exception:
        return "unknown"


def _trace_id(task_id: Optional[str]) -> Optional[str]:
    """trace_id do envelope = o da chamada MCP: derivado do task_id ou o do middleware."""
    if task_id:
        return tracing.derive_trace_id(task_id)[0]
    state = tracing.current_call.get()
    return state.trace_id if state is not None else None


@mcp.tool()
def classify(text: str, ctx: Context, task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Classifica um texto com o vocabulário do perfil, usando um modelo local barato.
    Use antes de gastar um modelo pago. Devolve um envelope task.result;
    se status == 'escalate', faça a tarefa você mesmo.
    task_id: optional label that groups this call with others of the same task
    """
    return router.run_task("classify", text=text, sender=_sender(ctx), trace_id=_trace_id(task_id))


@mcp.tool()
def extract(text: str, template: str, ctx: Context, task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Extrai campos de um texto para um template estruturado (ex: 'nome@1'), usando um modelo local.
    Os templates disponíveis estão em local_tasks_status -> templates.
    Use antes de gastar um modelo pago. Devolve um envelope task.result;
    se status == 'escalate', faça a tarefa você mesmo.
    task_id: optional label that groups this call with others of the same task
    """
    return router.run_task("extract", text=text, template=template, sender=_sender(ctx),
                           trace_id=_trace_id(task_id))


@mcp.tool()
def summarize(text: str, ctx: Context, target_words: int = 120,
              task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Resume um texto em aproximadamente target_words palavras, usando um modelo local.
    Use antes de gastar um modelo pago. Devolve um envelope task.result;
    se status == 'escalate', faça a tarefa você mesmo.
    task_id: optional label that groups this call with others of the same task
    """
    return router.run_task("summarize", text=text, target_words=target_words,
                           sender=_sender(ctx), trace_id=_trace_id(task_id))


@mcp.tool()
def validate(document: str, template: str, ctx: Context, source: Optional[str] = None,
             task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Valida um documento contra um template (checagem determinística); com 'source', pede também
    uma revisão do modelo local contra a fonte. Use antes de gastar um modelo pago.
    Devolve um envelope task.result; se status == 'escalate', faça a tarefa você mesmo.
    task_id: optional label that groups this call with others of the same task
    """
    return router.run_task("validate", text=document, template=template, source=source,
                           sender=_sender(ctx), trace_id=_trace_id(task_id))


@mcp.tool()
def local_tasks_status(task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Mostra o estado do runtime local: perfil, modelo, disponibilidade do modelo, falhas de gravação
    de eventos e templates disponíveis. Use para checar se vale tentar o modelo local.
    event_write_failures conta só as falhas deste processo do servidor, desde que ele iniciou.
    task_id: optional label that groups this call with others of the same task
    """
    return router.status()


if __name__ == "__main__":
    mcp.run()
