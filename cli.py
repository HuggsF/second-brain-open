import sys
import os
import re
import json
import math
import sqlite3
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
from core import ficha as ficha_core
from core.indice_texto import IndiceTexto
from core.evidence_store import EvidenceStore, EvidenceStoreError

console = Console(force_terminal=True)

@click.group()
def cli():
    """Second Brain CLI para Desenvolvedores"""
    pass

@cli.command()
@click.option("--rebuild", "do_rebuild", is_flag=True, help="Reconstrói o índice inteiro do Vault")
@click.option("--yes", "assume_yes", is_flag=True, help="Aceito e ignorado (compatibilidade com chamadas antigas)")
def sync(do_rebuild, assume_yes):
    """Sincroniza o Vault com o índice de busca."""
    banner = "Reconstruindo o índice do Vault..." if do_rebuild else "Sincronizando o Vault..."
    console.print(f"[bold yellow][*] {banner}[/bold yellow]")
    try:
        from core.sync_lock import SyncBusy
        from ingestion.sync import ReconstrucaoAbortada, SyncEngine
    except Exception as e:
        console.print(f"[bold red]Erro ao sincronizar:[/bold red] {e}")
        raise SystemExit(1)
    try:
        engine = SyncEngine()
        if do_rebuild:
            result = engine.rebuild(verbose=True)
            console.print(Panel(
                f"[bold green]Status da Reconstrução:[/bold green]\n"
                f"• Arquivos: {result['files']}\n"
                f"• Blocos: {result['chunks']}\n"
                f"• Esquema: {result['esquema']}",
                title="Reconstrução Concluída",
                border_style="green"
            ))
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
    except ReconstrucaoAbortada as e:
        click.echo("Reconstrução abortada: nenhum índice foi gravado ou alterado. Notas ilegíveis:")
        for arquivo in e.arquivos:
            click.echo(f"  {arquivo}")
        click.echo("Corrija ou remova essas notas (precisam ser texto UTF-8) e rode o sync de novo.")
        raise SystemExit(1)
    except FileNotFoundError as e:
        click.echo(f"{e}")
        click.echo("Crie a pasta ou aponte outra com a variável BRAIN_VAULT_DIR.")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[bold red]Erro ao sincronizar:[/bold red] {e}")
        raise SystemExit(1)

def _vault_ou_sai() -> None:
    if not settings.vault_dir.is_dir():
        click.echo(f"Pasta do vault não encontrada: {settings.vault_dir}")
        click.echo("Crie a pasta ou aponte outra com a variável BRAIN_VAULT_DIR.")
        raise SystemExit(1)


def _indice_ou_sai() -> IndiceTexto:
    """Índice pronto para leitura, ou mensagem do que fazer e saída 1."""
    indice = IndiceTexto()
    if not indice.caminho.exists():
        click.echo(f"Índice de busca não encontrado em {indice.caminho}. Rode 'cli.py sync'.")
        raise SystemExit(1)
    try:
        integro = indice.verificar()
    except Exception:
        click.echo(f"Não foi possível abrir o índice de busca em {indice.caminho}.")
        click.echo("Confira o caminho (variável BRAIN_INDEX_PATH) e rode 'cli.py sync --rebuild'.")
        raise SystemExit(1)
    if not integro:
        click.echo(f"Índice de busca em {indice.caminho}: Corrompido. Rode 'cli.py sync --rebuild'.")
        raise SystemExit(1)
    return indice


_MOTIVO_SEM_GERADOR = {
    "budget_daily": "orçamento do dia esgotado",
    "budget_monthly": "orçamento do mês esgotado",
    "profile_not_found": "perfil não encontrado ou inválido",
}


def _mostrar_lacunas(gaps) -> None:
    from core.citations import GAP_EMPTY_INDEX
    for gap in gaps:
        click.echo(gap)
        if gap == GAP_EMPTY_INDEX:
            click.echo("Rode 'cli.py sync' para indexar o vault.")


def _mostrar_fontes(sources) -> None:
    for src in sources:
        click.echo(f"{src['score']:8.2f}  {src['file_path']}  |  {src['section']}  |  linhas {src['line_start']}-{src['line_end']}")


@cli.command()
@click.argument("pergunta")
@click.option("--category", default=None, help="Filtrar por categoria (a pasta da nota dentro do vault)")
@click.option("--limite", default=5, type=click.IntRange(1, 50), show_default=True, help="Quantos trechos devolver")
def buscar(pergunta: str, category: str, limite: int):
    """Busca trechos do vault no índice de texto, sem chamar modelo nenhum."""
    _vault_ou_sai()
    indice = _indice_ou_sai()
    try:
        from core.retriever import BrainRetriever
        result = BrainRetriever(store=indice).query(pergunta, limit=limite, category=category)
    except Exception as e:
        click.echo(f"Erro na busca: {e}")
        raise SystemExit(1)
    if result["sources"]:
        click.echo("relevância  arquivo  |  seção  |  linhas")
        _mostrar_fontes(result["sources"])
    else:
        click.echo("Nada encontrado.")
    _mostrar_lacunas(result["gaps"])


@cli.command()
@click.argument("question")
@click.option("--category", default=None, help="Filtrar por categoria (a pasta da nota dentro do vault)")
def ask(question: str, category: str):
    """Busca no índice de texto e gera a resposta pela cadeia de provedores do perfil."""
    _vault_ou_sai()
    indice = _indice_ou_sai()
    try:
        from core.retriever import BrainRetriever
        result = BrainRetriever(store=indice).answer(question, category=category)
    except Exception as e:
        click.echo(f"Erro na consulta: {e}")
        raise SystemExit(1)
    if result["status"] == "ok":
        console.print(Panel(result["answer"], title="[bold green]Resposta[/bold green]", border_style="cyan"))
        quem = result["provider"] or f"servidor local ({result['model']})"
        click.echo(f"Gerado por: {quem} · custo US$ {result['cost_usd']:.4f}")
    else:
        click.echo(result["answer"])
    if result["status"] == "sem_gerador":
        motivo = result["motivo"]
        click.echo(f"Resposta não gerada: {_MOTIVO_SEM_GERADOR.get(motivo) or f'nenhum provedor respondeu ({motivo})'}.")
    _mostrar_lacunas(result["gaps"])
    if result["sources"]:
        click.echo("Fontes: relevância  arquivo  |  seção  |  linhas")
        _mostrar_fontes(result["sources"])
    if result["status"] == "sem_gerador":
        click.echo("Confira o perfil e o orçamento com 'cli.py budget'. 'cli.py buscar' não precisa de modelo.")
        raise SystemExit(1)


@cli.command()
def status():
    """Exibe o estado do índice de busca e do vault (sem consultar a rede)."""
    click.echo("Diagnóstico do Second Brain")
    if sqlite3.sqlite_version_info < (3, 43, 0):
        click.echo(f"SQLite: {sqlite3.sqlite_version} (o índice de busca pede 3.43 ou mais novo)")
    try:
        indice = IndiceTexto()
        integro = indice.verificar()
        stats = indice.estatisticas() if integro else {}
    except Exception as e:
        click.echo(f"Índice de busca: Erro — não foi possível ler o índice: {e}")
    else:
        if not integro:
            click.echo("Índice de busca: Corrompido — rode 'cli.py sync'")
        elif stats.get("points_count"):
            click.echo(
                f"Índice de busca: Pronto — {stats['points_count']} trechos em {stats['arquivos']} notas, "
                f"esquema {stats['esquema']}, construído em {stats['construido_em']}"
            )
        else:
            click.echo("Índice de busca: Vazio — rode 'cli.py sync'")
    if settings.vault_dir.is_dir():
        total_md = len(list(settings.vault_dir.rglob("*.md")))
        click.echo(f"Vault Markdown: Ativo — {total_md} documentos em {settings.vault_dir}")
    else:
        click.echo(f"Vault Markdown: Ausente — {settings.vault_dir} (aponte outro com BRAIN_VAULT_DIR)")
    click.echo(f"Servidor de modelos local (opcional, para ask e task): configurado em {settings.ollama_url}, não verificado")
    click.echo("Cadeia de provedores e orçamento: veja 'cli.py budget'")


@cli.command()
@click.option("--chat-model", default=settings.chat_model, help="Modelo de conversa a ser baixado")
def pull_models(chat_model: str):
    """Baixa o modelo de conversa no servidor local de modelos (usado só pelo ask)."""
    console.print(f"[bold cyan]Solicitando o modelo '{chat_model}' ao servidor local de modelos...[/bold cyan]")
    try:
        with httpx.Client(timeout=600.0) as client:
            with client.stream("POST", f"{settings.ollama_url}/api/pull", json={"name": chat_model}) as resp:
                if resp.status_code == 200:
                    for line in resp.iter_lines():
                        if line:
                            console.print(f"[dim]{line}[/dim]")
                    console.print(f"[bold green]Modelo '{chat_model}' pronto para uso.[/bold green]")
                else:
                    console.print(f"[bold red]Falha ao baixar o modelo {chat_model}: HTTP {resp.status_code}[/bold red]")
    except Exception as e:
        console.print(f"[bold red]Erro ao conectar ao servidor local de modelos:[/bold red] {e}")


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


def _emit_task(task: str, **kwargs):
    from core.local_tasks import router
    envelope = router.run_task(task, sender="cli", budget_tracker=_get_tracker(), **kwargs)
    click.echo(json.dumps(envelope, ensure_ascii=False, indent=2))
    raise SystemExit(_TASK_EXIT.get(envelope.get("status"), 1))


_ESTADO_ORCAMENTO = {"normal": "normal", "warning": "atenção", "critical": "crítico", "exceeded": "esgotado"}


@cli.command("budget")
@click.option("--history", "history_days", type=click.IntRange(1, 365), default=None, help="Mostra gasto por dia, últimos N dias")
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
        click.echo("Orçamento não configurado no perfil.")
        raise SystemExit(0)
    from core.budget import BudgetTracker
    from config import settings
    db_path = settings.base_dir / ".runtime" / "budget.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        tracker = BudgetTracker(db_path, profile.budget)
        if do_rebuild:
            _rebuild_budget(tracker, settings.base_dir)
            return
        if history_days is not None:
            for row in tracker.history(history_days):
                click.echo(f"  {row['date']}  US$ {row['actual_usd']:.4f}")
            return
        st = tracker.status()
    except sqlite3.Error:
        click.echo(f"Não foi possível ler o banco de orçamento em {db_path}.")
        click.echo("Apague esse arquivo e rode 'cli.py budget --rebuild' para refazê-lo a partir do log de eventos.")
        raise SystemExit(1)
    click.echo(f"Orçamento: {_ESTADO_ORCAMENTO.get(st.state, st.state)}")
    for rotulo, gasto, limite, saldo in (("Dia", st.daily_spent, st.daily_limit, st.daily_remaining),
                                         ("Mês", st.monthly_spent, st.monthly_limit, st.monthly_remaining)):
        pct = (gasto / limite * 100) if limite > 0 else 0
        click.echo(f"{rotulo}: US$ {gasto:.2f} de {limite:.2f} ({pct:.0f}%), saldo US$ {saldo:.2f}")


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
    if accuracy < min_accuracy:
        raise SystemExit(1)


@cli.group("ficha")
def ficha_grupo():
    """Fichas de projeto: documentação mínima, auditorias por etapa e processos."""


@ficha_grupo.command("nova")
@click.argument("slug")
@click.option("--nome", required=True, help="Nome do projeto, como aparece no resumo")
@click.option("--porte", required=True, type=click.Choice(ficha_core.PORTES), help="Define quais seções são obrigatórias")
def ficha_nova(slug, nome, porte):
    """Cria fichas/SLUG com os modelos das seções obrigatórias para o porte."""
    from datetime import date
    try:
        destino = ficha_core.criar(settings.fichas_dir, slug, nome, porte, date.today())
    except ficha_core.FichaRecusada as recusa:
        click.echo(f"Recusado: {recusa}")
        raise SystemExit(1)
    click.echo(f"Ficha criada em {destino}. Preencha as seções e rode: cli.py ficha validar {slug}")


@ficha_grupo.command("validar")
@click.argument("slug", required=False)
def ficha_validar(slug):
    """Valida uma ficha (ou todas); sai com 1 se houver problema."""
    if slug:
        pasta = settings.fichas_dir / slug
        if not re.match(r"^[a-z0-9][a-z0-9-]*$", slug) or not pasta.is_dir():
            click.echo(f"Ficha não encontrada: {slug}")
            raise SystemExit(1)
        resultados = [ficha_core.validar(pasta, settings.base_dir)]
    else:
        resultados = ficha_core.validar_todas(settings.fichas_dir, settings.base_dir)
        if not resultados:
            click.echo("Nenhuma ficha encontrada.")
    rotulos = {"ok": "ok", "nao_se_aplica": "não se aplica", "problema": "problema"}
    for r in resultados:
        click.echo(f"{r.slug}: {'válida' if r.valida else 'com problemas'}, situação {r.situacao}")
        for s in r.secoes:
            click.echo(f"  {s.numero:>2}  {ficha_core.ARQUIVOS[s.numero]:<22} {rotulos[s.situacao]}")
        for problema in r.problemas + [p for s in r.secoes for p in s.problemas]:
            click.echo(f"  - {problema}")
    raise SystemExit(0 if all(r.valida for r in resultados) else 1)


if __name__ == "__main__":
    # No Windows o click expande curingas dos argumentos; uma pergunta com "*" viraria lista de arquivos.
    cli(windows_expand_args=False)
