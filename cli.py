import sys
import os

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
from ingestion.sync import SyncEngine
from core.retriever import BrainRetriever
from core.qdrant_store import QdrantStore

console = Console(force_terminal=True)

@click.group()
def cli():
    """KIOSK Brands - Second Brain CLI para Desenvolvedores"""
    pass

@cli.command()
def sync():
    """Executa a sincronização diferencial do Vault com o Qdrant."""
    console.print("[bold yellow][*] Iniciando sincronização diferencial do Vault...[/bold yellow]")
    try:
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

if __name__ == "__main__":
    cli()
