import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import hashlib
from datetime import datetime, timezone
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


class MigrationNeedsConfirmation(RuntimeError):
    """O alias ainda é uma coleção real: a primeira reconstrução precisa de confirmação."""


def _utc_stamp() -> str:
    """Carimbo AAAAMMDDHHMMSS em UTC para o nome da coleção versionada."""
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


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

    def reconcile(self, verbose: bool = True) -> Dict[str, int]:
        """Reconcilia manifesto e índice (spec §2.7) e reindexa o que saiu do manifesto.

        Roda dentro do lock. Devolve `{"orphans_removed", "missing_reindexed", "untracked_reindexed"}`
        mais `failed` e `failed_files` do sync que reindexa (arquivos que ainda não voltaram ao índice).
        """
        with sync_lock(self.lock_path, self.lock_wait):
            # Manifesto ilegível levanta ManifestError antes de tocar o Qdrant.
            manifest = self.manifest_manager.load_manifest()
            self.store.ensure_collection()
            report = self._reconcile_unlocked(manifest, verbose)
            # O sync seguinte reindexa o que saiu do manifesto; as falhas dele entram no resultado.
            sync_result = self._sync_unlocked(verbose)
            report["failed"] = sync_result["failed"]
            report["failed_files"] = list(sync_result["failed_files"])
            return report

    def rebuild(self, verbose: bool = True, confirm_migration: bool = False) -> Dict[str, Any]:
        """Reindexa o vault inteiro numa coleção versionada e troca o alias (spec §2.8).

        Roda dentro do lock. O alias é `self.store.collection_name`. Qualquer falha antes da troca
        apaga a coleção nova e deixa alias, coleção anterior e manifesto como estavam (INV-N07).
        Se o alias ainda é uma coleção real (primeira vez), exige `confirm_migration=True`:
        a troca apaga a coleção real e cria o alias (a busca falha entre as duas chamadas).
        Devolve `{"collection", "files", "chunks", "migrated"}`.
        """
        with sync_lock(self.lock_path, self.lock_wait):
            return self._rebuild_unlocked(verbose, confirm_migration)

    def _rebuild_unlocked(self, verbose: bool, confirm_migration: bool) -> Dict[str, Any]:
        alias = self.store.collection_name

        # 0. Migração exige confirmação antes de criar ou indexar qualquer coisa.
        migrating = self.store.is_real_collection(alias)
        if migrating and not confirm_migration:
            raise MigrationNeedsConfirmation(
                f"'{alias}' é uma coleção real; a primeira reconstrução a apaga e cria o alias "
                "(a busca falha por um instante). Confirme para migrar."
            )

        # 0b. Sobras de reconstruções interrompidas (spec §6.2): tudo `{alias}__*` fora do alias.
        old_target = self.store.alias_target(alias)
        for name in self.store.collections_with_prefix(f"{alias}__"):
            if name != old_target:
                self.store.drop_collection(name)
                if verbose:
                    console.print(f"  [red][-] Coleção órfã de reconstrução anterior removida:[/red] {name}")

        # 1. Coleção nova versionada (UTC); duas reconstruções no mesmo segundo ganham sufixo.
        base = f"{alias}__{_utc_stamp()}"
        new = base
        suffix = 0
        while self.store.is_real_collection(new):
            suffix += 1
            new = f"{base}_{suffix}"
        self.store.create_named_collection(new, settings.vector_size)

        try:
            new_store = QdrantStore(url=self.store.url, collection_name=new)
            # 2. Indexa o vault inteiro na coleção nova; manifesto novo construído do zero.
            new_manifest: Dict[str, str] = {}
            failed = []
            files = 0
            total_chunks = 0
            for file_path in sorted(self.vault_dir.rglob("*.md")):
                rel_path = file_path.relative_to(self.vault_dir).as_posix()
                try:
                    sha, chunks = self._read_and_chunk(file_path, rel_path)
                except OSError as e:
                    failed.append(rel_path)
                    console.print(f"[bold red]Erro ao ler {rel_path}:[/bold red] {e}")
                    continue
                vectors = self._embed_chunks(chunks, rel_path)
                if vectors is None:
                    failed.append(rel_path)
                    continue
                if chunks:
                    new_store.upsert_chunks(chunks, vectors)
                new_manifest[rel_path] = sha
                files += 1
                total_chunks += len(chunks)
                if verbose:
                    console.print(f"  [green][+] Indexado:[/green] {rel_path} ({len(chunks)} blocos)")

            # 3. Valida: nenhum arquivo falhou e a coleção nova não está vazia (INV-N07).
            if failed:
                raise RuntimeError(
                    f"Reconstrução abortada: {len(failed)} arquivo(s) falharam: {', '.join(failed)}"
                )
            if new_store.points_count() == 0:
                raise RuntimeError("Reconstrução abortada: a coleção nova ficou sem pontos.")
        except BaseException:
            try:
                self.store.drop_collection(new)
            except Exception as e:
                console.print(f"[bold red]Erro ao apagar a coleção nova {new}:[/bold red] {e}")
            raise

        # 4. Troca o alias. Migração: apaga a coleção real homônima e cria o alias.
        if migrating:
            self.store.drop_collection(alias)
            self.store.swap_alias(alias, new, has_old_alias=False)
        else:
            self.store.swap_alias(alias, new, has_old_alias=old_target is not None)

        # 5. Manifesto novo (escrita atômica), sem ler o antigo (pode estar ilegível).
        self.manifest_manager.save_manifest(new_manifest)

        # 6. Apaga a coleção que o alias apontava antes.
        if old_target is not None and old_target != new:
            self.store.drop_collection(old_target)

        if verbose:
            console.print(
                f"[green][OK] Reconstrução concluída:[/green] {files} arquivos, {total_chunks} blocos "
                f"em {new}" + (" (migração do alias)" if migrating else "")
            )
        return {"collection": new, "files": files, "chunks": total_chunks, "migrated": migrating}

    def _read_and_chunk(self, file_path: Path, rel_path: str):
        """Leitura única: o hash devolvido é o dos mesmos bytes que geram os chunks (INV-N05).

        Devolve `(sha256, chunks)`; erro de leitura levanta `OSError`.
        """
        raw = file_path.read_bytes()
        return hashlib.sha256(raw).hexdigest(), self.chunker.chunk_bytes(raw, rel_path, self.vault_dir)

    def _embed_chunks(self, chunks, rel_path: str):
        """Embeddings de todos os chunks, ou `None` se algum falhou (o arquivo inteiro é ignorado)."""
        vectors = []
        for chunk in chunks:
            try:
                vectors.append(self.embedder.get_embedding(chunk["content"]))
            except Exception as e:
                console.print(f"[bold red]Erro ao gerar embedding para {rel_path}:[/bold red] {e}")
                return None
        return vectors

    def _reconcile_unlocked(self, manifest: Dict[str, str], verbose: bool = True) -> Dict[str, int]:
        """Corrige índice e manifesto em memória (spec §2.7); nunca indexa.

        Entradas do manifesto que saem daqui são reindexadas pelo diff seguinte. Quem chama já
        segura o lock. Arquivo no manifesto sem pontos só conta como "ausente" quando o arquivo
        existe no vault e gera chunks: nota vazia (zero chunks) não tem pontos por definição, e
        arquivo apagado do vault é trabalho do diff (remoção).
        """
        indexed = self.store.indexed_files()
        vault = {p.relative_to(self.vault_dir).as_posix() for p in self.vault_dir.rglob("*.md")}

        orphans = sorted(f for f in indexed if f not in manifest and f not in vault)
        orphans_removed = 0
        for rel_path in orphans:
            self.store.delete_by_file_path(rel_path)
            orphans_removed += 1
            if verbose:
                console.print(f"  [red][-] Órfão removido do índice:[/red] {rel_path}")

        missing = []
        for rel_path in sorted(f for f in manifest if f not in indexed):
            file_path = self.vault_dir / rel_path
            if not file_path.is_file():
                continue
            try:
                chunks = self.chunker.chunk_bytes(file_path.read_bytes(), rel_path, self.vault_dir)
            except (OSError, UnicodeDecodeError):
                chunks = [None]  # ilegível agora: o sync seguinte tenta de novo
            if chunks:
                missing.append(rel_path)

        untracked = sorted(f for f in indexed if f in vault and f not in manifest)

        for rel_path in missing:
            manifest.pop(rel_path, None)

        if missing:
            self.manifest_manager.save_manifest(manifest)

        if verbose and (missing or untracked):
            console.print(
                f"[bold cyan]Reconciliação:[/bold cyan] {len(missing)} ausentes do índice e "
                f"{len(untracked)} fora do manifesto serão reindexados."
            )
        return {
            "orphans_removed": orphans_removed,
            "missing_reindexed": len(missing),
            "untracked_reindexed": len(untracked),
        }

    def _sync_unlocked(self, verbose: bool = True) -> Dict[str, Any]:
        """Sync incremental; quem chama já segura o lock."""
        # Manifesto lido uma vez por sync, antes de tocar o Qdrant: ilegível -> ManifestError
        # sem criar a coleção (e sem gastar o sinal `created`).
        manifest = self.manifest_manager.load_manifest()

        # Garantir coleção ativa no Qdrant (True quando acabou de criar): coleção nova
        # com manifesto cheio -> reconcilia antes do diff para reindexar o que sumiu.
        # `created` só vale uma vez; se a reconciliação falhar depois da criação, o sinal durável
        # é "manifesto cheio e coleção sem pontos", que repete a reconciliação no sync seguinte.
        created = self.store.ensure_collection()
        if created or (manifest and self.store.points_count() == 0):
            self._reconcile_unlocked(manifest, verbose)

        added, modified, deleted, _ = self.manifest_manager.get_diff_with_hashes(self.vault_dir, manifest)
        total_changes = len(added) + len(modified) + len(deleted)

        if total_changes == 0:
            if verbose:
                console.print("[green][OK] Vault já está 100% sincronizado. Nenhuma alteração detectada.[/green]")
            return {"added": 0, "modified": 0, "deleted": 0, "chunks_indexed": 0, "failed": 0, "failed_files": []}

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

            try:
                sha, chunks = self._read_and_chunk(file_path, rel_path)
            except OSError as e:
                failed.append(rel_path)
                console.print(f"[bold red]Erro ao ler {rel_path}:[/bold red] {e}")
                continue

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

            vectors = self._embed_chunks(chunks, rel_path)
            if vectors is None:
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
