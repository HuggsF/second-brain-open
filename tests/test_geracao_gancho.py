"""Ligação da geração de artefatos: gancho de fase e comando ``gerar-artefatos``."""

import logging
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.demand_lifecycle import DemandLifecycleService, Phase  # noqa: E402


def _triagem_leve():
    return {
        "t1": False, "t2": False, "t3": False, "t4": True,
        "trilha": "leve", "aprovada_por": "gestor", "aprovada_em": "2026-11-09",
        "atividade": "", "faixa": "", "criterios_de_aceite": ["x"],
        "rebaixamentos": [], "mais_de_uma_sprint": False,
    }


@pytest.fixture
def svc(tmp_path):
    return DemandLifecycleService(db_path=tmp_path / "demands.db")


# -- gancho no serviço ---------------------------------------------------------

def test_gancho_chamado_na_criacao_e_na_transicao(svc):
    chamadas = []
    svc.set_gancho_fase(lambda demanda_id, fase: chamadas.append((demanda_id, fase)))
    dem = svc.create_demand("Gancho", source="test")
    svc.update_artefact(dem.id, "triagem", _triagem_leve())
    svc.transition(dem.id, Phase.SPIKE, actor="test")
    assert chamadas == [(dem.id, "intake"), (dem.id, "spike")]


def test_gancho_nao_chamado_quando_a_transicao_e_recusada(svc):
    chamadas = []
    dem = svc.create_demand("Sem triagem", source="test")
    svc.set_gancho_fase(lambda demanda_id, fase: chamadas.append((demanda_id, fase)))
    with pytest.raises(Exception):
        svc.transition(dem.id, Phase.SPIKE, actor="test")
    assert chamadas == []


def test_gancho_desligado_com_none(svc):
    chamadas = []
    svc.set_gancho_fase(lambda demanda_id, fase: chamadas.append(fase))
    svc.set_gancho_fase(None)
    svc.create_demand("Sem gancho", source="test")
    assert chamadas == []


def test_gancho_fora_do_lock(svc):
    """The callback writes to the card (takes the service lock): it must not deadlock."""
    vistos = []

    def cb(demanda_id, fase):
        svc.update_artefact(demanda_id, "nota", fase)
        vistos.append(svc.get_demand(demanda_id).phase.value)

    svc.set_gancho_fase(cb)
    resultado = {}

    def rodar():
        dem = svc.create_demand("Lock", source="test")
        svc.update_artefact(dem.id, "triagem", _triagem_leve())
        svc.transition(dem.id, Phase.SPIKE, actor="test")
        resultado["id"] = dem.id

    t = threading.Thread(target=rodar, daemon=True)
    t.start()
    t.join(timeout=10)
    assert not t.is_alive(), "gancho chamado dentro do lock (deadlock)"
    assert vistos == ["intake", "spike"]
    assert svc.get_demand(resultado["id"]).artefacts["nota"] == "spike"


def test_gancho_que_falha_nao_desfaz_a_transicao(svc, caplog):
    def cb(demanda_id, fase):
        raise RuntimeError("gerador quebrou")

    svc.set_gancho_fase(cb)
    with caplog.at_level(logging.ERROR):
        dem = svc.create_demand("Falha", source="test")
        svc.update_artefact(dem.id, "triagem", _triagem_leve())
        atualizada, evento = svc.transition(dem.id, Phase.SPIKE, actor="test")
    assert atualizada.phase == Phase.SPIKE
    assert evento["to_phase"] == "spike"
    assert svc.get_demand(dem.id).phase == Phase.SPIKE
    assert "gerador quebrou" in caplog.text


# -- API -----------------------------------------------------------------------

class _Classificador:
    class _Resp:
        answer = '{"category": "feature", "severity": "low", "summary": "x"}'

    def chat(self, prompt):
        return self._Resp()


# -- ligação real (sem IA, sem Node) ---------------------------------

def test_montar_gerador_liga_testes_busca_e_rastreio(svc, tmp_path, monkeypatch):
    from core.geracao import ligacao

    yaml_path = tmp_path / "produtos.yaml"
    yaml_path.write_text('produto-a:\n  descricao: A\n  testes_rastreio: "C:/x/tests/**/*.test.ts"\n'
                         'produto-b:\n  descricao: B\n', encoding="utf-8")

    class _Retriever:
        def query(self, pergunta, limit=4, include_content=False, **kw):
            assert include_content
            return {"sources": [{"file_path": "vault/a.md", "section": "S", "content": "trecho"}]}

    monkeypatch.setattr(ligacao, "BrainRetriever", _Retriever)
    comandos = []

    class _Proc:
        returncode = 1

    def fake_run(cmd, **kw):
        comandos.append(cmd)
        return _Proc()

    monkeypatch.setattr(ligacao.subprocess, "run", fake_run)
    tarefas = []
    monkeypatch.setattr(ligacao, "run_task",
                        lambda task, **kw: tarefas.append((task, kw)) or {"status": "ok"})

    gerador = ligacao.montar_gerador(svc, yaml_path)
    assert gerador._testes == {"produto-a": "C:/x/tests/**/*.test.ts"}
    assert set(gerador._produtos) == {"produto-a", "produto-b"}
    assert gerador._guia_triagem == ""
    (tmp_path / "guia_triagem.md").write_text("Guia X", encoding="utf-8")
    assert ligacao.montar_gerador(svc, yaml_path)._guia_triagem == "Guia X"
    trechos = gerador._busca("pergunta")
    assert len(trechos) == 1 and "trecho" in trechos[0] and "vault/a.md" in trechos[0]
    docs = tmp_path / "docs"
    codigo = gerador._executar_rastreio(docs, "produto-a", "glob", tmp_path / "s.json")
    assert codigo == 1
    assert comandos == [["node", str(docs / "tools" / "rastreio" / "cli.ts"), "--docs", str(docs),
                         "--produto", "produto-a", "--testes", "glob", "--saida", str(tmp_path / "s.json")]]
    gerador._cliente_ia("tpl", "texto")
    assert tarefas == [("extract", {"text": "texto", "template": "tpl", "sender": "gerador",
                                    "trace_id": None})]


def test_montar_gerador_sem_yaml_nao_tem_testes(svc, tmp_path):
    from core.geracao import ligacao
    assert ligacao.montar_gerador(svc, tmp_path / "ausente.yaml")._testes == {}


def test_busca_falha_quando_retriever_falha(svc, tmp_path, monkeypatch):
    from core.geracao import ligacao

    def quebra(*a, **kw):
        raise ConnectionError("índice parado")

    monkeypatch.setattr(ligacao, "BrainRetriever", quebra)
    gerador = ligacao.montar_gerador(svc, tmp_path / "ausente.yaml")
    with pytest.raises(ConnectionError):
        gerador._busca("pergunta")


# -- comando gerar-artefatos -----------------------------------------------------

def _cli_com_gerador(monkeypatch, svc, resultados):
    import cli
    from core import demand_lifecycle
    from core.geracao import ligacao

    chamadas = []

    class _Gerador:
        def executar(self, demanda_id, refazer=False):
            chamadas.append((demanda_id, refazer))
            return resultados

    monkeypatch.setattr(ligacao, "montar_gerador", lambda s, p: _Gerador())
    monkeypatch.setattr(demand_lifecycle, "DemandLifecycleService", lambda *a, **kw: svc)
    return cli, chamadas


def test_cli_gerar_artefatos_sai_1_quando_falha(svc, monkeypatch):
    from click.testing import CliRunner
    dem = svc.create_demand("CLI", source="test")
    cli, chamadas = _cli_com_gerador(monkeypatch, svc, {
        "visao": {"estado": "gerado", "caminho": "p/visao.mdx", "motivo": ""},
        "historias": {"estado": "falhou", "caminho": None, "motivo": "provedor: timeout"},
    })
    res = CliRunner().invoke(cli.cli, ["gerar-artefatos", dem.id, "--refazer"])
    assert res.exit_code == 1, res.output
    assert "visao: gerado p/visao.mdx" in res.output
    assert "historias: falhou provedor: timeout" in res.output
    assert chamadas == [(dem.id, True)]


def test_cli_gerar_artefatos_sai_0_sem_falha(svc, monkeypatch):
    from click.testing import CliRunner
    dem = svc.create_demand("CLI", source="test")
    cli, chamadas = _cli_com_gerador(monkeypatch, svc, {
        "regras": {"estado": "pulado", "caminho": ["p/regras/R-1.mdx"], "motivo": ""},
    })
    res = CliRunner().invoke(cli.cli, ["gerar-artefatos", dem.id])
    assert res.exit_code == 0, res.output
    assert "regras: pulado p/regras/R-1.mdx" in res.output
    assert chamadas == [(dem.id, False)]


def test_cli_gerar_artefatos_demanda_inexistente_sai_1(svc, monkeypatch):
    from click.testing import CliRunner
    cli, chamadas = _cli_com_gerador(monkeypatch, svc, {})
    res = CliRunner().invoke(cli.cli, ["gerar-artefatos", "DEM-999"])
    assert res.exit_code == 1
    assert "DEM-999" in res.output
    assert chamadas == []
