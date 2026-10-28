import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import hashlib
from pathlib import Path
from typing import Dict, Any
from rich.console import Console

from config import settings
from core.hasher import ManifestManager
from core.chunker import MarkdownChunker
from core.embeddings import OllamaEmbeddingClient
from core.qdrant_store import QdrantStore
from core.sync_lock import sync_lock

console = Console(force_terminal=True)

DEFAULT_LOCK_PATH = settings.base_dir / ".runtime" / "sync.lock"


class SyncEngine:
    def __init__(self, lock_path: Path = DEFAULT_LOCK_PATH, lock_wait: float = 0.0):
        self.manifest_manager = ManifestManager()
        self.chunker = MarkdownChunker()
        self.embedder = OllamaEmbeddingClient()
        self.store = QdrantStore()
        self.vault_dir = settings.vault_dir
        self.lock_path = Path(lock_path)
        self.lock_wait = lock_wait

    def sync_vault(self, verbose: bool = True) -> Dict[str, Any]:
        """Executa sincronização diferencial entre o Vault Markdown e o Qdrant.

        Roda dentro do lock do sistema operacional; outro sync em andamento -> `SyncBusy`.
        """
        with sync_lock(self.lock_path, self.lock_wait):
            return self._sync_unlocked(verbose)

    def _sync_unlocked(self, verbose: bool = True) -> Dict[str, Any]:
        """Sync incremental; quem chama já segura o lock."""
        # Garantir coleção ativa no Qdrant (True quando acabou de criar).
        # `created` é o gancho da reconciliação automática (coleção recém-criada).
        created = self.store.ensure_collection()  # noqa: F841

        # Manifesto lido uma vez por sync; ilegível -> ManifestError antes de tocar o índice.
        manifest = self.manifest_manager.load_manifest()
        added, modified, deleted, _ = self.manifest_manager.get_diff_with_hashes(self.vault_dir, manifest)
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
            manifest.pop(rel_path, None)
            self.manifest_manager.save_manifest(manifest)
            if verbose:
                console.print(f"  [red][-] Removido do índice:[/red] {rel_path}")

        modified_set = set(modified)
        total_chunks_indexed = 0

        # 2. Novos e modificados: troca por arquivo (grava os pontos novos antes de apagar os antigos)
        for file_path in added + modified:
            rel_path = file_path.relative_to(self.vault_dir).as_posix()

            # Leitura única: o hash gravado é o dos mesmos bytes que geram os chunks.
            try:
                raw = file_path.read_bytes()
            except OSError as e:
                failed.append(rel_path)
                console.print(f"[bold red]Erro ao ler {rel_path}:[/bold red] {e}")
                continue
            sha = hashlib.sha256(raw).hexdigest()
            chunks = self.chunker.chunk_bytes(raw, rel_path, self.vault_dir)

            if not chunks:
                if file_path in modified_set:
                    try:
                        self.store.delete_stale(rel_path, set())
                    except Exception as e:
                        failed.append(rel_path)
                        console.print(f"[bold red]Erro ao limpar {rel_path} do índice:[/bold red] {e}")
                        continue
                manifest[rel_path] = sha
                self.manifest_manager.save_manifest(manifest)
                continue

            vectors = []
            for chunk in chunks:
                try:
                    vec = self.embedder.get_embedding(chunk["content"])
                    vectors.append(vec)
                except Exception as e:
                    console.print(f"[bold red]Erro ao gerar embedding para {rel_path}:[/bold red] {e}")
                    break

            if len(vectors) != len(chunks):
                # Nada foi tocado: o índice mantém os vetores antigos e o manifesto não avança.
                failed.append(rel_path)
                continue

            try:
                self.store.upsert_chunks(chunks, vectors)
            except Exception as e:
                failed.append(rel_path)
                console.print(f"[bold red]Erro ao indexar {rel_path}:[/bold red] {e}")
                continue

            try:
                # Os pontos novos já estão gravados; só agora sai o que sobrou da versão anterior.
                self.store.delete_stale(rel_path, self.store.point_ids(chunks))
            except Exception as e:
                # Sobra lixo antigo; o manifesto não avança e o próximo sync repete a limpeza.
                failed.append(rel_path)
                console.print(f"[bold red]Erro ao remover pontos antigos de {rel_path}:[/bold red] {e}")
                continue

            manifest[rel_path] = sha
            self.manifest_manager.save_manifest(manifest)
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
        }
