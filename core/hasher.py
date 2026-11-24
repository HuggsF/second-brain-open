import hashlib
from pathlib import Path


def calculate_file_hash(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def diferenca(vault_dir: Path, manifesto: dict[str, str]) -> tuple[list[Path], list[Path], list[str]]:
    """Compara o vault com o manifesto do índice.

    Devolve `(novos, modificados, removidos)`: caminhos de arquivos novos e modificados e
    caminhos relativos (com `/`) das notas que saíram do vault.
    """
    novos: list[Path] = []
    modificados: list[Path] = []
    presentes: set[str] = set()
    for file_path in sorted(vault_dir.rglob("*.md")):
        chave = file_path.relative_to(vault_dir).as_posix()
        presentes.add(chave)
        if chave not in manifesto:
            novos.append(file_path)
        elif manifesto[chave] != calculate_file_hash(file_path):
            modificados.append(file_path)
    removidos = sorted(chave for chave in manifesto if chave not in presentes)
    return novos, modificados, removidos
