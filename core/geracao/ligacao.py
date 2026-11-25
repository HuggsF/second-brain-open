"""Montagem do gerador real: cadeia de provedores, retriever local e verificador do rastreio.

Não nomeia a instância: o caminho do ``produtos.yaml`` (catálogo de produtos) vem de
quem chama, e o perfil ativo só entra por ``caminho_produtos``.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from config import settings
from core.docs_registry import docs_root
from core.produtos import ler_guia_triagem, ler_produtos
from core.geracao.gerador import GeradorDeArtefatos
from core.local_tasks.profile import PROFILES_DIR, ProfileNotFound, _NAME_RE
from core.local_tasks.router import run_task
from core.retriever import BrainRetriever

TIMEOUT_RASTREIO_S = 300


def caminho_produtos(perfil: str | None = None) -> Path:
    """``profiles/<perfil>/produtos.yaml`` of the active profile (``BRAIN_PROFILE`` or default)."""
    nome = perfil or os.environ.get("BRAIN_PROFILE") or settings.default_profile
    if not _NAME_RE.match(nome):
        raise ProfileNotFound(nome)
    return PROFILES_DIR / nome / "produtos.yaml"


def _cliente_ia(template: str, texto: str, trace_id: str | None = None) -> dict:
    return run_task("extract", text=texto, template=template, sender="gerador", trace_id=trace_id)


def _busca(pergunta: str) -> list[str]:
    """Vault excerpts for *pergunta*; raises when the retriever is down (the caller goes on without)."""
    resultado = BrainRetriever().query(pergunta, limit=4, include_content=True)
    trechos = []
    for fonte in resultado.get("sources") or []:
        conteudo = str(fonte.get("content") or "").strip()
        if conteudo:
            trechos.append(f"Fonte: {fonte.get('file_path')} | Seção: {fonte.get('section')}\n{conteudo}")
    return trechos


def _executar_rastreio(docs: Path, produto: str, testes: str, saida: Path) -> int:
    cmd = ["node", str(Path(docs) / "tools" / "rastreio" / "cli.ts"), "--docs", str(docs),
           "--produto", produto, "--testes", testes, "--saida", str(saida)]
    return subprocess.run(cmd, cwd=str(docs), timeout=TIMEOUT_RASTREIO_S,
                          capture_output=True, text=True, encoding="utf-8", errors="replace").returncode


def montar_gerador(svc, produtos_yaml: Path) -> GeradorDeArtefatos:
    produtos = ler_produtos(produtos_yaml)
    runtime = Path(getattr(svc, "_db_path", settings.base_dir / ".runtime" / "demands.db")).parent
    return GeradorDeArtefatos(
        svc,
        cliente_ia=_cliente_ia,
        busca=_busca,
        docs_root=docs_root,
        executar_rastreio=_executar_rastreio,
        testes_por_produto={s: p.testes_rastreio for s, p in produtos.items() if p.testes_rastreio},
        runtime=runtime,
        produtos=produtos,
        guia_triagem=ler_guia_triagem(Path(produtos_yaml).parent / "guia_triagem.md"),
    )
