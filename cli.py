import sys
import os
import re
import json
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import httpx

from config import settings
from core import tracing
from core import evidence as evidence_core
from core.evidence_store import EvidenceStore, EvidenceStoreError

console = Console(force_terminal=True)

@click.group()
def cli():
    """KIOSK Brands - Second Brain CLI para Desenvolvedores"""
    pass

@cli.command("drive-sync")
@click.option("--folder-id", default=None, help="ID da pasta do Google Drive (opcional)")
def drive_sync_cmd(folder_id: str):
    """Sincroniza documentos do Google Drive com o Vault, extrai texto e atualiza o grafo."""
    from ingestion.drive_sync import DriveSyncEngine
    engine = DriveSyncEngine(folder_id=folder_id)
    engine.run()

@cli.command()
def sync():
    """Executa a sincronização diferencial do Vault com o Qdrant."""
    console.print("[bold yellow][*] Iniciando sincronização diferencial do Vault...[/bold yellow]")
    try:
        from ingestion.sync import SyncEngine
        engine = SyncEngine()
        result = engine.sync_vault(verbose=True)
        console.print(Panel(
            f"[bold green]Status da Sincronização:[/bold green]\n"
            f"• Arquivos Novos: {result['added']}\n"
            f"• Arquivos Modificados: {result['modified']}\n"
            f"• Arquivos Removidos: {result['deleted']}\n"
            f"• Blocos Indexados: {result['chunks_indexed']}\n"
            f"• Falhas: {result.get('failed', 0)}",
            title="Sincronização Concluída" if not result.get("failed") else "Sincronização com falhas",
            border_style="green" if not result.get("failed") else "red"
        ))
        if result.get("failed"):
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[bold red]Erro ao sincronizar:[/bold red] {e}")
        raise SystemExit(1)

@cli.command()
@click.argument("question")
@click.option("--category", default=None, help="Filtrar por categoria (adrs, systems, domain, daily)")
def ask(question: str, category: str):
    """Consulta a base de conhecimento técnica e responde com RAG local."""
    console.print(f"[bold cyan]🔍 Consultando Second Brain:[/bold cyan] '{question}'\n")
    try:
        from core.retriever import BrainRetriever
        retriever = BrainRetriever()
        result = retriever.answer(question, category=category)

        # Exibir resposta
        console.print(Panel(
            result["answer"],
            title="[bold green]Resposta do Assistente Técnico[/bold green]",
            border_style="cyan"
        ))

        # Exibir fontes citadas
        if result["sources"]:
            table = Table(title="Fontes Consultadas", show_header=True, header_style="bold magenta")
            table.add_column("Arquivo", style="dim")
            table.add_column("Seção")
            table.add_column("Relevância")

            for src in result["sources"]:
                table.add_row(src["file_path"], src["section"], f"{src['score']:.2f}")

            console.print(table)
    except Exception as e:
        console.print(f"[bold red]Erro na consulta:[/bold red] {e}")

@cli.command()
def status():
    """Exibe o status dos serviços locais (Qdrant, Ollama, Vault)."""
    console.print("[bold]Diagnóstico do Second Brain - KIOSK Brands[/bold]\n")

    # 1. Checar Qdrant
    qdrant = QdrantStore()
    stats = qdrant.get_stats()
    
    table = Table(title="Serviços Locais", show_header=True, header_style="bold blue")
    table.add_column("Serviço")
    table.add_column("Status")
    table.add_column("Detalhes")

    if "error" not in stats:
        table.add_row("Qdrant Vector DB", "[green]Online[/green]", f"Coleção '{stats['collection']}': {stats['points_count']} vetores")
    else:
        table.add_row("Qdrant Vector DB", "[red]Offline[/red]", stats["error"])

    # 2. Checar Ollama
    try:
        with httpx.Client(timeout=3.0) as client:
            resp = client.get(f"{settings.ollama_url}/api/tags")
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                table.add_row("Ollama Engine", "[green]Online[/green]", f"Modelos disponíveis: {', '.join(models) if models else 'Nenhum'}")
            else:
                table.add_row("Ollama Engine", "[yellow]Degradado[/yellow]", f"Status HTTP {resp.status_code}")
    except Exception as e:
        table.add_row("Ollama Engine", "[red]Offline[/red]", f"Não foi possível conectar: {e}")

    # 3. Vault
    total_md = len(list(settings.vault_dir.rglob("*.md")))
    table.add_row("Vault Markdown", "[green]Ativo[/green]", f"{total_md} documentos em {settings.vault_dir}")

    console.print(table)

@cli.command()
@click.option("--embed-model", default=settings.embedding_model, help="Modelo de embedding a ser baixado")
@click.option("--chat-model", default=settings.chat_model, help="Modelo de chat/raciocínio a ser baixado")
def pull_models(embed_model: str, chat_model: str):
    """Baixa os modelos necessários (embeddings e chat) diretamente no Ollama."""
    for model_name in [embed_model, chat_model]:
        console.print(f"[bold cyan]📥 Solicitando download do modelo '{model_name}' no Ollama...[/bold cyan]")
        try:
            with httpx.Client(timeout=600.0) as client:
                with client.stream("POST", f"{settings.ollama_url}/api/pull", json={"name": model_name}) as resp:
                    if resp.status_code == 200:
                        for line in resp.iter_lines():
                            if line:
                                console.print(f"[dim]{line}[/dim]")
                        console.print(f"[bold green]✔ Modelo '{model_name}' pronto para uso![/bold green]")
                    else:
                        console.print(f"[bold red]Falha ao baixar modelo {model_name}: HTTP {resp.status_code}[/bold red]")
        except Exception as e:
            console.print(f"[bold red]Erro ao conectar ao Ollama:[/bold red] {e}")

def _trace_log_path():
    return tracing.TRACE_LOG


def _by_start(records: list) -> list:
    """A call is written when it ends but stamped with when it started; order by that stamp
    (stable; at an equal stamp the call precedes its children), so a call is listed before the
    child events that happened inside it."""
    return sorted(records, key=lambda r: (str(r.get("ts", "")), 1 if r.get("parent_span_id") else 0))


def _trace_line(record: dict, with_trace_id: bool = False) -> str:
    """One metadata-only line per record; argument values are never printed."""
    duration = record.get("duration_ms")
    parts = [
        str(record.get("ts", "")),
        (str(record.get("trace_id", ""))[:8] if with_trace_id else ""),
        str(record.get("server", "")),
        str(record.get("tool", "")),
        str(record.get("event", "")),
        str(record.get("status", "")),
        (f"{duration}ms" if duration is not None else ""),
        (f"task={record['task_label']}" if record.get("task_label") else ""),
    ]
    line = "  ".join(p for p in parts if p)
    return ("  " + line) if record.get("parent_span_id") else line


@cli.command()
@click.argument("trace_id", required=False)
@click.option("--recent", "recent", type=int, default=None, help="Lista os últimos N registos (padrão 20 sem TRACE_ID)")
def trace(trace_id, recent):
    """Mostra a cadeia de chamadas MCP de uma tarefa (TRACE_ID) ou os registos mais recentes."""
    path = _trace_log_path()
    if trace_id and recent is not None:
        raise click.UsageError("use TRACE_ID ou --recent, não ambos")
    if trace_id:
        if not re.fullmatch(r"[0-9a-f]{32}", trace_id):
            click.echo("Identificador inválido: esperado 32 caracteres hexadecimais minúsculos.")
            raise SystemExit(1)
        records = _by_start(tracing.read_trace(trace_id, path))
        if not records:
            click.echo(f"Nenhum registo para {trace_id}")
            raise SystemExit(1)
        for record in records:
            click.echo(_trace_line(record))
        return
    records = _by_start(tracing.read_recent(20 if recent is None else recent, path))
    if not records:
        click.echo("Registo vazio: nenhuma chamada MCP registada.")
        return
    for record in records:
        click.echo(_trace_line(record, with_trace_id=True))


_NO_EVIDENCE = "sem evidência ainda"


def _evidence_context():
    """(definitions, execution store, seed file); a function so tests can replace it."""
    return (evidence_core.load_definitions(), EvidenceStore(),
            settings.base_dir / "evidence" / "seed-executions.json")


def _execution_line(row: dict) -> str:
    trace = f"trace={str(row['trace_id'])[:8]}" if row.get("trace_id") else ""
    summary = str(row.get("summary", ""))[:120]
    return "    " + "  ".join(p for p in (row["ts"], row["result"], row["source"], row["environment"], trace, summary) if p)


@cli.command()
@click.argument("rule_id", required=False)
@click.option("--lint", "do_lint", is_flag=True, help="Verifica regras, playbooks e execuções; sai com 1 se houver problemas")
@click.option("--import-seed", "do_import", is_flag=True, help="Importa as execuções históricas de evidence/seed-executions.json")
def evidence(rule_id, do_lint, do_import):
    """Árvore de evidências: regras, playbooks e execuções (sem argumentos lista as regras)."""
    if sum(bool(x) for x in (rule_id, do_lint, do_import)) > 1:
        raise click.UsageError("use apenas um entre RULE_ID, --lint e --import-seed")
    try:
        defs, store, seed_path = _evidence_context()
        if do_lint:
            problems = evidence_core.lint(defs, store)
            for problem in problems:
                click.echo(problem)
            if not problems:
                click.echo("sem problemas")
            raise SystemExit(1 if problems else 0)
        if do_import:
            added, skipped = evidence_core.import_seed(defs, store, seed_path)
            click.echo(f"Execuções importadas: {added}; ignoradas: {skipped}")
            return
        if rule_id:
            data = evidence_core.rule_evidence(defs, store, rule_id, 5)
            if "error" in data:
                click.echo(data["error"])
                raise SystemExit(1)
            rule = data["rule"]
            click.echo(f"{rule['id']}  {rule['status']}  {rule['title']}")
            click.echo(f"  origem: {rule['source']}")
            for playbook in data["playbooks"]:
                click.echo(f"  {playbook['id']}  {playbook['status']}  {playbook['environment']}  {playbook['title']}")
                for row in playbook["executions"]:
                    click.echo(_execution_line(row))
                if playbook.get("note"):
                    click.echo(f"    {playbook['note']}")
            return
        for rule in evidence_core.list_rules(defs, store):
            parts = []
            for playbook_id in rule["playbooks"]:
                latest = rule["playbook_latest"][playbook_id]
                parts.append(f"{playbook_id}={latest['result']}({latest['environment']})" if latest else f"{playbook_id}={_NO_EVIDENCE}")
            click.echo(f"{rule['id']}  {rule['status']}  {rule['title']}  [{rule['state']}]  " + "  ".join(parts))
    except (EvidenceStoreError, ValueError) as exc:
        click.echo(f"Erro: {exc}")
        raise SystemExit(1)


_TASK_EXIT = {"ok": 0, "escalate": 2}
_GOLDEN_LOCAL_TASKS = Path(__file__).parent / "tests" / "golden_dataset_local_tasks.json"


def _read_text_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8-sig")


def _task_text(text, file_path):
    if (text is None) == (file_path is None):
        raise click.UsageError("informe exatamente um entre TEXT e --file")
    return text if text is not None else _read_text_file(file_path)


def _emit_task(task: str, **kwargs):
    from core.local_tasks import router
    envelope = router.run_task(task, sender="cli", **kwargs)
    click.echo(json.dumps(envelope, ensure_ascii=False, indent=2))
    raise SystemExit(_TASK_EXIT.get(envelope.get("status"), 1))


@cli.group()
def task():
    """Tarefas pequenas executadas pelo modelo local."""


@task.command("classify")
@click.argument("text", required=False)
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False), default=None, help="Lê o texto de um arquivo UTF-8")
def task_classify(text, file_path):
    _emit_task("classify", text=_task_text(text, file_path))


@task.command("extract")
@click.option("--template", required=True, help="Template, ex.: adr@1")
@click.argument("text", required=False)
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False), default=None, help="Lê o texto de um arquivo UTF-8")
def task_extract(template, text, file_path):
    _emit_task("extract", text=_task_text(text, file_path), template=template)


@task.command("summarize")
@click.option("--words", "words", type=int, default=120, show_default=True, help="Tamanho alvo do resumo, em palavras")
@click.argument("text", required=False)
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False), default=None, help="Lê o texto de um arquivo UTF-8")
def task_summarize(words, text, file_path):
    _emit_task("summarize", text=_task_text(text, file_path), target_words=words)


@task.command("validate")
@click.option("--template", required=True, help="Template, ex.: adr@1")
@click.option("--source", "source_path", type=click.Path(exists=True, dir_okay=False), default=None, help="Fonte para conferência pelo modelo")
@click.argument("text", required=False)
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False), default=None, help="Lê o documento de um arquivo UTF-8")
def task_validate(template, source_path, text, file_path):
    document = _task_text(text, file_path)
    source = _read_text_file(source_path) if source_path else None
    _emit_task("validate", text=document, template=template, source=source)


@task.command("status")
def task_status():
    """Estado do runtime local (mesmo de local_tasks_status)."""
    from core.local_tasks import router
    click.echo(json.dumps(router.status(), ensure_ascii=False, indent=2))


def _case_passed(case: dict, envelope: dict) -> bool:
    if envelope.get("status") != "ok":
        return False
    payload = envelope.get("payload") or {}
    expect = case.get("expect") or {}
    if "labels" in expect:
        labels = payload.get("labels") or {}
        if any(labels.get(k) != v for k, v in expect["labels"].items()):
            return False
    if "required_keys" in expect and any(k not in payload for k in expect["required_keys"]):
        return False
    if "min_points" in expect and len(payload.get("key_points") or []) < expect["min_points"]:
        return False
    if "valid" in expect and payload.get("valid") != expect["valid"]:
        return False
    return True


@cli.command("task-eval")
@click.option("--min-accuracy", type=float, default=0.6, show_default=True, help="Acerto geral mínimo; abaixo disso sai com 1")
def task_eval(min_accuracy):
    """Avalia as tarefas locais contra tests/golden_dataset_local_tasks.json."""
    from core.local_tasks import router
    try:
        profile = router.load_profile()
        client = router.OllamaClient(timeout=profile.timeout_seconds)
        info = router.status(profile, client)
    except Exception as exc:
        click.echo(f"Erro ao preparar a avaliação: {exc}")
        raise SystemExit(1)
    if not info["model_available"]:
        click.echo(f"Modelo local indisponível ({info['local_model']}): inicie o Ollama e baixe o modelo antes de avaliar.")
        raise SystemExit(1)
    cases = json.loads(_GOLDEN_LOCAL_TASKS.read_text(encoding="utf-8"))
    stats: dict = {}
    for case in cases:
        envelope = router.run_task(
            case["task"], text=case["text"], template=case.get("template"),
            target_words=case.get("target_words", 120), source=case.get("source"),
            sender="cli", profile=profile, client=client,
        )
        row = stats.setdefault(case["task"], {"cases": 0, "passed": 0, "escalate": 0})
        row["cases"] += 1
        row["passed"] += int(_case_passed(case, envelope))
        row["escalate"] += int(envelope.get("status") == "escalate")
    for name, row in stats.items():
        click.echo(f"{name}: casos={row['cases']} acertos={row['passed']} escalate={row['escalate']} "
                   f"acerto={row['passed'] / row['cases']:.0%}")
    total = sum(r["cases"] for r in stats.values())
    accuracy = sum(r["passed"] for r in stats.values()) / total if total else 0.0
    click.echo(f"Acerto geral: {accuracy:.0%} (mínimo {min_accuracy:.0%})")
    if accuracy < min_accuracy:
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
