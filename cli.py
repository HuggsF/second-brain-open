import sys
import os
import re
import json
import math
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import settings

try:
    from dotenv import load_dotenv
    if settings.env_file.exists():
        load_dotenv(settings.env_file, override=False)
except ImportError:
    pass  # python-dotenv ausente: segue só com o ambiente do processo

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import httpx

from core import tracing
from core import evidence as evidence_core
from core.evidence_store import EvidenceStore, EvidenceStoreError
from core.qdrant_store import QdrantStore

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
@click.option("--reconcile", "do_reconcile", is_flag=True, help="Reconcilia o manifesto com o índice vetorial e corrige as diferenças")
@click.option("--rebuild", "do_rebuild", is_flag=True, help="Reconstrói o índice inteiro em uma coleção nova e troca o alias")
@click.option("--yes", "assume_yes", is_flag=True, help="Com --rebuild: confirma a migração da coleção atual para alias")
def sync(do_reconcile, do_rebuild, assume_yes):
    """Executa a sincronização diferencial do Vault com o Qdrant."""
    if do_reconcile and do_rebuild:
        raise click.UsageError("--reconcile e --rebuild não podem ser usados juntos")
    if assume_yes and not do_rebuild:
        raise click.UsageError("--yes só vale com --rebuild")
    if do_rebuild:
        banner = "Iniciando reconstrução do índice do Vault em uma coleção nova..."
    elif do_reconcile:
        banner = "Iniciando reconciliação do manifesto com o índice vetorial..."
    else:
        banner = "Iniciando sincronização diferencial do Vault..."
    console.print(f"[bold yellow][*] {banner}[/bold yellow]")
    try:
        from core.hasher import ManifestError
        from core.sync_lock import SyncBusy
        from ingestion.sync import LEGACY_INDEX_MESSAGE, LegacyIndexError, MigrationNeedsConfirmation, SyncEngine
    except Exception as e:
        console.print(f"[bold red]Erro ao sincronizar:[/bold red] {e}")
        raise SystemExit(1)
    try:
        engine = SyncEngine()
        if do_rebuild:
            result = engine.rebuild(verbose=True, confirm_migration=assume_yes)
            console.print(Panel(
                f"[bold green]Status da Reconstrução:[/bold green]\n"
                f"• Coleção: {result['collection']}\n"
                f"• Arquivos: {result['files']}\n"
                f"• Blocos: {result['chunks']}\n"
                f"• Migrou coleção para alias: {'sim' if result['migrated'] else 'não'}",
                title="Reconstrução Concluída",
                border_style="green"
            ))
            return
        if do_reconcile:
            result = engine.reconcile(verbose=True)
            failed = result.get("failed", 0)
            console.print(Panel(
                f"[bold green]Status da Reconciliação:[/bold green]\n"
                f"• Órfãos removidos: {result['orphans_removed']}\n"
                f"• Reindexados (faltavam no índice): {result['missing_reindexed']}\n"
                f"• Reindexados (fora do manifesto): {result['untracked_reindexed']}\n"
                f"• Falhas: {failed}",
                title="Reconciliação Concluída" if not failed else "Reconciliação com falhas",
                border_style="green" if not failed else "red"
            ))
            if failed:
                raise SystemExit(1)
            return
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
    except SyncBusy:
        click.echo("Outro sync está em andamento.")
        raise SystemExit(1)
    except ManifestError:
        click.echo("Manifesto ilegível; rode 'cli.py sync --rebuild'.")
        raise SystemExit(1)
    except LegacyIndexError:
        click.echo(LEGACY_INDEX_MESSAGE)
        raise SystemExit(1)
    except MigrationNeedsConfirmation:
        click.echo("A coleção atual vira alias nesta reconstrução e a busca falha por um instante. Rode de novo com --yes.")
        raise SystemExit(1)
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

        from core.citations import GAP_EMPTY_INDEX
        if GAP_EMPTY_INDEX in result.get("gaps", []):
            click.echo("Rode 'cli.py sync --rebuild' para reconstruir o índice deste espaço.")

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
                click.echo(f"  {playbook['id']}  {playbook['status']}  {playbook['environment']}  {playbook['kind']}  {playbook['title']}")
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
            click.echo(f"{rule['id']}  {rule['status']}  {rule['title']}  [{rule['state']}]  luz={rule['light']}  " + "  ".join(parts))
    except (EvidenceStoreError, ValueError) as exc:
        click.echo(f"Erro: {exc}")
        raise SystemExit(1)


_TASK_EXIT = {"ok": 0, "escalate": 2, "budget_exceeded": 3}
_GOLDEN_LOCAL_TASKS = Path(__file__).parent / "tests" / "golden_dataset_local_tasks.json"


def _read_text_file(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise click.ClickException(f"arquivo não está em UTF-8: {path}") from None


def _task_text(text, file_path):
    if (text is None) == (file_path is None):
        raise click.UsageError("informe exatamente um entre TEXT e --file")
    return text if text is not None else _read_text_file(file_path)



_budget_tracker_singleton = None
_budget_tracker_no_config = False  # True only when profile has no budget block


def _get_tracker():
    """Lazy singleton: creates BudgetTracker once from the active profile.

    If the SQLite open fails, returns a :class:`FailedBudgetTracker`
    sentinel that reports ``exceeded`` — blocking cloud calls on this
    invocation.  The real tracker is retried on the next call.
    """
    global _budget_tracker_singleton, _budget_tracker_no_config
    if _budget_tracker_singleton is not None:
        return _budget_tracker_singleton
    if _budget_tracker_no_config:
        return None
    budget_config = None
    try:
        from core.local_tasks.profile import load_profile
        profile = load_profile()
        if profile.budget is None:
            _budget_tracker_no_config = True
            return None
        budget_config = profile.budget
        from core.budget import BudgetTracker
        from config import settings
        db_path = settings.base_dir / ".runtime" / "budget.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _budget_tracker_singleton = BudgetTracker(db_path, profile.budget)
        return _budget_tracker_singleton
    except Exception:
        import logging
        logging.getLogger(__name__).warning("BudgetTracker init failed; will retry", exc_info=True)
        if budget_config is not None:
            from core.budget import FailedBudgetTracker
            return FailedBudgetTracker(budget_config)
        return None


def _emit_task(task: str, **kwargs):
    from core.local_tasks import router
    tracker = _get_tracker()
    envelope = router.run_task(task, sender="cli", budget_tracker=tracker, **kwargs)
    click.echo(json.dumps(envelope, ensure_ascii=False, indent=2))
    raise SystemExit(_TASK_EXIT.get(envelope.get("status"), 1))



@cli.command("budget")
@click.option("--history", "history_days", type=int, default=None, help="Mostra gasto por dia, últimos N dias")
@click.option("--rebuild", "do_rebuild", is_flag=True, help="Reconstrói budget.db a partir dos eventos")
def budget_cmd(history_days, do_rebuild):
    """Orçamento de chamadas pagas: gasto, limite, estado."""
    from core.local_tasks.profile import load_profile
    try:
        profile = load_profile()
    except Exception as exc:
        click.echo(f"Erro ao carregar o perfil: {exc}")
        raise SystemExit(1)
    if profile.budget is None:
        click.echo("Budget não configurado no perfil.")
        raise SystemExit(0)
    from core.budget import BudgetTracker
    from config import settings
    db_path = settings.base_dir / ".runtime" / "budget.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tracker = BudgetTracker(db_path, profile.budget)
    if do_rebuild:
        _rebuild_budget(tracker, settings.base_dir)
        return
    if history_days is not None:
        rows = tracker.history(history_days)
        for row in rows:
            click.echo(f"  {row['date']}  US$ {row['actual_usd']:.4f}")
        return
    st = tracker.status()
    click.echo(f"Budget status: {st.state}")
    daily_pct = (st.daily_spent / st.daily_limit * 100) if st.daily_limit > 0 else 0
    monthly_pct = (st.monthly_spent / st.monthly_limit * 100) if st.monthly_limit > 0 else 0
    click.echo(f"Daily:   US$ {st.daily_spent:.2f} / {st.daily_limit:.2f}  "
               f"({daily_pct:.0f}%)  remaining: US$ {st.daily_remaining:.2f}")
    click.echo(f"Monthly: US$ {st.monthly_spent:.2f} / {st.monthly_limit:.2f}  "
               f"({monthly_pct:.0f}%)  remaining: US$ {st.monthly_remaining:.2f}")


def _cost_number(value):
    """Valor de custo do evento para o rebuild: ausente ou ``null`` vale 0.0 (como o antigo
    ``or 0.0``); número finito que não seja bool vira ``float``; qualquer outro valor (texto,
    bool, NaN, inf) devolve ``None`` e a linha é pulada."""
    if value is None:
        return 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _rebuild_budget(tracker, base_dir):
    """Rebuild budget.db from all available events files."""
    from core.budget import _to_utc_iso
    events_log = base_dir / ".runtime" / "events.jsonl"
    # Read all rotated + current event files (oldest to newest)
    sources = []
    for i in range(3, 0, -1):
        rotated = events_log.with_name(f"{events_log.stem}.{i}{events_log.suffix}")
        if rotated.exists():
            sources.append(rotated)
    if events_log.exists():
        sources.append(events_log)
    # Phase 1: populate staging table (outside exclusive transaction)
    tracker.create_staging_table()
    count = 0
    ignored = 0  # linhas com JSON inválido, sem envelope_id ou sem ts válido: puladas
    totals = {}  # envelope_id -> actual_usd (o primeiro vence, como o INSERT OR IGNORE)
    for source_path in sources:
        try:
            text = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line in text.split("\n"):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                ignored += 1
                continue
            if not isinstance(record, dict):
                ignored += 1
                continue
            if record.get("kind") != "task.result":
                continue
            cost = record.get("cost")
            if cost is None:
                continue
            envelope_id = record.get("id")
            ts = record.get("ts")
            if not isinstance(cost, dict) or not envelope_id or not isinstance(ts, str):
                ignored += 1
                continue
            try:
                _to_utc_iso(ts)
            except ValueError:
                ignored += 1
                continue
            actual_usd = _cost_number(cost.get("actual_usd"))
            paid_equivalent_usd = _cost_number(cost.get("paid_equivalent_usd"))
            if actual_usd is None or paid_equivalent_usd is None:
                ignored += 1
                continue
            tracker.insert_staging(
                envelope_id=envelope_id,
                ts=ts,
                trace_id=record.get("trace_id"),
                task=record.get("task"),
                sender=record.get("from"),
                provider=cost.get("provider"),
                model=cost.get("model"),
                tier=cost.get("tier"),
                tokens_in=cost.get("tokens_in", 0),
                tokens_out=cost.get("tokens_out", 0),
                actual_usd=actual_usd,
                paid_equivalent_usd=paid_equivalent_usd,
            )
            if envelope_id not in totals:
                totals[envelope_id] = actual_usd
                count += 1
    tracker.commit_staging()
    # Phase 2: reconcile and swap (exclusive transaction)
    tracker.rebuild_reconcile()
    click.echo("\u26a0 A reconstru\u00e7\u00e3o cobre apenas o hist\u00f3rico "
               "dispon\u00edvel nos arquivos de eventos.")
    # Final report: soma do actual_usd dos registros reconstru\u00eddos (todos os per\u00edodos).
    total_usd = sum(totals.values())
    click.echo(f"Reconstru\u00eddo: {count} registros, ignoradas: {ignored}, "
               f"US$ {total_usd:.4f} acumulado.")

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
    """Estado do runtime local (mesmo de local_tasks_status).

    event_write_failures é contado por processo: aqui vale só para este comando;
    as falhas do servidor MCP aparecem em local_tasks_status.
    """
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


def _no_provider_message(info: dict) -> str:
    """Mensagem de saída do task-eval quando nenhum provedor do perfil pode responder."""
    providers = info.get("providers") or []
    if not providers:
        return (f"Nenhum provedor disponível: Ollama indisponível ({info['local_model']}). "
                "Inicie o Ollama e baixe o modelo antes de avaliar.")
    parts = []
    for p in providers:
        state = "sem chave" if not p["configured"] else ("ok" if p["available"] else "indisponível")
        parts.append(f"{p['name']} ({p['model']}): {state}")
    return ("Nenhum provedor disponível no perfil " + str(info.get("profile")) + ": "
            + "; ".join(parts) + ". Defina a chave no arquivo de ambiente ou inicie o Ollama antes de avaliar.")


@cli.command("task-eval")
@click.option("--min-accuracy", type=float, default=0.6, show_default=True, help="Acerto geral mínimo; abaixo disso sai com 1")
@click.option("--profile", "profile_name", default=None, help="Nome do perfil (padrão: perfil ativo)")
def task_eval(min_accuracy, profile_name):
    """Avalia as tarefas locais contra tests/golden_dataset_local_tasks.json."""
    from core.local_tasks import router
    eval_tracker = None
    try:
        profile = router.load_profile(profile_name)
        client = router.build_client(profile)
        info = router.status(profile)  # sondagem curta
        if profile.budget is not None:
            from core.budget import BudgetTracker
            from config import settings
            db_path = settings.base_dir / ".runtime" / "budget.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            eval_tracker = BudgetTracker(db_path, profile.budget)
    except Exception as exc:
        click.echo(f"Erro ao preparar a avaliação: {exc}")
        raise SystemExit(1)
    if not info["model_available"]:
        click.echo(_no_provider_message(info))
        raise SystemExit(1)
    cases = json.loads(_GOLDEN_LOCAL_TASKS.read_text(encoding="utf-8"))
    stats: dict = {}
    for case in cases:
        envelope = router.run_task(
            case["task"], text=case["text"], template=case.get("template"),
            target_words=case.get("target_words", 120), source=case.get("source"),
            sender="task-eval", profile=profile, client=client,
            budget_tracker=eval_tracker,
        )
        row = stats.setdefault(case["task"], {"cases": 0, "passed": 0, "escalate": 0,
                                                "ms_total": 0, "tiers": {}})
        row["cases"] += 1
        row["passed"] += int(_case_passed(case, envelope))
        row["escalate"] += int(envelope.get("status") == "escalate")
        cost = envelope.get("cost") or {}
        row["ms_total"] += cost.get("ms", 0)
        tier = cost.get("tier", "unknown")
        row["tiers"][tier] = row["tiers"].get(tier, 0) + 1
    for name, row in stats.items():
        avg_ms = row["ms_total"] / row["cases"] if row["cases"] else 0
        tiers_str = " ".join(f"{t}={c}" for t, c in sorted(row["tiers"].items()))
        click.echo(f"{name}: casos={row['cases']} acertos={row['passed']} escalate={row['escalate']} "
                   f"acerto={row['passed'] / row['cases']:.0%} latência_média_ms={avg_ms:.0f} {tiers_str}")
    total = sum(r["cases"] for r in stats.values())
    accuracy = sum(r["passed"] for r in stats.values()) / total if total else 0.0
    click.echo(f"Acerto geral: {accuracy:.0%} (mínimo {min_accuracy:.0%})")
    if eval_tracker is not None:
        bst = eval_tracker.status()
        if bst.state == "exceeded":
            click.echo(f"⚠ Budget excedido durante a avaliação "
                        f"(US$ {bst.daily_spent:.2f} / {bst.daily_limit:.2f} diário).")
    if accuracy < min_accuracy:
        raise SystemExit(1)



REPORTS_DIR = Path(__file__).resolve().parent / "evals" / "reports"


@cli.command("retrieval-eval")
@click.option("--min-recall", type=float, default=0.8, show_default=True, help="Recall mínimo da sugestão; abaixo disso sai com 1")
@click.option("--dataset", "dataset_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None,
              help="Golden dataset YAML (padrão: evals/golden_dataset.yaml)")
@click.option("--k", "k", type=click.IntRange(min=1), default=5, show_default=True, help="Trechos considerados por consulta")
def retrieval_eval_cmd(min_recall, dataset_path, k):
    """Mede recall dos positivos e negativos sem fonte numa grade de pisos e sugere o piso (precisa de Qdrant e Ollama)."""
    from datetime import datetime
    from evals import retrieval_eval as ev

    dataset = dataset_path or Path(__file__).resolve().parent / "evals" / "golden_dataset.yaml"
    positives, negatives = ev.load_cases(dataset)
    click.echo(f"Avaliando {len(positives)} consultas positivas e {len(negatives)} negativas (k={k})...")
    from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
    try:
        from core.retriever import BrainRetriever
        collected = ev.collect(BrainRetriever(), positives, negatives, k=k)
    except (httpx.HTTPError, ResponseHandlingException, UnexpectedResponse, RuntimeError, OSError) as exc:
        click.echo(f"Erro ao consultar o Qdrant/Ollama: {exc}. Confira se os serviços estão no ar e rode de novo.", err=True)
        raise SystemExit(1)
    rows = ev.grid(collected, ev.DEFAULT_MINS, ev.DEFAULT_DROPS, k=k)
    best = ev.suggest(rows)

    table = Table(title="Grade de pisos", show_header=True, header_style="bold magenta")
    for column in ("min_score", "max_drop", f"recall@{k}", "negativos sem fonte"):
        table.add_column(column, justify="right")
    for row in rows:
        mark = "  <-" if best is not None and row == best else ""
        table.add_row(f"{row['min_score']:.2f}", f"{row['max_drop']:.2f}",
                      f"{row['recall_at_k']:.0%}", f"{row['negatives_cleared']:.0%}{mark}")
    console.print(table)

    report = {"generated_at": datetime.now().isoformat(timespec="seconds"), "k": k, "min_recall": min_recall,
              "dataset": str(dataset), "positives": len(positives), "negatives": len(negatives),
              "rows": rows, "suggestion": best, "collected": collected}
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"retrieval-{datetime.now():%Y%m%d-%H%M}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    click.echo(f"Relatório gravado em {report_path}")

    if best is None:
        click.echo("Nenhum par da grade limpa todos os negativos; não há piso a sugerir.")
        raise SystemExit(1)
    click.echo(f"Sugestão: RETRIEVAL_MIN_SCORE={best['min_score']:.2f} RETRIEVAL_MAX_DROP={best['max_drop']:.2f} "
               f"(recall@{k} {best['recall_at_k']:.0%}, negativos sem fonte {best['negatives_cleared']:.0%})")
    if best["recall_at_k"] < min_recall:
        click.echo(f"Recall {best['recall_at_k']:.0%} abaixo do mínimo {min_recall:.0%}.")
        raise SystemExit(1)


@cli.command("etl")
@click.option("--days", type=int, default=7, show_default=True, help="Dias de dados a extrair (1-90)")
@click.option("--environment", default="production", type=click.Choice(["production", "hml"]), help="Ambiente do Hub")
def etl_cmd(days, environment):
    """Executa o pipeline ETL para extrair dados analíticos do Hub Logístico."""
    from core.analytics_etl import extract_and_store
    result = extract_and_store(days, environment)
    console.print_json(json.dumps(result))


from scripts.sanitize import sanitize_cmd
cli.add_command(sanitize_cmd, "sanitize")

if __name__ == "__main__":
    cli()
