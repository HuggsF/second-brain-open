"""Leitura do status das páginas do repositório de documentação (checkout local)."""
from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

import yaml

ENV_VAR = "DOCS_REPO_PATH"

# Same rule as the documentation repository's page validator (validateRulePage).
REGRA_REL_RE = re.compile(r"^[^/]+/regras/[^/]+\.mdx$")
RULE_ID_RE = re.compile(r"^[a-z0-9-]+\.[a-z0-9-]+$")
_AVAL_CAMPOS = ("area", "pessoa", "data", "email")


class DocsRegistryError(Exception):
    pass


def docs_root(env: Mapping[str, str] = os.environ) -> Path:
    """Pasta de documentos: a de ``DOCS_REPO_PATH`` ou, sem a variável, a pasta de fichas do repositório."""
    raw = (env.get(ENV_VAR) or "").strip()
    if not raw:
        from config import settings
        root = Path(settings.fichas_dir)
        if not root.is_dir():
            raise DocsRegistryError(f"pasta de fichas inexistente: {root} (ou aponte outra pasta com {ENV_VAR})")
        return root
    root = Path(raw)
    if not root.is_dir():
        raise DocsRegistryError(f"{ENV_VAR} aponta para uma pasta inexistente: {root}")
    return root


def _frontmatter(text: str, rel: str) -> tuple[dict, str]:
    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        raise DocsRegistryError(f"página sem frontmatter: {rel}")
    try:
        fim = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise DocsRegistryError(f"frontmatter sem fechamento: {rel}") from None
    try:
        data = yaml.safe_load("\n".join(lines[1:fim]))
    except yaml.YAMLError as exc:
        raise DocsRegistryError(f"frontmatter malformado em {rel}: {exc}") from exc
    if not isinstance(data, dict):
        raise DocsRegistryError(f"frontmatter malformado em {rel}: esperado um mapa")
    return data, "\n".join(lines[fim + 1:])


def _secao(body: str, titulo: str) -> list[str]:
    """Lines of the ``## <titulo>`` section up to the next ``## ``."""
    lines = body.splitlines()
    cabecalho = re.compile(rf"^##\s+{titulo}\s*$", re.IGNORECASE)
    inicio = next((i for i, l in enumerate(lines) if cabecalho.match(l)), None)
    if inicio is None:
        return []
    out: list[str] = []
    for l in lines[inicio + 1:]:
        if re.match(r"^##\s", l):
            break
        out.append(l)
    return out


def pagina_path(root: Path, rel: str) -> Path:
    """Path of *rel* inside *root*; refuses ``../`` and absolute paths that leave it."""
    base = Path(root).resolve()
    path = (base / rel).resolve()
    if not path.is_relative_to(base):
        raise DocsRegistryError(f"caminho fora do repositório de documentação: {rel}")
    return path


def page_status(root: Path, rel: str) -> dict:
    path = pagina_path(root, rel)
    if not path.is_file():
        raise DocsRegistryError(f"página não encontrada: {rel} (em {path})")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DocsRegistryError(f"página ilegível: {rel}: {exc}") from exc
    fm, body = _frontmatter(text, rel)
    avais = fm.get("avais")
    return {
        "id": fm.get("id"),
        "title": fm.get("title"),
        "dono": fm.get("dono"),
        "status": fm.get("status"),
        "versao": fm.get("versao"),
        "areas_aval": fm.get("areas_aval"),
        "avais": avais if isinstance(avais, list) else [],
        "exemplos": sum(1 for l in _secao(body, "Exemplos") if re.match(r"^\s*\|\s*\d+\s*\|", l)),
        "perguntas_abertas": sum(
            1 for l in _secao(body, "Perguntas em aberto") if re.match(r"^\s*(?:[-*]|\d+\.)\s+\S", l)
        ),
    }


def _versao(v) -> int | None:
    """Integer >= 1 (a float only when whole, as YAML ``1.0`` is an integer in JS)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return v if isinstance(v, int) and v >= 1 else None


def _preenchido(v) -> bool:
    return v is not None and v != ""


def _aval_valido(a) -> bool:
    return isinstance(a, dict) and all(_preenchido(a.get(k)) for k in _AVAL_CAMPOS) and _versao(a.get("versao")) is not None


def _aprovada(s: dict) -> bool:
    versao = _versao(s["versao"])
    if s["status"] != "aprovada" or versao is None:
        return False
    if not all(_preenchido(s.get(k)) for k in ("id", "title", "dono")):
        return False
    if not (isinstance(s["id"], str) and RULE_ID_RE.match(s["id"])):
        return False
    # aprovada also requires what validada requires
    if s.get("exemplos", 0) < 2 or s.get("perguntas_abertas", 0) > 0:
        return False
    areas = s["areas_aval"]
    if not isinstance(areas, list) or not areas:
        return False
    avais = s["avais"]
    if not all(_aval_valido(a) for a in avais):
        return False
    return all(any(a["area"] == area and _versao(a["versao"]) == versao for a in avais) for area in areas)


def regras_aprovadas(root: Path, rels: list[str]) -> list[str]:
    """Devolve os rel que NÃO estão aprovados na versão atual.

    Um rel fora de ``<produto>/regras/<nome>.mdx`` nunca conta como aprovado.
    """
    return [rel for rel in rels if not REGRA_REL_RE.match(rel) or not _aprovada(page_status(root, rel))]


def _celulas(linha: str) -> list[str]:
    r"""Cells of a Markdown table row; ``\|`` is a literal bar."""
    corpo = linha.strip()
    if corpo.startswith("|"):
        corpo = corpo[1:]
    if corpo.endswith("|") and not corpo.endswith("\\|"):
        corpo = corpo[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", corpo)]


def exemplos_da_regra(root: Path, rel: str) -> list[dict]:
    """Examples of the rule page *rel*: ``[{"id": "<id>#<n>", "dado", "quando", "entao"}]``.

    Read from the ``## Exemplos`` table (columns ``# | Dado | Quando | Então``).
    """
    path = pagina_path(root, rel)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise DocsRegistryError(f"página ilegível: {rel}: {exc}") from exc
    fm, body = _frontmatter(text, rel)
    rule_id = fm.get("id")
    exemplos: list[dict] = []
    for linha in _secao(body, "Exemplos"):
        if not re.match(r"^\s*\|\s*\d+\s*\|", linha):
            continue
        celulas = _celulas(linha)
        if len(celulas) < 4:
            continue
        n, dado, quando, entao = celulas[:4]
        exemplos.append({"id": f"{rule_id}#{n}", "dado": dado, "quando": quando, "entao": entao})
    return exemplos
