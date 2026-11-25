"""Uma demanda vai de ``intake`` a ``done`` sem interface e sem custo.

Serviço e gerador reais, ligados pelo gancho de fase (síncrono, sem thread); IA falsa com payload
fixo por template; repositório de documentação temporário; verificador de rastreio falso que grava
o JSON de contrato.
"""

import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.demand_lifecycle import DemandLifecycleService, MissingArtefactError, Phase  # noqa: E402
from core.docs_registry import docs_root  # noqa: E402
from core.geracao.gerador import GeradorDeArtefatos  # noqa: E402
from core.protocol import registry  # noqa: E402

PRODUTO = "portal"
SLUG = "agrupamento-por-cliente"
REGRA_REL = f"{PRODUTO}/regras/{SLUG}.mdx"
REGRA_ID = f"{PRODUTO}.{SLUG}"

PAYLOADS = {
    "triagem@1": {
        "produto": PRODUTO, "t1": True, "t2": False, "t3": False, "t4": False,
        "trilha": "completa", "atividade": "desenvolvimento", "faixa": "media",
        "criterios_de_aceite": ["uma reserva por cliente"], "mais_de_uma_sprint": False,
        "justificativa": "regra de negócio nova",
    },
    "visao@1": {
        "problema": "Cliente recebe várias reservas", "cenario_atual": "Uma por pedido",
        "cenario_desejado": "Uma por cliente", "escopo_dentro": ["agrupamento"],
        "escopo_fora": ["comprovante"], "setores": [{"area": "Atendimento", "papel": "aprova"}],
        "riscos": [{"risco": "agrupar errado", "mitigacao": "exemplos aprovados"}],
    },
    "historias@1": {
        "epico": "Reserva agrupada",
        "historias": [{"id": "H1", "persona": "Analista de atendimento", "quero": "uma reserva",
                       "para": "não confundir o cliente", "regras_citadas": [REGRA_ID],
                       "criterios": ["um envio por cliente"]}],
    },
    "regras@1": {
        "regras": [{
            "slug": SLUG, "titulo": "Agrupamento por cliente",
            "regra": "Os pedidos em aberto de um cliente saem numa reserva só.",
            "exemplos": [
                {"dado": "dois pedidos do mesmo cliente", "quando": "o portal roda",
                 "entao": "sai uma reserva"},
                {"dado": "pedidos de dois clientes", "quando": "o portal roda",
                 "entao": "saem duas reservas"},
            ],
            "por_que": "Evita ruído.", "se_nao_existisse": "Várias mensagens por dia.",
            "perguntas": [],
        }],
    },
    "telas@1": {"telas": [{"nome": "Painel", "intencao": "ver reserva", "usuario": "analista",
                           "pior_caso": "sem dados", "estados": [{"estado": "vazio", "gatilho": "sem pedidos"}],
                           "fluxo": ["abrir o painel"]}]},
    "casos-de-uso@1": {"casos": [{"id": "UC1", "nome": "Enviar reserva", "atores": ["portal"],
                                  "pre_condicao": "pedidos em aberto", "fluxo_principal": ["agrupar"],
                                  "fluxos_alternativos": [], "pos_condicao": "reserva enviada"}]},
    "rnf@1": {"requisitos": [{"id": "RNF1", "categoria": "desempenho", "descricao": "rodar em 1 min",
                              "criterio_de_teste": "cronometrar"}]},
}


class IAFalsa:
    """Devolve o envelope de ``run_task`` com payload fixo e custo zero."""

    def __init__(self):
        self.chamadas: list[str] = []

    def __call__(self, template, texto):
        self.chamadas.append(template)
        return {"status": "ok", "reason": "", "payload": PAYLOADS[template],
                "cost": {"actual_usd": 0.0, "provider": "falso"}, "trace_id": f"tr-{template}"}


def _frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---\n", 2)[1])


def _dar_aval(path: Path) -> None:
    """Edit the rule page like the area would: owner, areas, one aval at version 1, no open question."""
    _, fm, corpo = path.read_text(encoding="utf-8").split("---\n", 2)
    dados = yaml.safe_load(fm)
    dados.update({
        "status": "aprovada", "dono": {"area": "Atendimento", "pessoa": "area-solicitante"},
        "areas_aval": ["Atendimento"],
        "avais": [{"area": "Atendimento", "pessoa": "area-solicitante", "data": "2026-11-09",
                   "email": "area-solicitante@empresa.example", "versao": 1}],
    })
    corpo = corpo.split("## Perguntas em aberto")[0] + "## Perguntas em aberto\n\nNenhuma.\n"
    path.write_text("---\n" + yaml.safe_dump(dados, allow_unicode=True, sort_keys=False) + "---\n"
                    + corpo, encoding="utf-8")


def _validar(path: Path) -> None:
    """A person validates a generated (non-rule) page: ``status: proposta`` -> ``validada``."""
    _, fm, corpo = path.read_text(encoding="utf-8").split("---\n", 2)
    dados = yaml.safe_load(fm)
    assert dados["status"] == "proposta"
    dados["status"] = "validada"
    path.write_text("---\n" + yaml.safe_dump(dados, allow_unicode=True, sort_keys=False) + "---\n"
                    + corpo, encoding="utf-8")


def _recusa(svc, did, destino) -> list[str]:
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(did, destino, actor="teste")
    assert svc.get_demand(did).phase != destino
    return exc.value.missing


@pytest.mark.parametrize("template", sorted(PAYLOADS))
def test_payloads_falsos_validos_no_schema(template):
    assert registry.validate(template, PAYLOADS[template]) == []


def test_demanda_vai_de_intake_a_done_com_artefatos_gerados(tmp_path, monkeypatch):
    docs = tmp_path / "portal-docs"
    (docs / PRODUTO).mkdir(parents=True)
    monkeypatch.setenv("DOCS_REPO_PATH", str(docs))
    runtime = tmp_path / "runtime"

    rastreios = []

    def executar_rastreio(root, produto, testes, saida):
        rastreios.append((Path(root), produto, testes))
        saida.write_text(json.dumps({
            "versao": 1, "produto": produto, "gerado_em": "2026-11-09T12:00:00Z", "ok": True,
            "exemplos_aprovados": [f"{REGRA_ID}#1", f"{REGRA_ID}#2"], "orfaos": [], "fantasmas": [],
        }), encoding="utf-8")
        return 0

    ia = IAFalsa()
    svc = DemandLifecycleService(db_path=tmp_path / "demands.db")
    gerador = GeradorDeArtefatos(svc, ia, lambda pergunta: [], docs_root, executar_rastreio,
                                 {PRODUTO: "C:/portal/tests/**/*.test.ts"}, runtime)
    svc.set_gancho_fase(lambda demanda_id, fase: gerador.executar(demanda_id))

    # 1. Criação: triagem sugerida, sem aprovador; o portão recusa.
    did = svc.create_demand("Agrupar reserva por cliente", "Uma reserva por cliente",
                            source="teste").id
    art = svc.get_demand(did).artefacts
    assert art["triagem"]["aprovada_por"] == "" and art["triagem"]["sugerida_por"] == "ia"
    assert art["triagem"]["produto"] == PRODUTO
    assert art["triagem"]["trilha"] == "" and art["triagem"]["trilha_sugerida"] == "completa"
    assert art["geracao"]["triagem"]["estado"] == "gerado"
    assert ia.chamadas == ["triagem@1"]
    assert _recusa(svc, did, Phase.SPIKE) == ["triagem"]

    # 2. O gestor escolhe a trilha (a sugerida) e aprova (completa, T1 = SIM) -> spike gera a visão.
    svc.update_artefact(did, "triagem", {**art["triagem"], "trilha": art["triagem"]["trilha_sugerida"],
                                         "aprovada_por": "Gestor", "aprovada_em": "2026-11-09"})
    assert svc.get_demand(did).artefacts["triagem"]["rebaixamentos"] == []
    svc.transition(did, Phase.SPIKE, actor="teste")
    visao_rel = f"{PRODUTO}/demandas/{did.lower()}/visao.mdx"
    assert (docs / visao_rel).is_file()
    assert _frontmatter(docs / visao_rel)["status"] == "proposta"
    art = svc.get_demand(did).artefacts
    assert art["visao"] == {"pagina": visao_rel, "aprovada_por": ""}
    assert art["geracao"]["visao"]["estado"] == "gerado"
    assert ia.chamadas == ["triagem@1", "visao@1"]

    # 3. spike -> spec recusado até a visão ter aprovador e ser validada; depois gera regras e histórias.
    assert _recusa(svc, did, Phase.SPEC) == ["visao:aprovada_por", f"visao:{visao_rel}:proposta"]
    svc.update_artefact(did, "visao", {"pagina": visao_rel, "aprovada_por": "Gestor"})
    assert _recusa(svc, did, Phase.SPEC) == [f"visao:{visao_rel}:proposta"]
    _validar(docs / visao_rel)
    svc.transition(did, Phase.SPEC, actor="teste")
    historias_rel = f"{PRODUTO}/demandas/{did.lower()}/historias.mdx"
    art = svc.get_demand(did).artefacts
    assert art["regras"] == [REGRA_REL] and art["historias"] == historias_rel
    assert (docs / historias_rel).is_file() and (docs / REGRA_REL).is_file()
    fm_regra = _frontmatter(docs / REGRA_REL)
    assert fm_regra["status"] == "proposta" and fm_regra["id"] == REGRA_ID
    assert fm_regra["avais"] == [] and fm_regra["areas_aval"] == []
    assert _frontmatter(docs / historias_rel)["status"] == "proposta"
    assert art["geracao"]["regras"]["estado"] == "gerado"
    assert art["geracao"]["historias"]["estado"] == "gerado"
    assert sorted(ia.chamadas[2:]) == ["historias@1", "regras@1"]

    # 4. spec -> dev recusado com a regra e as histórias em proposta; aval e validação abrem o portão.
    assert set(_recusa(svc, did, Phase.DEV)) == {f"regras:{REGRA_REL}", f"historias:{historias_rel}:proposta"}
    _dar_aval(docs / REGRA_REL)
    assert _recusa(svc, did, Phase.DEV) == [f"historias:{historias_rel}:proposta"]
    _validar(docs / historias_rel)
    svc.transition(did, Phase.DEV, actor="teste")
    plano = svc.get_demand(did).artefacts["plano_de_testes"]
    assert [c["id"] for c in plano] == [f"{REGRA_ID}#1", f"{REGRA_ID}#2"]
    assert all(c["regra"] == REGRA_REL for c in plano)
    assert plano[0]["dado"] == "dois pedidos do mesmo cliente"
    assert plano[0]["entao"] == "sai uma reserva"

    # 5. dev -> review grava o rastreio; review -> done fecha com evidência e aceite.
    svc.transition(did, Phase.REVIEW, actor="teste")
    art = svc.get_demand(did).artefacts
    saida = runtime / ".rastreio" / f"{did}.json"
    assert art["rastreio"] == str(saida) and saida.is_file()
    assert rastreios == [(docs, PRODUTO, "C:/portal/tests/**/*.test.ts")]
    assert set(_recusa(svc, did, Phase.DONE)) == {"evidence", "aceite_area"}
    svc.update_artefact(did, "evidence", {"test_results": ["portal: 2 passaram"]})
    svc.update_artefact(did, "aceite_area", {"area": "Atendimento", "pessoa": "area-solicitante"})
    svc.transition(did, Phase.DONE, actor="teste")

    final = svc.get_demand(did)
    assert final.phase == Phase.DONE
    assert final.artefacts["triagem"]["aprovada_por"] == "Gestor"
    assert all(r["custo_usd"] == 0.0 for r in final.artefacts["geracao"].values())
    assert not any(r["estado"] == "falhou" for r in final.artefacts["geracao"].values())
    # A IA só foi chamada nas fases com rascunho (dev e review geram sem IA).
    assert len(ia.chamadas) == 4


def _rastreio_falso(ok=True, orfaos=()):
    def executar(root, produto, testes, saida):
        saida.write_text(json.dumps({
            "versao": 1, "produto": produto, "gerado_em": "2026-11-09T12:00:00Z", "ok": ok,
            "exemplos_aprovados": [], "orfaos": list(orfaos), "fantasmas": [],
        }), encoding="utf-8")
        return 0 if ok else 1
    return executar


def test_t1_nao_t2_t3_sim_valida_cada_pagina_e_refaz_o_rastreio_ate_done(tmp_path, monkeypatch):
    docs = tmp_path / "portal-docs"
    (docs / PRODUTO).mkdir(parents=True)
    monkeypatch.setenv("DOCS_REPO_PATH", str(docs))
    payloads = {**PAYLOADS, "triagem@1": {**PAYLOADS["triagem@1"], "t1": False, "t2": True, "t3": True}}
    ia = lambda template, texto: {"status": "ok", "payload": payloads[template],  # noqa: E731
                                  "cost": {"actual_usd": 0.0}, "trace_id": "t"}
    svc = DemandLifecycleService(db_path=tmp_path / "demands.db")
    verificador = {"executar": _rastreio_falso(ok=False, orfaos=[f"{PRODUTO}.x#1"])}
    gerador = GeradorDeArtefatos(svc, ia, lambda pergunta: [], docs_root,
                                 lambda *a: verificador["executar"](*a),
                                 {PRODUTO: "tests/**"}, tmp_path / "runtime")
    svc.set_gancho_fase(lambda demanda_id, fase: gerador.executar(demanda_id))

    did = svc.create_demand("Painel de reserva", "Painel", source="teste").id
    triagem = svc.get_demand(did).artefacts["triagem"]
    svc.update_artefact(did, "triagem", {**triagem, "trilha": "completa", "aprovada_por": "Gestor",
                                         "aprovada_em": "2026-11-09"})
    svc.transition(did, Phase.SPIKE, actor="teste")
    base = f"{PRODUTO}/demandas/{did.lower()}"
    svc.update_artefact(did, "visao", {"pagina": f"{base}/visao.mdx", "aprovada_por": "Gestor"})
    _validar(docs / base / "visao.mdx")
    svc.transition(did, Phase.SPEC, actor="teste")

    paginas = {"historias": "historias", "telas": "telas", "casos_de_uso": "casos-de-uso", "rnf": "rnf"}
    art = svc.get_demand(did).artefacts
    assert "regras" not in art
    assert all(art[k] == f"{base}/{nome}.mdx" for k, nome in paginas.items())
    pendentes = {f"{k}:{base}/{nome}.mdx:proposta" for k, nome in paginas.items()}
    for k, nome in paginas.items():
        assert set(_recusa(svc, did, Phase.DEV)) == pendentes
        _validar(docs / base / f"{nome}.mdx")
        pendentes.discard(f"{k}:{base}/{nome}.mdx:proposta")
    svc.transition(did, Phase.DEV, actor="teste")
    assert svc.get_demand(did).phase == Phase.DEV

    # dev -> review: o rastreio com órfão (ok falso) bloqueia a entrega.
    svc.transition(did, Phase.REVIEW, actor="teste")
    svc.update_artefact(did, "evidence", {"test_results": ["ok"]})
    svc.update_artefact(did, "aceite_area", {"area": "Atendimento", "pessoa": "area-solicitante"})
    assert _recusa(svc, did, Phase.DONE) == ["rastreio"]
    # Corrigido o teste (executor falso), refazer recalcula o rastreio e a entrega passa.
    verificador["executar"] = _rastreio_falso(ok=True)
    res = gerador.executar(did, refazer=True)
    assert res["rastreio"]["estado"] == "gerado"
    svc.transition(did, Phase.DONE, actor="teste")
    assert svc.get_demand(did).phase == Phase.DONE


@pytest.mark.parametrize("produto", ["../fora", "a/b", "..", "Portal", ""])
def test_produto_com_cara_de_caminho_nao_grava_fora_da_pasta(tmp_path, monkeypatch, produto):
    docs = tmp_path / "docs"
    docs.mkdir()
    monkeypatch.setenv("DOCS_REPO_PATH", str(docs))
    svc = DemandLifecycleService(db_path=tmp_path / "demands.db")
    gerador = GeradorDeArtefatos(svc, IAFalsa(), lambda pergunta: [], docs_root, lambda *a: 0, {}, tmp_path / "runtime")
    did = svc.create_demand("Pedido", "Texto", source="teste").id
    svc.update_artefact(did, "triagem", {**PAYLOADS["triagem@1"], "produto": produto,
                                         "aprovada_por": "gestor-demandas", "aprovada_em": "2026-11-24"})
    svc.transition(did, Phase.SPIKE, actor="teste")
    antes = sorted(p for p in tmp_path.rglob("*") if p.is_file() and p.suffix == ".mdx")
    try:
        resultados = gerador.executar(did)
    except ValueError:
        resultados = {}
    assert all(r.get("estado") != "gerado" for r in resultados.values()), resultados
    assert sorted(p for p in tmp_path.rglob("*") if p.is_file() and p.suffix == ".mdx") == antes
