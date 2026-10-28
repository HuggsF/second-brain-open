import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from config import settings


class ManifestError(RuntimeError):
    """Manifesto existente, mas ilegivel ou com formato invalido."""


class ManifestManager:
    def __init__(self, manifest_path: Path = settings.hash_manifest_path):
        self.manifest_path = manifest_path

    def load_manifest(self) -> Dict[str, str]:
        """Manifesto ausente e primeira execucao ({}); existente e invalido levanta ManifestError."""
        if not self.manifest_path.exists():
            return {}
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as exc:
            raise ManifestError(f"Manifesto ilegivel: {self.manifest_path} ({exc})") from exc
        if not isinstance(data, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in data.items()
        ):
            raise ManifestError(
                f"Manifesto com formato invalido (esperado objeto str->str): {self.manifest_path}"
            )
        return data

    def save_manifest(self, manifest: Dict[str, str]) -> None:
        """Grava de forma atomica: arquivo temporario, fsync e os.replace.

        Um `.tmp` de gravacao interrompida e removido antes; se a gravacao falhar, o `.tmp` sai
        e o manifesto anterior fica intacto (INV-N03).
        """
        tmp_path = self.manifest_path.with_suffix(self.manifest_path.suffix + ".tmp")
        self._unlink_quiet(tmp_path)
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.manifest_path)
        except BaseException:
            self._unlink_quiet(tmp_path)
            raise

    @staticmethod
    def _unlink_quiet(path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    @staticmethod
    def calculate_file_hash(file_path: Path) -> str:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def get_diff_with_hashes(
        self, vault_dir: Path = settings.vault_dir, manifest: Optional[Dict[str, str]] = None
    ) -> Tuple[List[Path], List[Path], List[str], Dict[str, str]]:
        """
        Returns:
            added_files: List of Path
            modified_files: List of Path
            deleted_rel_paths: List of relative path strings
            current_hashes: rel_path -> sha256 of the current files
        """
        old_manifest = self.load_manifest() if manifest is None else manifest

        added: List[Path] = []
        modified: List[Path] = []
        current_hashes: Dict[str, str] = {}

        for file_path in vault_dir.rglob("*.md"):
            rel_key = str(file_path.relative_to(vault_dir).as_posix())
            current_hash = self.calculate_file_hash(file_path)
            current_hashes[rel_key] = current_hash

            if rel_key not in old_manifest:
                added.append(file_path)
            elif old_manifest[rel_key] != current_hash:
                modified.append(file_path)

        deleted = [rel_key for rel_key in old_manifest if rel_key not in current_hashes]

        return added, modified, deleted, current_hashes

    def get_diff(self, vault_dir: Path = settings.vault_dir) -> Tuple[List[Path], List[Path], List[str]]:
        added, modified, deleted, _ = self.get_diff_with_hashes(vault_dir)
        return added, modified, deleted

    def update_file_hash(self, file_path: Path, vault_dir: Path = settings.vault_dir) -> None:
        manifest = self.load_manifest()
        rel_key = str(file_path.relative_to(vault_dir).as_posix())
        manifest[rel_key] = self.calculate_file_hash(file_path)
        self.save_manifest(manifest)

    def remove_file(self, rel_key: str) -> None:
        manifest = self.load_manifest()
        if rel_key in manifest:
            del manifest[rel_key]
            self.save_manifest(manifest)
