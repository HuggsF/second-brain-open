import sqlite3
import threading
from pathlib import Path

import pytest
import yaml

from core.demand_lifecycle import DemandLifecycleService
from core.docs_registry import DocsRegistryError, exemplos_da_regra
from core.geracao.gerador import GeradorDeArtefatos
from core.geracao.render import render_regras
from core.triagem import TRIAGEM_TEMPLATE

PRODUTO = "prod-a"

TRIAGEM_IA = {
    "produto": PRODUTO, "t1": True, "t2": False, "t3": False, "t4": False, "trilha": "completa",
    "atividade": "desenvolvimento", "faixa": "media", "criterios_de_aceite": ["c1"],
    "mais_de_uma_sprint": False, "justificativa": "regra nova",
}

VISAO = {"problema": "P", "cenario_atual": "A", "cenario_desejado": "D",
         "escopo_dentro": ["i1"], "escopo_fora": ["f1"],
         "setores": [{"area": "Fin", "papel": "aprova"}],
         "riscos": [{"risco": "r", "mitigacao": "m"}]}

HISTORIAS = {"epico": "E", "historias": [{"id": "H1", "persona": "Analista", "quero": "ver",
                                          "para": "x", "regras_citadas": [], "criterios": ["c"]}]}


def _regra(slug_="agrupamento", n=2):
    return {"slug": slug_, "titulo": "Agrupamento", "regra": "Uma por cliente.",
            "exemplos": [{"dado": f"d{i}", "quando": f"q{i}", "entao": f"e{i}"} for i in range(n)],
            "por_que": "Evita ruído.", "se_nao_existisse": "Várias.", "perguntas": []}


REGRAS = {"regras": [_regra()]}

PAYLOADS = {"triagem@1": TRIAGEM_IA, "visao@1": VISAO, "historias@1": HISTORIAS, "regras@1": REGRAS}


class ClienteFalso:
    def __init__(self, payloads=None, envelope=None, antes=None):
        self.payloads = dict(PAYLOADS, **(payloads or {}))
        self.envelope = envelope
        self.antes = antes
        self.chamadas = []

    def __call__(self, template, texto):
        self.chamadas.append(template)
        if self.antes:
            self.antes()
        if self.envelope is not None:
            return self.envelope
        return {"status": "ok", "reason": "", "payload": self.payloads[template],
                "cost": {"actual_usd": 0.0003, "provider": "fake"}, "trace_id": "tr-1"}


@pytest.fixture
def svc(tmp_path):
    return DemandLifecycleService(db_path=tmp_path / "demands.db")


@pytest.fixture
def docs(tmp_path):
    d = tmp_path / "docs"
    d.mkdir()
    return d


def _gerador(svc, docs, cliente, rastreio=None, testes=None, root=None):
    def docs_root():
        if root is not None:
            return root()
        return docs
    return GeradorDeArtefatos(svc, cliente, lambda q: ["trecho"], docs_root,
                              rastreio or (lambda *a: 0), testes or {}, svc._db_path.parent)


def _fase(svc, demand_id, fase):
    conn = sqlite3.connect(str(svc._db_path))
    conn.execute("UPDATE demands SET phase = ? WHERE id = ?", (fase, demand_id))
    conn.commit()
    conn.close()


def _demanda(svc, fase="intake", triagem=None, **artefatos):
    d = svc.create_demand("Agrupar reserva", "Uma reserva por cliente")
    if triagem is not None:
        svc.update_artefact(d.id, "triagem", triagem)
    for k, v in artefatos.items():
        svc.update_artefact(d.id, k, v)
    _fase(svc, d.id, fase)
    return d.id


def _triagem_aprovada(**extra):
    return {**TRIAGEM_TEMPLATE, **TRIAGEM_IA, "aprovada_por": "Gestor", "aprovada_em": "2026-11-09", **extra}


def _aprovar(docs, rel):
    p = docs / rel
    texto = p.read_text(encoding="utf-8")
    _, fm, corpo = texto.split("---\n", 2)
    dados = yaml.safe_load(fm)
    dados.update({"status": "aprovada", "dono": {"area": "Fin", "pessoa": "X"}, "areas_aval": ["Fin"],
                  "avais": [{"area": "Fin", "pessoa": "X", "data": "2026-11-09", "email": "area-solicitante@empresa.example", "versao": 1}]})
    corpo = corpo.split("## Perguntas em aberto")[0] + "## Perguntas em aberto\n\nNenhuma.\n"
    p.write_text("---\n" + yaml.safe_dump(dados, allow_unicode=True, sort_keys=False) + "---\n" + corpo,
                 encoding="utf-8")


def _escrever_regra(docs, regra=None):
    (rel, mdx), = render_regras({"regras": [regra or _regra()]}, PRODUTO)
    p = docs / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(mdx, encoding="utf-8")
    return rel


def test_gera_triagem_na_criacao(svc, docs):
    did = _demanda(svc)
    cliente = ClienteFalso()
    res = _gerador(svc, docs, cliente).executar(did)
    assert res["triagem"]["estado"] == "gerado"
    assert res["triagem"]["custo_usd"] == 0.0003 and res["triagem"]["trace_id"] == "tr-1"
    assert res["triagem"]["contexto"] == "vault" and res["triagem"]["em"]
    tri = svc.get_demand(did).artefacts["triagem"]
    assert tri["aprovada_por"] == "" and tri["sugerida_por"] == "ia"
    assert tri["produto"] == PRODUTO
    # A sugestão da IA não ocupa o campo da escolha do gestor.
    assert tri["trilha"] == "" and tri["trilha_sugerida"] == "completa"
    assert set(TRIAGEM_TEMPLATE) <= set(tri)
    assert svc.get_demand(did).artefacts["geracao"]["triagem"]["estado"] == "gerado"


def test_gestor_aprova_trilha_diferente_da_sugerida_sem_rebaixamento(svc, docs):
    did = _demanda(svc)
    _gerador(svc, docs, ClienteFalso()).executar(did)
    tri = svc.get_demand(did).artefacts["triagem"]
    aprovada = {**tri, "trilha": "operacional", "aprovada_por": "Gestor", "aprovada_em": "2026-11-09"}
    tri = svc.update_artefact(did, "triagem", aprovada).artefacts["triagem"]
    assert tri["trilha"] == "operacional" and tri["trilha_sugerida"] == "completa"
    assert tri["rebaixamentos"] == [] and tri["aprovada_por"] == "Gestor"
    assert not any(h.get("action", "").startswith("rebaixar_trilha")
                   for h in svc.get_demand(did).agent_history)


def test_triagem_da_ia_nao_traz_aprovacao(svc, docs):
    did = _demanda(svc)
    cliente = ClienteFalso({"triagem@1": {**TRIAGEM_IA, "aprovada_por": "IA", "aprovada_em": "x"}})
    _gerador(svc, docs, cliente).executar(did)
    tri = svc.get_demand(did).artefacts["triagem"]
    assert tri["aprovada_por"] == "" and tri["aprovada_em"] == ""


def test_gera_visao_ao_entrar_em_spike(svc, docs):
    did = _demanda(svc, "spike", _triagem_aprovada())
    cliente = ClienteFalso()
    res = _gerador(svc, docs, cliente).executar(did)
    rel = f"{PRODUTO}/demandas/{did.lower()}/visao.mdx"
    assert res["visao"]["estado"] == "gerado" and res["visao"]["caminho"] == rel
    assert cliente.chamadas == ["visao@1"]
    fm = yaml.safe_load((docs / rel).read_text(encoding="utf-8").split("---\n")[1])
    assert fm["status"] == "proposta"
    assert svc.get_demand(did).artefacts["visao"] == {"pagina": rel, "aprovada_por": ""}


def test_falha_de_provedor(svc, docs):
    did = _demanda(svc, "spike", _triagem_aprovada())
    res = _gerador(svc, docs, ClienteFalso(envelope={"status": "error", "reason": "timeout"})).executar(did)
    assert res["visao"]["estado"] == "falhou" and res["visao"]["motivo"].startswith("provedor")

    def quebra(template, texto):
        raise ConnectionError("fora do ar")
    res = _gerador(svc, docs, quebra).executar(did)
    assert res["visao"]["estado"] == "falhou" and res["visao"]["motivo"].startswith("provedor")
    assert "visao" not in svc.get_demand(did).artefacts
    assert not any(docs.rglob("*.mdx"))


def test_orcamento_estourado(svc, docs):
    did = _demanda(svc, "spike", _triagem_aprovada())
    env = {"status": "budget_exceeded", "reason": "limite", "payload": None, "cost": None, "trace_id": "t"}
    res = _gerador(svc, docs, ClienteFalso(envelope=env)).executar(did)
    assert res["visao"]["estado"] == "falhou" and res["visao"]["motivo"].startswith("orçamento")
    assert not any(docs.rglob("*.mdx"))


def test_rascunho_invalido_nao_escreve(svc, docs):
    did = _demanda(svc, "spike", _triagem_aprovada())
    cliente = ClienteFalso({"visao@1": {"problema": "P"}})
    res = _gerador(svc, docs, cliente).executar(did)
    assert res["visao"]["estado"] == "falhou"
    assert res["visao"]["motivo"].startswith("rascunho inválido")
    assert "cenario_atual" in res["visao"]["motivo"]
    assert not any(docs.rglob("*.mdx"))


def test_triagem_sem_produto_valido_vira_rascunho_invalido(svc, docs):
    did = _demanda(svc, "spike", _triagem_aprovada(produto="Portal X"))
    cliente = ClienteFalso()
    res = _gerador(svc, docs, cliente).executar(did)
    assert res["triagem"]["estado"] == "falhou"
    assert res["triagem"]["motivo"].startswith("rascunho inválido")
    assert cliente.chamadas == []


def test_regra_que_nao_renderiza_vira_pagina_invalida(svc, docs):
    did = _demanda(svc, "spec", _triagem_aprovada(), visao={"pagina": "x", "aprovada_por": "G"})
    cliente = ClienteFalso({"regras@1": {"regras": [_regra(slug_="!!!")]}})
    res = _gerador(svc, docs, cliente).executar(did)
    assert res["regras"]["estado"] == "falhou" and res["regras"]["motivo"].startswith("página inválida")
    assert not list(docs.rglob("regras/*.mdx"))
    assert "regras" not in svc.get_demand(did).artefacts


def test_docs_repo_ausente(svc, docs):
    did = _demanda(svc, "spike", _triagem_aprovada())

    def sem_docs():
        raise DocsRegistryError("DOCS_REPO_PATH não configurado: aponte para o checkout")
    cliente = ClienteFalso()
    res = _gerador(svc, docs, cliente, root=sem_docs).executar(did)
    assert res["visao"]["estado"] == "falhou"
    assert res["visao"]["motivo"].startswith("docs_repo")
    assert "DOCS_REPO_PATH" in res["visao"]["motivo"]
    assert cliente.chamadas == []


def test_docs_repo_falha_na_escrita_guarda_custo(svc, docs, monkeypatch):
    import core.geracao.gerador as mod

    def falha(root, rel, conteudo):
        raise DocsRegistryError("caminho fora do repositório de documentação")
    monkeypatch.setattr(mod, "escrever", falha)
    did = _demanda(svc, "spike", _triagem_aprovada())
    res = _gerador(svc, docs, ClienteFalso()).executar(did)
    assert res["visao"]["estado"] == "falhou" and res["visao"]["motivo"].startswith("docs_repo")
    assert res["visao"]["custo_usd"] == 0.0003 and res["visao"]["trace_id"] == "tr-1"


@pytest.mark.parametrize("artefato,fase,extra", [
    ("visao", "spike", {}),
    ("regras", "spec", {"visao": {"pagina": "x", "aprovada_por": "G"}}),
])
def test_oserror_na_escrita_vira_docs_repo_com_detalhe(svc, docs, monkeypatch, artefato, fase, extra):
    import core.geracao.gerador as mod

    def falha(root, rel, conteudo):
        raise PermissionError(13, "Acesso negado", rel)
    monkeypatch.setattr(mod, "escrever", falha)
    did = _demanda(svc, fase, _triagem_aprovada(), **extra)
    res = _gerador(svc, docs, ClienteFalso()).executar(did)
    assert res[artefato]["estado"] == "falhou"
    assert res[artefato]["motivo"].startswith("docs_repo") and "Acesso negado" in res[artefato]["motivo"]
    assert res[artefato]["custo_usd"] == 0.0003
    assert svc.get_demand(did).artefacts["geracao"][artefato]["estado"] == "falhou"


def test_oserror_no_rastreio_vira_falha_registrada(svc, docs):
    did = _demanda(svc, "review", _triagem_aprovada())

    def rastreio(root, produto, testes, saida):
        raise OSError("disco cheio")
    res = _gerador(svc, docs, ClienteFalso(), rastreio=rastreio, testes={PRODUTO: "t"}).executar(did)
    assert res["rastreio"]["estado"] == "falhou" and "disco cheio" in res["rastreio"]["motivo"]
    assert svc.get_demand(did).artefacts["geracao"]["rastreio"]["estado"] == "falhou"


def test_pagina_existente_vira_pulado(svc, docs):
    did = _demanda(svc, "spike", _triagem_aprovada())
    rel = f"{PRODUTO}/demandas/{did.lower()}/visao.mdx"
    (docs / rel).parent.mkdir(parents=True)
    (docs / rel).write_text("ORIGINAL", encoding="utf-8")
    cliente = ClienteFalso()
    res = _gerador(svc, docs, cliente).executar(did)
    assert res["visao"]["estado"] == "pulado" and res["visao"]["caminho"] == rel
    assert (docs / rel).read_text(encoding="utf-8") == "ORIGINAL"
    assert cliente.chamadas == []


def test_geracao_concorrente_escreve_uma_vez(svc, docs):
    did = _demanda(svc, "spike", _triagem_aprovada())
    um_terminou = threading.Event()
    cliente = ClienteFalso(antes=lambda: um_terminou.wait(5))
    gerador = _gerador(svc, docs, cliente)
    barreira = threading.Barrier(2)
    resultados = []

    def rodar():
        barreira.wait()
        resultados.append(gerador.executar(did))
        um_terminou.set()

    threads = [threading.Thread(target=rodar) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert cliente.chamadas == ["visao@1"]
    assert sorted(len(r) for r in resultados) == [0, 1]
    assert len(list(docs.rglob("*.mdx"))) == 1


def test_demanda_sem_triagem_fora_do_intake_so_gera_triagem(svc, docs):
    did = _demanda(svc, "spec")
    cliente = ClienteFalso()
    res = _gerador(svc, docs, cliente).executar(did)
    assert list(res) == ["triagem"] and cliente.chamadas == ["triagem@1"]
    assert not any(docs.rglob("*.mdx"))
    # triagem sugerida, sem aprovação: nada mais é gerado
    assert _gerador(svc, docs, cliente).executar(did) == {}


def test_gera_regras_e_historias_ao_entrar_em_spec(svc, docs):
    did = _demanda(svc, "spec", _triagem_aprovada(), visao={"pagina": "x", "aprovada_por": "G"})
    res = _gerador(svc, docs, ClienteFalso()).executar(did)
    assert res["historias"]["estado"] == "gerado" and res["regras"]["estado"] == "gerado"
    arts = svc.get_demand(did).artefacts
    assert arts["regras"] == [f"{PRODUTO}/regras/agrupamento.mdx"]
    assert arts["historias"] == f"{PRODUTO}/demandas/{did.lower()}/historias.mdx"
    fm = yaml.safe_load((docs / arts["regras"][0]).read_text(encoding="utf-8").split("---\n")[1])
    assert fm["status"] == "proposta" and fm["avais"] == []


def test_plano_de_testes_tem_ids_das_regras_aprovadas(svc, docs):
    aprovada = _escrever_regra(docs)
    _aprovar(docs, aprovada)
    proposta = _escrever_regra(docs, _regra(slug_="outra"))
    did = _demanda(svc, "dev", _triagem_aprovada(), regras=[aprovada, proposta])
    res = _gerador(svc, docs, ClienteFalso()).executar(did)
    assert res["plano_de_testes"]["estado"] == "gerado"
    plano = svc.get_demand(did).artefacts["plano_de_testes"]
    assert [c["id"] for c in plano] == [f"{PRODUTO}.agrupamento#1", f"{PRODUTO}.agrupamento#2"]
    assert plano[0]["dado"] == "d0" and plano[0]["quando"] == "q0" and plano[0]["entao"] == "e0"


def test_rastreio_sem_testes_configurados_falha(svc, docs):
    did = _demanda(svc, "review", _triagem_aprovada())
    chamadas = []
    res = _gerador(svc, docs, ClienteFalso(), rastreio=lambda *a: chamadas.append(a) or 0).executar(did)
    assert res["rastreio"]["estado"] == "falhou" and res["rastreio"]["motivo"].startswith("rastreio")
    assert chamadas == []
    assert "rastreio" not in svc.get_demand(did).artefacts


def test_rastreio_grava_caminho_e_codigo_estranho_falha(svc, docs, tmp_path):
    did = _demanda(svc, "review", _triagem_aprovada())
    chamadas = []

    def rastreio(root, produto, testes, saida):
        chamadas.append((root, produto, testes, saida))
        saida.write_text("{}", encoding="utf-8")
        return 1
    res = _gerador(svc, docs, ClienteFalso(), rastreio=rastreio, testes={PRODUTO: "t/**/*.ts"}).executar(did)
    saida = tmp_path / ".rastreio" / f"{did}.json"
    assert chamadas == [(docs, PRODUTO, "t/**/*.ts", saida)]
    assert res["rastreio"]["estado"] == "gerado"
    assert svc.get_demand(did).artefacts["rastreio"] == str(saida)

    did2 = _demanda(svc, "review", _triagem_aprovada())
    res = _gerador(svc, docs, ClienteFalso(), rastreio=lambda *a: 2, testes={PRODUTO: "t"}).executar(did2)
    assert res["rastreio"]["estado"] == "falhou" and res["rastreio"]["motivo"].startswith("rastreio")
    assert "rastreio" not in svc.get_demand(did2).artefacts


def test_refazer_nao_toca_regra_aprovada(svc, docs):
    aprovada = _escrever_regra(docs)
    _aprovar(docs, aprovada)
    original = (docs / aprovada).read_text(encoding="utf-8")
    proposta = _escrever_regra(docs, _regra(slug_="outra"))
    (docs / proposta).write_text((docs / proposta).read_text(encoding="utf-8") + "\nANTIGA\n", encoding="utf-8")
    did = _demanda(svc, "spec", _triagem_aprovada(), visao={"pagina": "x", "aprovada_por": "G"},
                   regras=[aprovada, proposta])
    cliente = ClienteFalso({"regras@1": {"regras": [_regra(), _regra(slug_="outra")]}})
    res = _gerador(svc, docs, cliente).executar(did, refazer=True)
    assert (docs / aprovada).read_text(encoding="utf-8") == original
    assert "ANTIGA" not in (docs / proposta).read_text(encoding="utf-8")
    assert res["regras"]["estado"] == "gerado"
    assert svc.get_demand(did).artefacts["regras"] == [aprovada, proposta]


def test_sem_refazer_nao_regera_o_que_ja_esta_no_card(svc, docs):
    did = _demanda(svc, "spike", _triagem_aprovada())
    cliente = ClienteFalso()
    _gerador(svc, docs, cliente).executar(did)
    assert _gerador(svc, docs, cliente).executar(did) == {}
    assert cliente.chamadas == ["visao@1"]


def test_exemplos_da_regra(docs):
    rel = _escrever_regra(docs, {**_regra(), "exemplos": [
        {"dado": "a | b", "quando": "q", "entao": "e"}, {"dado": "x", "quando": "y", "entao": "z"}]})
    assert exemplos_da_regra(docs, rel) == [
        {"id": f"{PRODUTO}.agrupamento#1", "dado": "a | b", "quando": "q", "entao": "e"},
        {"id": f"{PRODUTO}.agrupamento#2", "dado": "x", "quando": "y", "entao": "z"},
    ]


def test_regra_existente_de_outra_demanda_nao_entra_no_card(svc, docs):
    alheia = _escrever_regra(docs)
    _aprovar(docs, alheia)
    original = (docs / alheia).read_text(encoding="utf-8")
    did = _demanda(svc, "spec", _triagem_aprovada(), visao={"pagina": "x", "aprovada_por": "G"})
    cliente = ClienteFalso({"regras@1": {"regras": [_regra(), _regra(slug_="nova")]}})
    res = _gerador(svc, docs, cliente).executar(did)
    nova = f"{PRODUTO}/regras/nova.mdx"
    assert svc.get_demand(did).artefacts["regras"] == [nova]
    assert res["regras"]["estado"] == "gerado"
    assert f"regra já existe: {alheia}" in res["regras"]["motivo"]
    assert (docs / alheia).read_text(encoding="utf-8") == original

    did2 = _demanda(svc, "spec", _triagem_aprovada(), visao={"pagina": "x", "aprovada_por": "G"})
    res = _gerador(svc, docs, ClienteFalso()).executar(did2)
    assert "regras" not in svc.get_demand(did2).artefacts
    assert res["regras"]["estado"] == "pulado" and alheia in res["regras"]["motivo"]


def test_refazer_nao_toca_regra_de_outra_demanda(svc, docs):
    alheia = _escrever_regra(docs)
    (docs / alheia).write_text((docs / alheia).read_text(encoding="utf-8") + "\nANTIGA\n", encoding="utf-8")
    original = (docs / alheia).read_text(encoding="utf-8")
    did = _demanda(svc, "spec", _triagem_aprovada(), visao={"pagina": "x", "aprovada_por": "G"})
    res = _gerador(svc, docs, ClienteFalso()).executar(did, refazer=True)
    assert (docs / alheia).read_text(encoding="utf-8") == original
    assert "regras" not in svc.get_demand(did).artefacts
    assert f"regra já existe: {alheia}" in res["regras"]["motivo"]


def test_refazer_nao_troca_visao_aprovada(svc, docs):
    did = _demanda(svc, "spike", _triagem_aprovada())
    rel = f"{PRODUTO}/demandas/{did.lower()}/visao.mdx"
    _gerador(svc, docs, ClienteFalso()).executar(did)
    svc.update_artefact(did, "visao", {"pagina": rel, "aprovada_por": "Gestor"})
    original = (docs / rel).read_text(encoding="utf-8")
    cliente = ClienteFalso()
    res = _gerador(svc, docs, cliente).executar(did, refazer=True)
    assert res["visao"]["estado"] == "pulado" and res["visao"]["motivo"] == "visão já aprovada"
    assert cliente.chamadas == []
    assert (docs / rel).read_text(encoding="utf-8") == original


def test_refazer_regera_visao_sem_aprovacao(svc, docs):
    did = _demanda(svc, "spike", _triagem_aprovada())
    rel = f"{PRODUTO}/demandas/{did.lower()}/visao.mdx"
    _gerador(svc, docs, ClienteFalso()).executar(did)
    (docs / rel).write_text((docs / rel).read_text(encoding="utf-8") + "\nANTIGA\n", encoding="utf-8")
    res = _gerador(svc, docs, ClienteFalso()).executar(did, refazer=True)
    assert res["visao"]["estado"] == "gerado"
    assert "ANTIGA" not in (docs / rel).read_text(encoding="utf-8")


def test_regras_com_produto_invalido_nao_chama_ia(svc, docs):
    did = _demanda(svc, "spec", _triagem_aprovada(produto="../x"),
                   visao={"pagina": "x", "aprovada_por": "G"}, historias="x")
    cliente = ClienteFalso()
    res = _gerador(svc, docs, cliente).executar(did)
    assert res["regras"]["estado"] == "falhou"
    assert res["regras"]["motivo"].startswith("rascunho inválido")
    assert cliente.chamadas == []
    assert not list(docs.rglob("*.mdx"))


def _rastreio_que_grava(codigo=0, conteudo='{"versao": 1}'):
    def rastreio(root, produto, testes, saida):
        saida.write_text(conteudo, encoding="utf-8")
        return codigo
    return rastreio


def test_rastreio_sem_arquivo_falha_e_nao_toca_o_card(svc, docs):
    did = _demanda(svc, "review", _triagem_aprovada())
    res = _gerador(svc, docs, ClienteFalso(), rastreio=lambda *a: 0, testes={PRODUTO: "t"}).executar(did)
    assert res["rastreio"]["estado"] == "falhou" and "arquivo" in res["rastreio"]["motivo"]
    assert res["rastreio"]["motivo"].startswith("rastreio")
    assert "rastreio" not in svc.get_demand(did).artefacts


def test_rastreio_ja_no_card_e_recalculado_sem_refazer(svc, docs, tmp_path):
    did = _demanda(svc, "review", _triagem_aprovada(), rastreio="/antigo.json")
    res = _gerador(svc, docs, ClienteFalso(), rastreio=_rastreio_que_grava(1),
                   testes={PRODUTO: "t"}).executar(did)
    saida = tmp_path / ".rastreio" / f"{did}.json"
    assert res["rastreio"]["estado"] == "gerado"
    assert svc.get_demand(did).artefacts["rastreio"] == str(saida)


@pytest.mark.parametrize("rastreio", [lambda *a: 2, lambda *a: 0], ids=["codigo-2", "sem-arquivo"])
def test_refazer_rastreio_que_falha_nao_toca_o_card_e_tira_o_arquivo_velho(svc, docs, tmp_path, rastreio):
    did = _demanda(svc, "review", _triagem_aprovada())
    _gerador(svc, docs, ClienteFalso(), rastreio=_rastreio_que_grava(0), testes={PRODUTO: "t"}).executar(did)
    saida = tmp_path / ".rastreio" / f"{did}.json"
    assert svc.get_demand(did).artefacts["rastreio"] == str(saida) and saida.is_file()
    res = _gerador(svc, docs, ClienteFalso(), rastreio=rastreio, testes={PRODUTO: "t"}).executar(did, refazer=True)
    assert res["rastreio"]["estado"] == "falhou"
    assert svc.get_demand(did).artefacts["rastreio"] == str(saida)
    # The old result must not stand in for the rerun that failed.
    assert not saida.exists()


# -- refazer o rascunho da triagem ainda não aprovado ----------------------------

def test_refazer_regera_triagem_sugerida_e_nao_aprovada(svc, docs):
    did = _demanda(svc)
    _gerador(svc, docs, ClienteFalso()).executar(did)
    nova = ClienteFalso({"triagem@1": {**TRIAGEM_IA, "t3": True, "justificativa": "segunda versão"}})
    res = _gerador(svc, docs, nova).executar(did, refazer=True)
    assert res["triagem"]["estado"] == "gerado" and nova.chamadas == ["triagem@1"]
    tri = svc.get_demand(did).artefacts["triagem"]
    assert tri["t3"] is True and tri["justificativa"] == "segunda versão" and tri["sugerida_por"] == "ia"


def test_refazer_nao_toca_triagem_aprovada_nem_a_feita_por_pessoa(svc, docs):
    aprovada = _demanda(svc, triagem=_triagem_aprovada(sugerida_por="ia"))
    da_pessoa = _demanda(svc, triagem={**TRIAGEM_TEMPLATE, **TRIAGEM_IA})
    cliente = ClienteFalso()
    for did in (aprovada, da_pessoa):
        antes = svc.get_demand(did).artefacts["triagem"]
        _gerador(svc, docs, cliente).executar(did, refazer=True)
        assert svc.get_demand(did).artefacts["triagem"] == antes
    assert "triagem@1" not in cliente.chamadas


def test_sem_refazer_triagem_sugerida_fica(svc, docs):
    did = _demanda(svc)
    _gerador(svc, docs, ClienteFalso()).executar(did)
    cliente = ClienteFalso()
    assert _gerador(svc, docs, cliente).executar(did) == {} and cliente.chamadas == []


def test_guia_da_triagem_vai_ao_texto_do_rascunho(svc, docs):
    did = _demanda(svc)
    textos = []

    def cliente(template, texto):
        textos.append(texto)
        return {"status": "ok", "reason": "", "payload": TRIAGEM_IA, "cost": {"actual_usd": 0.0}, "trace_id": "t"}

    g = GeradorDeArtefatos(svc, cliente, lambda q: [], lambda: docs, lambda *a: 0, {}, svc._db_path.parent,
                           guia_triagem="T3: roda sem pessoa?")
    g.executar(did)
    assert "# Como triar\nT3: roda sem pessoa?" in textos[0]
