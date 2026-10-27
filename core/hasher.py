import hashlib
import json
from pathlib import Path
from typing import Dict, List, Tuple
from config import settings

class ManifestManager:
    def __init__(self, manifest_path: Path = settings.hash_manifest_path):
        self.manifest_path = manifest_path

    def load_manifest(self) -> Dict[str, str]:
        if not self.manifest_path.exists():
            return {}
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_manifest(self, manifest: Dict[str, str]) -> None:
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

    @staticmethod
    def calculate_file_hash(file_path: Path) -> str:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def get_diff(self, vault_dir: Path = settings.vault_dir) -> Tuple[List[Path], List[Path], List[str]]:
        """
        Returns:
            added_files: List of Path
            modified_files: List of Path
            deleted_rel_paths: List of relative path strings
        """
        old_manifest = self.load_manifest()
        current_files = list(vault_dir.rglob("*.md"))

        added: List[Path] = []
        modified: List[Path] = []
        current_rel_keys = set()

        for file_path in current_files:
            rel_key = str(file_path.relative_to(vault_dir).as_posix())
            current_rel_keys.add(rel_key)
            current_hash = self.calculate_file_hash(file_path)

            if rel_key not in old_manifest:
                added.append(file_path)
            elif old_manifest[rel_key] != current_hash:
                modified.append(file_path)

        deleted = [rel_key for rel_key in old_manifest.keys() if rel_key not in current_rel_keys]

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
