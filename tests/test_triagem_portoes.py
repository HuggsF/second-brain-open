"""Portões do ciclo de vida por trilha da triagem."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.demand_lifecycle import (  # noqa: E402
    DemandLifecycleService,
    MissingArtefactError,
    Phase,
)
from core.triagem import Trilha  # noqa: E402


def _triagem(trilha="leve", aprovada_por="gestor", **extra):
    base = {
        "t1": False, "t2": False, "t3": False, "t4": True,
        "trilha": trilha, "aprovada_por": aprovada_por, "aprovada_em": "2026-11-09",
        "atividade": "", "faixa": "",
        "criterios_de_aceite": ["x"], "rebaixamentos": [], "mais_de_uma_sprint": False,
    }
    base.update(extra)
    return base


def _pagina(root: Path, rel: str, status="aprovada", versao=1, areas=("negocio",), avais=None):
    if avais is None:
        avais = [{"area": a, "versao": versao} for a in areas]
    rule_id = f"{rel.split('/')[0]}.{Path(rel).stem.lower()}"
    linhas = ["---", f"id: {rule_id}", "title: Pagina", "dono: { area: negocio, pessoa: X }",
              f"status: {status}", f"versao: {versao}",
              f"areas_aval: [{', '.join(areas)}]", "avais:"]
    for a in avais:
        linhas += [f"  - area: {a['area']}", "    pessoa: X", "    data: 2026-11-09",
                   f"    versao: {a['versao']}", "    email: area-solicitante@empresa.example"]
    if not avais:
        linhas[-1] = "avais: []"
    linhas += ["---", "", "## Exemplos", "| # | Caso |", "|---|---|", "| 1 | a |", "| 2 | b |", "",
               "## Perguntas em aberto", "Nenhuma."]
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(linhas) + "\n", encoding="utf-8")


@pytest.fixture
def svc(tmp_path):
    return DemandLifecycleService(db_path=tmp_path / "demands.db")


@pytest.fixture
def docs(tmp_path, monkeypatch):
    root = tmp_path / "docs"
    root.mkdir()
    monkeypatch.setenv("DOCS_REPO_PATH", str(root))
    return root


def _completa_em_spec(svc, t1=True):
    dem = svc.create_demand("Completa", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem("completa", t1=t1, t4=False))
    svc.transition(dem.id, Phase.SPIKE, actor="test")
    svc.update_artefact(dem.id, "visao", {"pagina": "projeto/visao.mdx", "aprovada_por": "gestor"})
    return dem


# -- intake -> spike -----------------------------------------------------------

def test_intake_spike_sem_triagem_recusa(svc):
    dem = svc.create_demand("Sem triagem", source="test")
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.SPIKE, actor="test")
    assert exc.value.missing == ["triagem"]
    assert svc.get_demand(dem.id).phase == Phase.INTAKE


def test_intake_spike_com_triagem_nao_aprovada_recusa(svc):
    dem = svc.create_demand("Sugerida", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem(aprovada_por=""))
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.SPIKE, actor="test")
    assert exc.value.missing == ["triagem"]
    assert "aprovada_por" in str(exc.value)


def test_demanda_sem_triagem_pode_receber_triagem_e_seguir(svc):
    dem = svc.create_demand("Depois", source="test")
    with pytest.raises(MissingArtefactError):
        svc.transition(dem.id, Phase.SPIKE, actor="test")
    svc.update_artefact(dem.id, "triagem", _triagem())
    dem, _ = svc.transition(dem.id, Phase.SPIKE, actor="test")
    assert dem.phase == Phase.SPIKE


# -- spec -> dev (completa) ----------------------------------------------------

def test_completa_spec_dev_com_regra_proposta_recusa_citando_a_pagina(svc, docs):
    _pagina(docs, "projeto/visao.mdx")
    _pagina(docs, "projeto/historias.mdx")
    _pagina(docs, "projeto/regras/R-1.mdx", status="proposta")
    dem = _completa_em_spec(svc)
    svc.transition(dem.id, Phase.SPEC, actor="test")
    svc.update_artefact(dem.id, "historias", "projeto/historias.mdx")
    svc.update_artefact(dem.id, "regras", ["projeto/regras/R-1.mdx"])
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.DEV, actor="test")
    assert exc.value.missing == ["regras:projeto/regras/R-1.mdx"]
    assert svc.get_demand(dem.id).phase == Phase.SPEC


def test_completa_spec_dev_com_regras_aprovadas_passa(svc, docs):
    _pagina(docs, "projeto/visao.mdx")
    _pagina(docs, "projeto/historias.mdx")
    _pagina(docs, "projeto/regras/R-1.mdx")
    dem = _completa_em_spec(svc)
    svc.transition(dem.id, Phase.SPEC, actor="test")
    svc.update_artefact(dem.id, "historias", {"pagina": "projeto/historias.mdx"})
    svc.update_artefact(dem.id, "regras", ["projeto/regras/R-1.mdx"])
    dem, _ = svc.transition(dem.id, Phase.DEV, actor="test")
    assert dem.phase == Phase.DEV


def test_spec_dev_sem_pasta_de_documentos_recusa_com_docs_repo(svc, docs, monkeypatch):
    _pagina(docs, "projeto/visao.mdx")
    dem = _completa_em_spec(svc)
    svc.transition(dem.id, Phase.SPEC, actor="test")
    svc.update_artefact(dem.id, "historias", "projeto/historias.mdx")
    svc.update_artefact(dem.id, "regras", ["projeto/regras/R-1.mdx"])
    monkeypatch.delenv("DOCS_REPO_PATH", raising=False)
    monkeypatch.setattr("config.settings.fichas_dir", docs / "sem-fichas")
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.DEV, actor="test")
    assert exc.value.missing == ["docs_repo"]
    assert "pasta de fichas inexistente" in str(exc.value)


def test_spec_dev_sem_variavel_le_as_paginas_da_pasta_de_fichas(svc, docs, monkeypatch):
    _pagina(docs, "projeto/visao.mdx")
    dem = _completa_em_spec(svc)
    svc.transition(dem.id, Phase.SPEC, actor="test")
    svc.update_artefact(dem.id, "historias", "projeto/historias.mdx")
    svc.update_artefact(dem.id, "regras", ["projeto/regras/R-1.mdx"])
    monkeypatch.delenv("DOCS_REPO_PATH", raising=False)
    monkeypatch.setattr("config.settings.fichas_dir", docs)
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.DEV, actor="test")
    assert "docs_repo" not in exc.value.missing
    assert "historias:projeto/historias.mdx" in exc.value.missing


# -- rebaixamento --------------------------------------------------------------

def test_rebaixar_sem_motivo_recusa(svc):
    dem = svc.create_demand("Rebaixar", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem("completa"))
    for motivo in ("", "   "):
        with pytest.raises(ValueError):
            svc.rebaixar_trilha(dem.id, Trilha.LEVE, motivo=motivo, actor="gestor")
    assert svc.get_demand(dem.id).artefacts["triagem"]["trilha"] == "completa"


def test_rebaixar_grava_motivo_e_autor(svc):
    dem = svc.create_demand("Rebaixar", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem("completa"))
    dem = svc.rebaixar_trilha(dem.id, Trilha.LEVE, motivo="escopo reduzido", actor="gestor")
    tri = dem.artefacts["triagem"]
    assert tri["trilha"] == "leve"
    assert tri["rebaixamentos"][-1]["de"] == "completa"
    assert tri["rebaixamentos"][-1]["para"] == "leve"
    assert tri["rebaixamentos"][-1]["motivo"] == "escopo reduzido"
    assert tri["rebaixamentos"][-1]["autor"] == "gestor"
    ultimo = dem.agent_history[-1]
    assert ultimo["agent_id"] == "gestor"
    assert ultimo["action"] == "rebaixar_trilha:completa->leve"
    assert ultimo["details"] == "escopo reduzido"


# -- validate_artefacts --------------------------------------------------------

def test_validate_artefacts_segue_a_trilha(svc, docs):
    _pagina(docs, "projeto/visao.mdx")
    _pagina(docs, "projeto/historias.mdx")
    dem = _completa_em_spec(svc)
    svc.transition(dem.id, Phase.SPEC, actor="test")
    svc.update_artefact(dem.id, "historias", "projeto/historias.mdx")
    res = svc.validate_artefacts(dem.id, Phase.DEV)
    assert res["valid"] is False
    assert "regras" in res["missing"]
    assert res["required"] == ["historias", "regras"]


# -- bloqueio com "aguardando" -------------------------------------------------

def _em_spike(svc):
    dem = svc.create_demand("Bloquear", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem())
    svc.transition(dem.id, Phase.SPIKE, actor="test")
    return dem


def test_bloquear_com_aguardando_fora_da_lista_recusa(svc):
    dem = _em_spike(svc)
    with pytest.raises(ValueError):
        svc.block_demand(dem.id, waiting_on="x", aguardando="papa", actor="gestor-demandas")
    assert svc.get_demand(dem.id).phase == Phase.SPIKE


def test_bloquear_com_aguardando_valido_grava_no_blocked_metadata(svc):
    dem = _em_spike(svc)
    dem, _ = svc.block_demand(dem.id, waiting_on="resposta do gestor", aguardando="gestor", actor="gestor-demandas")
    assert dem.phase == Phase.BLOCKED
    assert dem.blocked_metadata["aguardando"] == "gestor"
    assert dem.blocked_metadata["waiting_on"] == "resposta do gestor"


# -- fix round 1: trilha aprovada em todo portao; desbloqueio volta a origem --

def _em_spike_na_trilha(svc, trilha):
    dem = svc.create_demand("Desaprovar", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem(trilha))
    svc.transition(dem.id, Phase.SPIKE, actor="test")
    return dem


@pytest.mark.parametrize("trilha", ["completa", "operacional"])
def test_spike_spec_com_triagem_desaprovada_recusa(svc, trilha):
    dem = _em_spike_na_trilha(svc, trilha)
    svc.update_artefact(dem.id, "triagem", _triagem(trilha, aprovada_por=""))
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.SPEC, actor="test")
    assert exc.value.missing == ["triagem"]
    assert "aprovada_por" in str(exc.value)
    assert svc.validate_artefacts(dem.id, Phase.SPEC)["missing"] == ["triagem"]


@pytest.mark.parametrize("trilha", ["completa", "operacional"])
def test_spec_dev_com_triagem_desaprovada_recusa(svc, docs, trilha):
    _pagina(docs, "projeto/visao.mdx")
    dem = _em_spike_na_trilha(svc, trilha)
    svc.update_artefact(dem.id, "visao", {"pagina": "projeto/visao.mdx", "aprovada_por": "gestor"})
    svc.transition(dem.id, Phase.SPEC, actor="test")
    svc.update_artefact(dem.id, "triagem", _triagem(trilha, aprovada_por=""))
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.DEV, actor="test")
    assert exc.value.missing == ["triagem"]
    assert "aprovada_por" in str(exc.value)
    assert svc.get_demand(dem.id).phase == Phase.SPEC


def test_transicao_simples_para_blocked_grava_origem(svc):
    dem = _em_spike(svc)
    dem, _ = svc.transition(dem.id, Phase.BLOCKED, actor="gestor-demandas", reason="parado")
    assert dem.phase == Phase.BLOCKED
    assert dem.blocked_metadata["origin_phase"] == "spike"
    assert dem.blocked_metadata["blocked_by"] == "gestor-demandas"


@pytest.mark.parametrize("alvo", [Phase.DEV, Phase.REVIEW, Phase.SPEC])
def test_spike_blocked_simples_para_outra_fase_recusa(svc, alvo):
    from core.demand_lifecycle import InvalidTransitionError
    dem = _em_spike(svc)
    svc.transition(dem.id, Phase.BLOCKED, actor="gestor-demandas")
    with pytest.raises(InvalidTransitionError):
        svc.transition(dem.id, alvo, actor="gestor-demandas")
    assert svc.get_demand(dem.id).phase == Phase.BLOCKED


def test_spike_blocked_simples_volta_para_spike(svc):
    dem = _em_spike(svc)
    svc.transition(dem.id, Phase.BLOCKED, actor="gestor-demandas")
    dem, _ = svc.transition(dem.id, Phase.SPIKE, actor="gestor-demandas")
    assert dem.phase == Phase.SPIKE
    assert dem.blocked_metadata is None


def test_desbloqueio_sem_origem_registrada_recusa(svc):
    import sqlite3
    from core.demand_lifecycle import InvalidTransitionError
    dem = _em_spike(svc)
    conn = sqlite3.connect(str(svc._db_path))
    conn.execute("UPDATE demands SET phase = 'blocked', blocked_metadata = NULL WHERE id = ?", (dem.id,))
    conn.commit()
    conn.close()
    with pytest.raises(InvalidTransitionError, match="origin"):
        svc.transition(dem.id, Phase.DEV, actor="gestor-demandas")
    # INTAKE e CANCELLED continuam permitidos
    dem, _ = svc.transition(dem.id, Phase.INTAKE, actor="gestor-demandas")
    assert dem.phase == Phase.INTAKE


# -- review -> done: resultado do verificador de rastreio --------------------------

def _em_review(svc, docs, trilha="completa"):
    _pagina(docs, "projeto/visao.mdx")
    _pagina(docs, "projeto/historias.mdx")
    dem = svc.create_demand("Entrega", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem(trilha, t4=trilha == "leve"))
    svc.transition(dem.id, Phase.SPIKE, actor="test")
    svc.update_artefact(dem.id, "visao", {"pagina": "projeto/visao.mdx", "aprovada_por": "gestor"})
    svc.transition(dem.id, Phase.SPEC, actor="test")
    svc.update_artefact(dem.id, "historias", {"pagina": "projeto/historias.mdx"})
    svc.transition(dem.id, Phase.DEV, actor="test")
    svc.transition(dem.id, Phase.REVIEW, actor="test")
    svc.update_artefact(dem.id, "evidence", "ok")
    return dem


def _rastreio(tmp_path, **campos):
    import json
    dados = {"versao": 1, "produto": "portal", "gerado_em": "2026-11-09T10:00:00Z",
             "ok": True, "exemplos_aprovados": 12, "orfaos": [], "fantasmas": []}
    dados.update(campos)
    caminho = tmp_path / "rastreio.json"
    caminho.write_text(json.dumps(dados), encoding="utf-8")
    return caminho


def test_review_done_completa_sem_rastreio_recusa(svc, docs):
    dem = _em_review(svc, docs)
    svc.update_artefact(dem.id, "aceite_area", {"aprovada_por": "area"})
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.DONE, actor="test")
    assert "rastreio" in exc.value.missing


def test_review_done_com_rastreio_ok_false_recusa_listando_orfaos(svc, docs, tmp_path):
    dem = _em_review(svc, docs)
    svc.update_artefact(dem.id, "aceite_area", {"aprovada_por": "area"})
    svc.update_artefact(dem.id, "rastreio", str(_rastreio(
        tmp_path, ok=False, orfaos=["portal.x#1", "portal.x#2"], fantasmas=["t.y"])))
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.DONE, actor="test")
    assert "rastreio" in exc.value.missing
    assert "rastreio: 2 exemplos sem teste: portal.x#1, portal.x#2" in exc.value.detail
    assert "t.y" in exc.value.detail


def test_review_done_com_json_invalido_recusa(svc, docs, tmp_path):
    dem = _em_review(svc, docs)
    svc.update_artefact(dem.id, "aceite_area", {"aprovada_por": "area"})
    ruim = tmp_path / "ruim.json"
    ruim.write_text("{nao e json", encoding="utf-8")
    svc.update_artefact(dem.id, "rastreio", str(ruim))
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.DONE, actor="test")
    assert "rastreio" in exc.value.missing
    assert "inválido" in exc.value.detail


def test_review_done_com_rastreio_ok_passa(svc, docs, tmp_path):
    dem = _em_review(svc, docs)
    svc.update_artefact(dem.id, "aceite_area", {"aprovada_por": "area"})
    svc.update_artefact(dem.id, "rastreio", str(_rastreio(tmp_path)))
    dem, _ = svc.transition(dem.id, Phase.DONE, actor="test")
    assert dem.phase == Phase.DONE


def test_review_done_leve_nao_exige_rastreio(svc, docs):
    dem = _em_review(svc, docs, trilha="leve")
    dem, _ = svc.transition(dem.id, Phase.DONE, actor="test")
    assert dem.phase == Phase.DONE


def test_erros_rastreio_ausente_e_versao():
    import json, tempfile
    from core.triagem import erros_rastreio
    assert "não encontrado" in erros_rastreio(Path("/nao/existe.json"))[0]
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "v.json"
        p.write_text(json.dumps({"versao": 2, "ok": True}), encoding="utf-8")
        assert "versão" in erros_rastreio(p)[0]


# -- trilha so muda por rebaixar_trilha, com registro e aprovacao ---------------

def test_update_artefact_trocando_trilha_recusa(svc, docs):
    dem = _completa_em_spec(svc)
    with pytest.raises(ValueError, match="rebaixar_trilha"):
        svc.update_artefact(dem.id, "triagem", _triagem("operacional", t1=True, t4=False))
    tri = svc.get_demand(dem.id).artefacts["triagem"]
    assert tri["trilha"] == "completa"


def test_update_artefact_triagem_sem_trilha_recusa(svc):
    dem = svc.create_demand("Sem trilha", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem("completa"))
    with pytest.raises(ValueError):
        svc.update_artefact(dem.id, "triagem", {"t1": False})
    with pytest.raises(ValueError):
        svc.update_artefact(dem.id, "triagem", "texto")


def test_update_artefact_mesma_trilha_aceita(svc):
    dem = svc.create_demand("Mesma", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem("completa"))
    dem = svc.update_artefact(dem.id, "triagem", _triagem("completa", aprovada_por=""))
    assert dem.artefacts["triagem"]["aprovada_por"] == ""


def test_update_artefact_nao_forja_rebaixamentos(svc):
    dem = svc.create_demand("Forjar", source="test")
    falso = [{"de": "completa", "para": "leve", "motivo": "x", "autor": "y", "em": "z"}]
    with pytest.raises(ValueError, match="rebaixamentos"):
        svc.update_artefact(dem.id, "triagem", _triagem("leve", t1=True, rebaixamentos=falso))
    assert "triagem" not in svc.get_demand(dem.id).artefacts


def test_update_artefact_sem_rebaixamentos_preserva_registro(svc):
    dem = svc.create_demand("Preserva", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem("completa"))
    svc.rebaixar_trilha(dem.id, Trilha.LEVE, motivo="escopo reduzido", actor="gestor")
    novo = _triagem("leve")
    del novo["rebaixamentos"]
    dem = svc.update_artefact(dem.id, "triagem", novo)
    assert dem.artefacts["triagem"]["rebaixamentos"][-1]["motivo"] == "escopo reduzido"
    with pytest.raises(ValueError, match="rebaixamentos"):
        svc.update_artefact(dem.id, "triagem", _triagem("leve", rebaixamentos=[]))


def test_rebaixar_aprova_a_nova_trilha(svc):
    dem = svc.create_demand("Aprova", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem("completa", aprovada_por="outro"))
    dem = svc.rebaixar_trilha(dem.id, Trilha.LEVE, motivo="escopo reduzido", actor="gestor-demandas")
    tri = dem.artefacts["triagem"]
    assert tri["trilha"] == "leve"
    assert tri["aprovada_por"] == "gestor-demandas"
    assert tri["aprovada_em"] and tri["aprovada_em"] == tri["rebaixamentos"][-1]["em"]


def test_probe_sobrescrever_triagem_em_spec_nao_chega_a_dev(svc, docs):
    _pagina(docs, "projeto/visao.mdx")
    dem = _completa_em_spec(svc)
    svc.transition(dem.id, Phase.SPEC, actor="test")
    with pytest.raises(ValueError):
        svc.update_artefact(dem.id, "triagem", _triagem("operacional", t1=True, t4=False))
    with pytest.raises(MissingArtefactError):
        svc.transition(dem.id, Phase.DEV, actor="test")
    assert svc.get_demand(dem.id).phase == Phase.SPEC


def test_probe_leve_com_t1_sim_nao_avanca(svc):
    dem = svc.create_demand("Leve T1", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem("leve", t1=True))
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.SPIKE, actor="test")
    assert exc.value.missing == ["triagem"]
    assert "t1" in exc.value.detail


def test_rebaixada_com_t1_sim_avanca(svc):
    dem = svc.create_demand("Rebaixada", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem("completa", t1=True, t4=False))
    svc.rebaixar_trilha(dem.id, Trilha.LEVE, motivo="regra ja aprovada noutra demanda", actor="gestor-demandas")
    dem, _ = svc.transition(dem.id, Phase.SPIKE, actor="test")
    assert dem.phase == Phase.SPIKE


# -- review -> done reconfere as regras e o produto do rastreio --------------

def _em_review_com_regras(svc, docs, regras=("portal/regras/R-1.mdx",)):
    _pagina(docs, "portal/visao.mdx")
    _pagina(docs, "portal/historias.mdx")
    for rel in regras:
        _pagina(docs, rel)
    dem = svc.create_demand("Entrega com regra", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem("completa", t1=True, t4=False))
    svc.transition(dem.id, Phase.SPIKE, actor="test")
    svc.update_artefact(dem.id, "visao", {"pagina": "portal/visao.mdx", "aprovada_por": "gestor"})
    svc.transition(dem.id, Phase.SPEC, actor="test")
    svc.update_artefact(dem.id, "historias", "portal/historias.mdx")
    svc.update_artefact(dem.id, "regras", list(regras))
    svc.transition(dem.id, Phase.DEV, actor="test")
    svc.transition(dem.id, Phase.REVIEW, actor="test")
    svc.update_artefact(dem.id, "evidence", "ok")
    svc.update_artefact(dem.id, "aceite_area", {"aprovada_por": "area"})
    return dem


def test_review_done_com_regra_voltando_a_proposta_recusa(svc, docs, tmp_path):
    dem = _em_review_com_regras(svc, docs)
    svc.update_artefact(dem.id, "rastreio", str(_rastreio(tmp_path)))
    _pagina(docs, "portal/regras/R-1.mdx", status="proposta", versao=2)
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.DONE, actor="test")
    assert exc.value.missing == ["regras:portal/regras/R-1.mdx"]
    assert svc.get_demand(dem.id).phase == Phase.REVIEW
    assert svc.validate_artefacts(dem.id, Phase.DONE)["missing"] == ["regras:portal/regras/R-1.mdx"]


def test_review_done_com_rastreio_de_outro_produto_recusa(svc, docs, tmp_path):
    dem = _em_review_com_regras(svc, docs)
    svc.update_artefact(dem.id, "rastreio", str(_rastreio(tmp_path, produto="outro")))
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.DONE, actor="test")
    assert exc.value.missing == ["rastreio"]
    assert "outro" in exc.value.detail and "portal" in exc.value.detail


def test_review_done_com_rastreio_do_produto_das_regras_passa(svc, docs, tmp_path):
    dem = _em_review_com_regras(svc, docs)
    svc.update_artefact(dem.id, "rastreio", str(_rastreio(tmp_path, produto="portal")))
    dem, _ = svc.transition(dem.id, Phase.DONE, actor="test")
    assert dem.phase == Phase.DONE


def test_review_done_com_regras_de_produtos_diferentes_recusa(svc, docs, tmp_path):
    dem = _em_review_com_regras(svc, docs, regras=("portal/regras/R-1.mdx", "estoque/regras/R-2.mdx"))
    svc.update_artefact(dem.id, "rastreio", str(_rastreio(tmp_path, produto="portal")))
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.DONE, actor="test")
    assert "rastreio" in exc.value.missing
    assert "estoque" in exc.value.detail and "portal" in exc.value.detail


def test_erros_rastreio_confere_produto_esperado(tmp_path):
    from core.triagem import erros_rastreio
    caminho = _rastreio(tmp_path, produto="outro")
    assert erros_rastreio(caminho) == []
    assert erros_rastreio(caminho, produto="outro") == []
    erros = erros_rastreio(caminho, produto="portal")
    assert len(erros) == 1 and "outro" in erros[0] and "portal" in erros[0]


# -- T7 / T9 -------------------------------------------------------------------

def test_pagina_fora_do_repositorio_recusa_no_portao(svc, docs, tmp_path):
    _pagina(tmp_path, "fora.mdx")
    dem = svc.create_demand("Fora", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem("completa"))
    svc.transition(dem.id, Phase.SPIKE, actor="test")
    svc.update_artefact(dem.id, "visao", {"pagina": "../fora.mdx", "aprovada_por": "gestor"})
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.SPEC, actor="test")
    assert "docs_repo" in exc.value.missing
    assert "fora do repositório" in exc.value.detail


@pytest.mark.parametrize("campo,valor", [("orfaos", 5), ("fantasmas", "t.y"), ("orfaos", {"a": 1})])
def test_erros_rastreio_listas_invalidas(tmp_path, campo, valor):
    from core.triagem import erros_rastreio
    erros = erros_rastreio(_rastreio(tmp_path, **{campo: valor}))
    assert len(erros) == 1 and "arquivo inválido" in erros[0] and campo in erros[0]


# -- rascunho gerado (status proposta) não abre portão ------------------

def _pagina_simples(root: Path, rel: str, status: str | None):
    linhas = ["---", "title: Rascunho"] + ([f"status: {status}"] if status else []) + ["---", "", "Corpo."]
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def _validar(root: Path, rel: str, status="validada"):
    path = root / rel
    path.write_text(path.read_text(encoding="utf-8").replace("status: proposta", f"status: {status}"),
                    encoding="utf-8")


_PAGINAS_SPEC = {"historias": "projeto/historias.mdx", "telas": "projeto/telas.mdx",
                 "casos_de_uso": "projeto/casos-de-uso.mdx", "rnf": "projeto/rnf.mdx"}


def _completa_t2_t3_em_spec(svc, docs):
    _pagina(docs, "projeto/visao.mdx")
    dem = svc.create_demand("T2 e T3", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem("completa", t1=False, t2=True, t3=True, t4=False))
    svc.transition(dem.id, Phase.SPIKE, actor="test")
    svc.update_artefact(dem.id, "visao", {"pagina": "projeto/visao.mdx", "aprovada_por": "gestor"})
    svc.transition(dem.id, Phase.SPEC, actor="test")
    for key, rel in _PAGINAS_SPEC.items():
        _pagina_simples(docs, rel, "validada")
        svc.update_artefact(dem.id, key, rel)
    return dem


@pytest.mark.parametrize("key", sorted(_PAGINAS_SPEC))
def test_spec_dev_recusa_pagina_em_proposta_e_passa_validada(svc, docs, key):
    dem = _completa_t2_t3_em_spec(svc, docs)
    rel = _PAGINAS_SPEC[key]
    _pagina_simples(docs, rel, "proposta")
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.DEV, actor="test")
    assert exc.value.missing == [f"{key}:{rel}:proposta"]
    assert svc.get_demand(dem.id).phase == Phase.SPEC
    _validar(docs, rel)
    dem, _ = svc.transition(dem.id, Phase.DEV, actor="test")
    assert dem.phase == Phase.DEV


def test_spec_dev_aceita_pagina_aprovada_e_pagina_sem_status(svc, docs):
    dem = _completa_t2_t3_em_spec(svc, docs)
    _pagina_simples(docs, _PAGINAS_SPEC["telas"], None)  # escrita à mão antes de existir a geração
    _pagina_simples(docs, _PAGINAS_SPEC["rnf"], "aprovada")
    dem, _ = svc.transition(dem.id, Phase.DEV, actor="test")
    assert dem.phase == Phase.DEV


def test_spike_spec_recusa_cronograma_em_proposta(svc, docs):
    _pagina(docs, "projeto/visao.mdx")
    _pagina_simples(docs, "projeto/cronograma.mdx", "proposta")
    dem = svc.create_demand("Cronograma", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem("completa", t4=False, mais_de_uma_sprint=True))
    svc.transition(dem.id, Phase.SPIKE, actor="test")
    svc.update_artefact(dem.id, "visao", {"pagina": "projeto/visao.mdx", "aprovada_por": "gestor"})
    svc.update_artefact(dem.id, "cronograma", "projeto/cronograma.mdx")
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.SPEC, actor="test")
    assert exc.value.missing == ["cronograma:projeto/cronograma.mdx:proposta"]
    _validar(docs, "projeto/cronograma.mdx")
    dem, _ = svc.transition(dem.id, Phase.SPEC, actor="test")
    assert dem.phase == Phase.SPEC


def test_spike_spec_recusa_visao_em_proposta_mesmo_com_aprovada_por(svc, docs):
    _pagina_simples(docs, "projeto/visao.mdx", "proposta")
    dem = svc.create_demand("Visao", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem("completa", t4=False))
    svc.transition(dem.id, Phase.SPIKE, actor="test")
    svc.update_artefact(dem.id, "visao", {"pagina": "projeto/visao.mdx", "aprovada_por": "gestor"})
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.SPEC, actor="test")
    assert exc.value.missing == ["visao:projeto/visao.mdx:proposta"]


# -- produto do catálogo ---------------------------------------------

def test_intake_spike_com_produto_fora_do_catalogo_recusa(svc):
    svc.set_produtos({"produto-a"})
    dem = svc.create_demand("Produto inventado", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem(produto="inventado"))
    with pytest.raises(MissingArtefactError) as exc:
        svc.transition(dem.id, Phase.SPIKE, actor="test")
    assert exc.value.missing == ["triagem"] and "fora do catálogo" in str(exc.value)
    assert svc.pendencias(dem.id) == ["triagem"]
    svc.update_artefact(dem.id, "triagem", _triagem(produto="produto-a"))
    dem, _ = svc.transition(dem.id, Phase.SPIKE, actor="test")
    assert dem.phase == Phase.SPIKE


def test_sem_catalogo_o_portao_nao_confere_produto(svc):
    dem = svc.create_demand("Sem catálogo", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem(produto="inventado"))
    dem, _ = svc.transition(dem.id, Phase.SPIKE, actor="test")
    assert dem.phase == Phase.SPIKE
