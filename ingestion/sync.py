import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import hashlib
from pathlib import Path
from typing import Any, Dict
from rich.console import Console

from config import settings
from core.chunker import MarkdownChunker
from core.hasher import diferenca
from core.indice_texto import IndiceTexto, eh_corrupcao, esquema_indice
from core.sync_lock import sync_lock

console = Console(force_terminal=True)

DEFAULT_LOCK_PATH = settings.base_dir / ".runtime" / "sync.lock"


class ReconstrucaoAbortada(RuntimeError):
    """Alguma nota não pôde ser lida: a reconstrução não toca o índice.

    `arquivos` traz os caminhos relativos das notas ilegíveis.
    """

    def __init__(self, arquivos: list[str]):
        self.arquivos = list(arquivos)
        super().__init__(
            f"Reconstrução abortada: {len(self.arquivos)} arquivo(s) ilegíveis: {', '.join(self.arquivos)}"
        )


class SyncEngine:
    def __init__(
        self,
        lock_path: Path = DEFAULT_LOCK_PATH,
        lock_wait: float = 0.0,
        store: IndiceTexto | None = None,
        vault_dir: Path | None = None,
    ):
        self.chunker = MarkdownChunker()
        self.store = store if store is not None else IndiceTexto()
        self.vault_dir = Path(vault_dir) if vault_dir is not None else settings.vault_dir
        self.lock_path = Path(lock_path)
        self.lock_wait = lock_wait

    def sync_vault(self, verbose: bool = True) -> Dict[str, Any]:
        """Sincroniza o vault Markdown com o índice de texto.

        Roda dentro do lock do sistema operacional; outro sync em andamento -> `SyncBusy`.
        Esquema do índice diferente do atual (ou índice ausente/corrompido) reconstrói tudo.
        """
        with sync_lock(self.lock_path, self.lock_wait):
            return self._sync_unlocked(verbose)

    def rebuild(self, verbose: bool = True) -> Dict[str, Any]:
        """Reconstrói o índice inteiro numa transação. Devolve `{"files", "chunks", "esquema"}`.

        Nota ilegível -> `ReconstrucaoAbortada` e o índice fica como estava.
        Pasta do vault inexistente -> `FileNotFoundError`, sem tocar o índice.
        """
        with sync_lock(self.lock_path, self.lock_wait):
            return self._rebuild_unlocked(verbose)

    def reconcile(self, verbose: bool = True) -> Dict[str, Any]:
        """Hoje reconstrói o índice; devolve o mesmo que `rebuild`."""
        return self.rebuild(verbose=verbose)

    def _exigir_vault(self) -> None:
        # `rglob` numa pasta inexistente devolve vazio: sem esta checagem o sync apagaria o índice.
        if not self.vault_dir.is_dir():
            raise FileNotFoundError(f"Pasta do vault não encontrada: {self.vault_dir}")

    def _rebuild_unlocked(self, verbose: bool) -> Dict[str, Any]:
        self._exigir_vault()
        itens = []
        ilegiveis = []
        for file_path in sorted(self.vault_dir.rglob("*.md")):
            rel_path = file_path.relative_to(self.vault_dir).as_posix()
            try:
                sha, chunks = self._read_and_chunk(file_path, rel_path)
            except (OSError, UnicodeDecodeError) as e:
                ilegiveis.append(rel_path)
                console.print(f"[bold red]Erro ao ler {rel_path}:[/bold red] {e}")
                continue
            itens.append((rel_path, sha, chunks))
        if ilegiveis:
            raise ReconstrucaoAbortada(ilegiveis)
        contagem = self.store.reconstruir(itens)
        if verbose:
            console.print(
                f"[green][OK] Reconstrução concluída:[/green] {contagem['files']} arquivos, "
                f"{contagem['chunks']} blocos"
            )
        return {"files": contagem["files"], "chunks": contagem["chunks"], "esquema": esquema_indice()}

    def _read_and_chunk(self, file_path: Path, rel_path: str):
        """Leitura única: o hash devolvido é o dos mesmos bytes que geram os chunks.

        Devolve `(sha256, chunks)`; erro de leitura levanta `OSError`, bytes fora de UTF-8
        levantam `UnicodeDecodeError`.
        """
        raw = file_path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        chunks = self.chunker.chunk_bytes(raw, rel_path, self.vault_dir)
        # Procedência no metadado: o mesmo hash do manifesto e o espaço.
        for chunk in chunks:
            chunk["metadata"]["doc_sha256"] = sha
            chunk["metadata"]["space_id"] = settings.space_id
        return sha, chunks

    def _sync_reconstruindo(self, verbose: bool) -> Dict[str, Any]:
        contagem = self._rebuild_unlocked(verbose)
        return {
            "added": contagem["files"],
            "modified": 0,
            "deleted": 0,
            "chunks_indexed": contagem["chunks"],
            "failed": 0,
            "failed_files": [],
            "reconstruido": True,
        }

    def _sync_unlocked(self, verbose: bool = True) -> Dict[str, Any]:
        """Sync incremental; quem chama já segura o lock.

        Índice corrompido (esquema legível, tabelas não, ou prova de integridade que falha)
        -> reconstrução completa no mesmo lock, no máximo uma por sync.
        Pasta do vault inexistente -> `FileNotFoundError`, sem tocar o índice.
        """
        self._exigir_vault()
        if self.store.esquema_atual() != esquema_indice():
            if verbose:
                console.print("[bold cyan]Índice ausente ou de outro esquema: reconstruindo.[/bold cyan]")
            return self._sync_reconstruindo(verbose)
        # A leitura trata corrupção como vazio: sem a prova, um índice com contagens normais e
        # busca vazia passaria por sincronizado.
        if self.store.caminho.exists() and not self.store.verificar():
            console.print("[bold yellow]Índice corrompido: reconstruindo.[/bold yellow]")
            return self._sync_reconstruindo(verbose)
        try:
            return self._sync_incremental(verbose)
        except Exception as exc:
            if not eh_corrupcao(exc):
                raise
            console.print("[bold yellow]Índice corrompido: reconstruindo.[/bold yellow]")
            return self._sync_reconstruindo(verbose)

    def _sync_incremental(self, verbose: bool) -> Dict[str, Any]:
        added, modified, deleted = diferenca(self.vault_dir, self.store.manifesto())
        if not (added or modified or deleted):
            if verbose:
                console.print("[green][OK] Vault já está 100% sincronizado. Nenhuma alteração detectada.[/green]")
            return {
                "added": 0, "modified": 0, "deleted": 0, "chunks_indexed": 0,
                "failed": 0, "failed_files": [], "reconstruido": False,
            }

        if verbose:
            console.print(
                f"[bold cyan]Detectadas alterações:[/bold cyan] {len(added)} novos, "
                f"{len(modified)} modificados, {len(deleted)} removidos."
            )

        failed = []
        for rel_path in deleted:
            self.store.remover_arquivo(rel_path)
            if verbose:
                console.print(f"  [red][-] Removido do índice:[/red] {rel_path}")

        total_chunks_indexed = 0
        for file_path in added + modified:
            rel_path = file_path.relative_to(self.vault_dir).as_posix()
            try:
                sha, chunks = self._read_and_chunk(file_path, rel_path)
            except (OSError, UnicodeDecodeError) as e:
                # Índice intacto: o próximo sync tenta de novo.
                failed.append(rel_path)
                console.print(f"[bold red]Erro ao ler {rel_path}:[/bold red] {e}")
                continue
            self.store.substituir_arquivo(rel_path, sha, chunks)
            total_chunks_indexed += len(chunks)
            if verbose:
                console.print(f"  [green][+] Indexado:[/green] {rel_path} ({len(chunks)} blocos)")

        return {
            "added": len(added),
            "modified": len(modified),
            "deleted": len(deleted),
            "chunks_indexed": total_chunks_indexed,
            "failed": len(failed),
            "failed_files": failed,
            "reconstruido": False,
        }
