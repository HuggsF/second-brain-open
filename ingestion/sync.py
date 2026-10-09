import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pathlib import Path
from typing import Dict, Any
from rich.console import Console

from config import settings
from core.hasher import ManifestManager
from core.chunker import MarkdownChunker
from core.embeddings import OllamaEmbeddingClient
from core.qdrant_store import QdrantStore

console = Console(force_terminal=True)

class SyncEngine:
    def __init__(self):
        self.manifest_manager = ManifestManager()
        self.chunker = MarkdownChunker()
        self.embedder = OllamaEmbeddingClient()
        self.store = QdrantStore()

    def sync_vault(self, verbose: bool = True) -> Dict[str, Any]:
        """Executa sincronização diferencial entre o Vault Markdown e o Qdrant."""
        # Garantir coleção ativa no Qdrant
        self.store.ensure_collection()

        added, modified, deleted = self.manifest_manager.get_diff(settings.vault_dir)
        total_changes = len(added) + len(modified) + len(deleted)

        if total_changes == 0:
            if verbose:
                console.print("[green][OK] Vault já está 100% sincronizado. Nenhuma alteração detectada.[/green]")
            return {"added": 0, "modified": 0, "deleted": 0, "chunks_indexed": 0, "failed": 0}

        if verbose:
            console.print(f"[bold cyan]Detectadas alterações:[/bold cyan] {len(added)} novos, {len(modified)} modificados, {len(deleted)} removidos.")

        failed = []

        # 1. Tratar arquivos deletados (se falhar, o manifesto não avança e o próximo sync repete)
        for rel_path in deleted:
            try:
                self.store.delete_by_file_path(rel_path)
            except Exception as e:
                failed.append(rel_path)
                console.print(f"[bold red]Erro ao remover {rel_path} do índice:[/bold red] {e}")
                continue
            self.manifest_manager.remove_file(rel_path)
            if verbose:
                console.print(f"  [red][-] Removido do índice:[/red] {rel_path}")

        files_to_index = added + modified
        total_chunks_indexed = 0

        # 2. Processar novos e modificados com barra de progresso
        for file_path in files_to_index:
            rel_path = str(file_path.relative_to(settings.vault_dir).as_posix())
            
            chunks = self.chunker.chunk_file(file_path, settings.vault_dir)
            if not chunks:
                if file_path in modified:
                    try:
                        self.store.delete_by_file_path(rel_path)
                    except Exception as e:
                        failed.append(rel_path)
                        console.print(f"[bold red]Erro ao limpar {rel_path} do índice:[/bold red] {e}")
                        continue
                self.manifest_manager.update_file_hash(file_path, settings.vault_dir)
                continue

            vectors = []
            for chunk in chunks:
                try:
                    vec = self.embedder.get_embedding(chunk["content"])
                    vectors.append(vec)
                except Exception as e:
                    console.print(f"[bold red]Erro ao gerar embedding para {rel_path}:[/bold red] {e}")
                    break

            if len(vectors) == len(chunks):
                try:
                    # Só agora, com os vetores novos prontos, troca o conhecimento antigo pelo novo.
                    if file_path in modified:
                        self.store.delete_by_file_path(rel_path)
                    self.store.upsert_chunks(chunks, vectors)
                except Exception as e:
                    failed.append(rel_path)
                    console.print(f"[bold red]Erro ao indexar {rel_path}:[/bold red] {e}")
                    continue
                self.manifest_manager.update_file_hash(file_path, settings.vault_dir)
                total_chunks_indexed += len(chunks)
                if verbose:
                    console.print(f"  [green][+] Indexado:[/green] {rel_path} ({len(chunks)} blocos)")
            else:
                failed.append(rel_path)

        return {
            "added": len(added),
            "modified": len(modified),
            "deleted": len(deleted),
            "chunks_indexed": total_chunks_indexed,
            "failed": len(failed),
            "failed_files": failed,
        }
