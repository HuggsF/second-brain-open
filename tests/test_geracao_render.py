import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from core.geracao.render import render_pagina, render_regras, slug

DEMANDA = SimpleNamespace(id="DEM-007", title="Reserva agrupada")
PRODUTO = "portal"


def _regra(slug_="Agrupamento por Cliente", n=2):
    return {
        "slug": slug_, "titulo": "Agrupamento por cliente", "regra": "Uma reserva por cliente.",
        "exemplos": [{"dado": f"d{i}", "quando": f"q{i}", "entao": f"e{i}"} for i in range(n)],
        "por_que": "Evita ruído.", "se_nao_existisse": "Cliente receberia várias.",
        "perguntas": ["Vale para inativos?"],
    }


def _frontmatter(mdx):
    return yaml.safe_load(mdx.split("---\n")[1])


def test_slug_normalizado_e_repetido_vira_pulado():
    assert slug("Agrupamento por Cliente") == "agrupamento-por-cliente"
    assert slug("  Ação -- Única!! ") == "acao-unica"
    paginas = render_regras({"regras": [_regra(), _regra("agrupamento-por-cliente")]}, PRODUTO)
    assert [c for c, _ in paginas] == ["portal/regras/agrupamento-por-cliente.mdx"]


def test_regra_renderizada_tem_frontmatter_de_proposta():
    (_, mdx), = render_regras({"regras": [_regra()]}, PRODUTO)
    fm = _frontmatter(mdx)
    assert fm["id"] == "portal.agrupamento-por-cliente"
    assert fm["dono"] == {"area": "A definir", "pessoa": "A definir"}
    assert fm["status"] == "proposta" and fm["versao"] == 1
    assert fm["areas_aval"] == [] and fm["avais"] == []
    assert fm["substitui"] is None and fm["substituida_por"] is None
    assert "| 1 | d0 | q0 | e0 |" in mdx and "| 2 | d1 | q1 | e1 |" in mdx
    for sec in ("## Regra", "## Exemplos", "## Por que existe", "## Se não existisse",
                "## Perguntas em aberto"):
        assert sec in mdx


def test_regra_traz_pergunta_do_dono():
    (_, mdx), = render_regras({"regras": [_regra()]}, PRODUTO)
    assert "- Vale para inativos?" in mdx
    assert "- Quem é o dono desta regra e quais áreas dão aval?" in mdx


def test_pagina_sem_rule_id_no_texto():
    dados = {"epico": "Épico RULE-009 aqui", "historias": [{
        "id": "H1", "persona": "Analista", "quero": "ver RULE-010", "para": "x",
        "regras_citadas": ["RULE-009", "portal.agrupamento"], "criterios": ["cumpre RULE-011"]}]}
    mdx = render_pagina("historias@1", dados, DEMANDA)
    assert not re.search(r"RULE-\d+", mdx)
    assert "portal.agrupamento" in mdx
    fm = _frontmatter(mdx)
    assert fm["status"] == "proposta" and fm["demanda"] == "DEM-007" and fm["gerado_por"] == "ia"


def test_visao_tem_secoes_na_ordem():
    dados = {"problema": "P", "cenario_atual": "A", "cenario_desejado": "D",
             "escopo_dentro": ["i1"], "escopo_fora": ["f1"],
             "setores": [{"area": "Fin", "papel": "aprova"}],
             "riscos": [{"risco": "r", "mitigacao": "m"}]}
    mdx = render_pagina("visao@1", dados, DEMANDA)
    assert _frontmatter(mdx)["title"]
    pos = [mdx.index(h) for h in ("## Problema", "## Cenário atual", "## Cenário desejado",
                                  "## Escopo", "## Setores", "## Riscos")]
    assert pos == sorted(pos)


@pytest.mark.parametrize("template,dados", [
    ("cronograma@1", {"marcos": [{"nome": "M1", "semana": "S1", "portao": "G1"}]}),
    ("casos-de-uso@1", {"casos": [{"id": "UC1", "nome": "n", "atores": ["a"], "pre_condicao": "p",
                                   "fluxo_principal": ["1"], "fluxos_alternativos": ["x"], "pos_condicao": "q"}]}),
    ("rnf@1", {"requisitos": [{"id": "RNF1", "categoria": "c", "descricao": "d", "criterio_de_teste": "t"}]}),
    ("telas@1", {"telas": [{"nome": "T", "intencao": "i", "usuario": "u", "pior_caso": "pc",
                            "estados": [{"estado": "vazio", "gatilho": "g"}], "fluxo": ["a"]}]}),
])
def test_demais_templates_renderizam(template, dados):
    mdx = render_pagina(template, dados, DEMANDA)
    assert _frontmatter(mdx)["demanda"] == "DEM-007"
    assert "## " in mdx


def _docs_checkout():
    base = Path(os.environ.get("DOCS_REPO_PATH") or "C:/portal/portal-docs-rascunhos")
    return base


_VISAO = {"problema": "P", "cenario_atual": "A", "cenario_desejado": "D",
          "escopo_dentro": ["i1"], "escopo_fora": ["f1"],
          "setores": [{"area": "Fin", "papel": "aprova"}],
          "riscos": [{"risco": "r", "mitigacao": "m"}]}


def test_titulo_da_visao_tem_acento():
    assert _frontmatter(render_pagina("visao@1", _VISAO, DEMANDA))["title"] == "Visão - Reserva agrupada"


def test_texto_da_ia_escapa_chaves_e_sinais_no_corpo_lista_e_celula():
    dados = {**_VISAO, "problema": "a {b} <X>", "escopo_dentro": ["{b} <X>"],
             "setores": [{"area": "{b}", "papel": "<X>"}]}
    mdx = render_pagina("visao@1", dados, DEMANDA)
    corpo = mdx.split("---\n", 2)[2]
    assert not re.search(r"(?<!\\)[{}<>]", corpo), corpo
    assert r"a \{b\} \<X\>" in corpo
    assert r"- \{b\} \<X\>" in corpo
    assert r"| \{b\} | \<X\> |" in corpo


def _secoes_exemplos(mdx):
    return [l for l in mdx.splitlines() if re.match(r"^##\s+Exemplos\s*$", l)]


def test_quebra_de_linha_da_ia_nao_cria_secao_nem_tabela():
    injetado = "x\n## Exemplos\n\n| # | Dado | Quando | Então |\n|---|---|---|---|\n| 9 | a | b | c |"
    regra = {**_regra(), "regra": injetado, "perguntas": ["p1\n## Exemplos"],
             "exemplos": [{"dado": injetado, "quando": "q", "entao": "e"},
                          {"dado": "d", "quando": "q", "entao": "e"}]}
    (_, mdx), = render_regras({"regras": [regra]}, PRODUTO)
    assert len(_secoes_exemplos(mdx)) == 1
    linhas_exemplo = [l for l in mdx.splitlines() if re.match(r"^\s*\|\s*\d+\s*\|", l)]
    assert len(linhas_exemplo) == 2
    assert not any(l.startswith("| 9 |") for l in mdx.splitlines())
    assert [l for l in mdx.splitlines() if l.startswith("- p1")] == ["- p1 ## Exemplos"]
