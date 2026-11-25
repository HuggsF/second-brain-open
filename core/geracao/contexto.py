"""Contexto de entrada da geração: título, descrição, triagem, páginas já geradas e vault."""
from __future__ import annotations

import json

MAX_TRECHOS = 4
_ORDEM_PAGINAS = ("visao", "cronograma", "historias", "casos_de_uso", "rnf", "telas")
# Who approved or downgraded is not context for the draft (and names people).
_TRIAGEM_FORA = ("aprovada_por", "rebaixamentos")


def _sem_frontmatter(texto: str) -> str:
    """Page body only: the frontmatter carries owners and approvals (names, e-mails)."""
    linhas = texto.lstrip("\ufeff").splitlines()
    if not linhas or linhas[0].strip() != "---":
        return texto
    fim = next((i for i in range(1, len(linhas)) if linhas[i].strip() == "---"), None)
    if fim is None:
        return ""  # unclosed frontmatter: send nothing rather than the approvals
    return "\n".join(linhas[fim + 1:]).strip("\n")


def _paginas_geradas(artefacts: dict) -> list[str]:
    rels: list[str] = []
    for nome in _ORDEM_PAGINAS:
        valor = artefacts.get(nome)
        if isinstance(valor, dict):
            valor = valor.get("pagina")
        if isinstance(valor, str) and valor:
            rels.append(valor)
    regras = artefacts.get("regras")
    if isinstance(regras, list):
        rels.extend(r for r in regras if isinstance(r, str))
    return rels


def _catalogo(produtos: dict) -> str:
    """Slugs que a triagem pode escolher, com a descrição e as pistas de cada um."""
    linhas = ["# Produtos do catálogo",
              "Escolha em `produto` exatamente um destes slugs; se nenhum servir, diga isso na justificativa."]
    for slug in sorted(produtos):
        p = produtos[slug]
        linha = f"- {slug}: {p.descricao}"
        if p.pistas:
            linha += " Pistas: " + "; ".join(p.pistas)
        linhas.append(linha)
    return "\n".join(linhas)


def montar(demanda, item, busca, ler_pagina, produtos: dict | None = None,
           guia: str = "") -> tuple[str, bool]:
    artefacts = demanda.artefacts or {}
    partes = [
        f"# Título\n{demanda.title}",
        f"# Descrição\n{demanda.description}",
    ]
    # The triage draft never sees a previous draft: the model would copy it instead of reading.
    triagem = artefacts.get("triagem") if item.artefato != "triagem" else None
    if triagem:
        if isinstance(triagem, dict):
            triagem = {k: v for k, v in triagem.items() if k not in _TRIAGEM_FORA}
        partes.append("# Triagem\n" + json.dumps(triagem, ensure_ascii=False, sort_keys=True))
    for rel in _paginas_geradas(artefacts):
        conteudo = ler_pagina(rel)
        conteudo = _sem_frontmatter(conteudo) if conteudo else conteudo
        if conteudo:
            partes.append(f"# Página já gerada\n{conteudo}")
    com_vault = False
    try:
        trechos = list(busca(f"{demanda.title}\n{demanda.description}"))[:MAX_TRECHOS]
    except Exception:
        trechos = []
    if trechos:
        com_vault = True
        partes.append("# Trechos do vault\n" + "\n---\n".join(trechos))
    if item.artefato == "triagem" and guia.strip():
        partes.append("# Como triar\n" + guia.strip())
    if item.artefato == "triagem" and produtos:
        partes.append(_catalogo(produtos))
    partes.append(f"# Tarefa\nGere o artefato '{item.artefato}' seguindo o template {item.template}.")
    return "\n\n".join(partes), com_vault
