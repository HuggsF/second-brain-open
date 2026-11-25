"""Render MDX dos artefatos de fase a partir do JSON extraído (funções puras)."""
from __future__ import annotations

import re
import unicodedata

import yaml

PERGUNTA_DONO = "Quem é o dono desta regra e quais áreas dão aval?"
_RULE_ID = re.compile(r"RULE-\d+")


def slug(texto: str) -> str:
    base = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")


_QUEBRA = re.compile(r"\s*[\r\n]+\s*")
_MDX_ESPECIAIS = str.maketrans({"{": "\\{", "}": "\\}", "<": "\\<", ">": "\\>"})


def _limpo(texto) -> str:
    """Model text for the frontmatter (YAML quotes it): only the rule ids go."""
    return _RULE_ID.sub("regra citada", str(texto))


def _texto(texto) -> str:
    """Model text for the MDX body: one line (no heading, list or table of its own)
    and ``{ } < >`` escaped so MDX reads them as text, not as JSX."""
    return _QUEBRA.sub(" ", _limpo(texto)).strip().translate(_MDX_ESPECIAIS)


def _celula(texto) -> str:
    return _texto(texto).replace("|", "\\|")


def _frontmatter(campos: dict) -> str:
    corpo = yaml.safe_dump(campos, allow_unicode=True, sort_keys=False, width=1000).rstrip("\n")
    return f"---\n{corpo}\n---\n"


def _lista(itens) -> str:
    return "\n".join(f"- {_texto(i)}" for i in itens)


def _numerada(itens) -> str:
    return "\n".join(f"{n}. {_texto(i)}" for n, i in enumerate(itens, 1))


def _tabela(cabecalho: list[str], linhas: list[list]) -> str:
    out = ["| " + " | ".join(cabecalho) + " |", "|" + "|".join("---" for _ in cabecalho) + "|"]
    out += ["| " + " | ".join(_celula(c) for c in linha) + " |" for linha in linhas]
    return "\n".join(out)


def _visao(d):
    return "\n\n".join([
        "## Problema\n\n" + _texto(d["problema"]),
        "## Cenário atual\n\n" + _texto(d["cenario_atual"]),
        "## Cenário desejado\n\n" + _texto(d["cenario_desejado"]),
        "## Escopo\n\n### Dentro\n\n" + _lista(d["escopo_dentro"]) + "\n\n### Fora\n\n" + _lista(d["escopo_fora"]),
        "## Setores envolvidos\n\n" + _tabela(["Área", "Papel"], [[s["area"], s["papel"]] for s in d["setores"]]),
        "## Riscos\n\n" + _tabela(["Risco", "Mitigação"], [[r["risco"], r["mitigacao"]] for r in d["riscos"]]),
    ])


def _cronograma(d):
    return "## Marcos\n\n" + _tabela(
        ["Marco", "Semana", "Portão"], [[m["nome"], m["semana"], m["portao"]] for m in d["marcos"]])


def _historias(d):
    partes = ["## Épico\n\n" + _texto(d["epico"])]
    for h in d["historias"]:
        bloco = [f"## {_texto(h['id'])}",
                 f"Como {_texto(h['persona'])}, quero {_texto(h['quero'])}, para {_texto(h['para'])}."]
        if h["regras_citadas"]:
            bloco.append("### Regras citadas\n\n" + _lista(h["regras_citadas"]))
        bloco.append("### Critérios de aceite\n\n" + _lista(h["criterios"]))
        partes.append("\n\n".join(bloco))
    return "\n\n".join(partes)


def _casos(d):
    partes = []
    for c in d["casos"]:
        bloco = [f"## {_texto(c['id'])} - {_texto(c['nome'])}",
                 "### Atores\n\n" + _lista(c["atores"]),
                 "### Pré-condição\n\n" + _texto(c["pre_condicao"]),
                 "### Fluxo principal\n\n" + _numerada(c["fluxo_principal"])]
        if c["fluxos_alternativos"]:
            bloco.append("### Fluxos alternativos\n\n" + _lista(c["fluxos_alternativos"]))
        bloco.append("### Pós-condição\n\n" + _texto(c["pos_condicao"]))
        partes.append("\n\n".join(bloco))
    return "\n\n".join(partes)


def _rnf(d):
    return "## Requisitos não funcionais\n\n" + _tabela(
        ["Id", "Categoria", "Descrição", "Critério de teste"],
        [[r["id"], r["categoria"], r["descricao"], r["criterio_de_teste"]] for r in d["requisitos"]])


def _telas(d):
    partes = []
    for t in d["telas"]:
        partes.append("\n\n".join([
            f"## {_texto(t['nome'])}",
            "### Intenção\n\n" + _texto(t["intencao"]),
            "### Usuário\n\n" + _texto(t["usuario"]),
            "### Pior caso\n\n" + _texto(t["pior_caso"]),
            "### Estados\n\n" + _tabela(["Estado", "Gatilho"], [[e["estado"], e["gatilho"]] for e in t["estados"]]),
            "### Fluxo\n\n" + _numerada(t["fluxo"]),
        ]))
    return "\n\n".join(partes)


_TITULOS = {"visao@1": "Visão", "cronograma@1": "Cronograma", "historias@1": "Histórias",
            "casos-de-uso@1": "Casos de uso", "rnf@1": "RNF", "telas@1": "Telas"}

_CORPOS = {"visao@1": _visao, "cronograma@1": _cronograma, "historias@1": _historias,
           "casos-de-uso@1": _casos, "rnf@1": _rnf, "telas@1": _telas}


def render_pagina(template: str, dados: dict, demanda) -> str:
    if template not in _CORPOS:
        raise ValueError(f"template sem página: {template!r}")
    titulo = f"{_TITULOS[template]} - {_limpo(demanda.title)}"
    fm = _frontmatter({"title": titulo, "status": "proposta", "demanda": demanda.id, "gerado_por": "ia"})
    return fm + "\n" + _CORPOS[template](dados) + "\n"


def render_regras(dados: dict, produto: str) -> list[tuple[str, str]]:
    vistos: set[str] = set()
    paginas = []
    for r in dados["regras"]:
        s = slug(r["slug"])
        if not s or s in vistos:
            continue
        vistos.add(s)
        fm = _frontmatter({
            "id": f"{produto}.{s}", "title": _limpo(r["titulo"]),
            "dono": {"area": "A definir", "pessoa": "A definir"}, "areas_aval": [],
            "status": "proposta", "versao": 1, "avais": [],
            "substitui": None, "substituida_por": None,
        })
        linhas = [[n, e["dado"], e["quando"], e["entao"]] for n, e in enumerate(r["exemplos"], 1)]
        corpo = "\n\n".join([
            "## Regra\n\n" + _texto(r["regra"]),
            "## Exemplos\n\n" + _tabela(["#", "Dado", "Quando", "Então"], linhas),
            "## Por que existe\n\n" + _texto(r["por_que"]),
            "## Se não existisse\n\n" + _texto(r["se_nao_existisse"]),
            "## Perguntas em aberto\n\n" + _lista([*r["perguntas"], PERGUNTA_DONO]),
        ])
        paginas.append((f"{produto}/regras/{s}.mdx", fm + "\n" + corpo + "\n"))
    return paginas
