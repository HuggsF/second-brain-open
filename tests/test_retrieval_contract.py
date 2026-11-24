import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from config import settings
from core.chunker import MarkdownChunker
from core.citations import GAP_EMPTY_INDEX, GAP_NO_EVIDENCE, GAP_STALE
from core.cost import CostRecord
from core.indice_texto import IndiceTexto
from core.local_tasks.answer import AnswerResult

NO_DOC_TEXT = "Nenhum documento relevante encontrado na sua base de conhecimento para essa pergunta."
REBUILD_HINT = "Rode 'cli.py sync --rebuild' para reconstruir o índice deste espaço."

NOTAS = {
    "systems/alfa.md": ("# Alfa\n\n## Pedidos\n\nO fluxo de pedidos usa a fila de despacho.\n\n"
                        "## Despacho\n\nO despacho de pedidos roda toda noite.\n"),
    "systems/beta.md": "# Beta\n\n## Webhook\n\nPedidos chegam por webhook e entram na fila.\n",
    "domain/gama.md": "# Gama\n\n## Cartao\n\nA fatura do cartao fecha no dia dez.\n",
    "domain/delta.md": ("# Delta\n\n## Notas\n\nTexto solto sobre pedidos e outros assuntos diversos "
                        "sem relacao com nada importante aqui.\n"),
}
# Scores reais do BM25 nesta fixture (indice com as quatro notas, um trecho por nota):
#   "pedidos webhook fila": beta 3.78, alfa 1.26, delta 0.15
#   "fluxo de pedidos":     alfa 1.83, beta 0.18, delta 0.15
CONSULTA = "pedidos webhook fila"
CONSULTA_FRACA = "fluxo de pedidos"


def indexar_vault(vault: Path, arquivo_db: Path, notas: dict) -> IndiceTexto:
    """Grava `notas` no vault e as indexa com o chunker real.

    O valor de cada nota e o texto (espaco do `settings`) ou um par `(texto, space_id)`.
    """
    itens = []
    for rel, valor in notas.items():
        texto, space_id = valor if isinstance(valor, tuple) else (valor, settings.space_id)
        caminho = vault / rel
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")
        raw = caminho.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        trechos = MarkdownChunker().chunk_bytes(raw, rel, vault)
        for trecho in trechos:
            trecho["metadata"]["doc_sha256"] = sha
            trecho["metadata"]["space_id"] = space_id
        itens.append((rel, sha, trechos))
    indice = IndiceTexto(arquivo_db)
    indice.reconstruir(itens)
    return indice


def custo(modelo="m1", provedor="nuvem-a", usd=0.0012):
    return CostRecord(model=modelo, tier="cloud" if provedor else "local", tokens_in=100, tokens_out=20, ms=5,
                      paid_equivalent_usd=0.002, provider=provedor, actual_usd=usd)


class FakeGenerator:
    """Gerador de resposta falso: guarda (sistema, usuario) e devolve `resultado`, ou levanta `erro`."""

    def __init__(self):
        self.calls = []
        self.resultado = AnswerResult("ok", "resposta do modelo", None, "nuvem-a", custo())
        self.erro = None

    def __call__(self, sistema, usuario):
        self.calls.append((sistema, usuario))
        if self.erro is not None:
            raise self.erro
        return self.resultado

    def falha(self, motivo):
        self.resultado = AnswerResult("model_error", None, motivo, None, custo("m1", None, 0.0))


class TestRetriever(unittest.TestCase):
    """BrainRetriever.query()/answer() sobre o indice de texto: escopo, piso, diversidade e citacoes."""

    def setUp(self):
        from core.retriever import BrainRetriever
        self.BrainRetriever = BrainRetriever
        self.config({"space_id": "principal", "retrieval_min_score": 0.5, "retrieval_max_drop": 0.8,
                     "retrieval_max_per_doc": 1})
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.vault = self.tmp / "vault"
        self.generator = FakeGenerator()
        self.store = indexar_vault(self.vault, self.tmp / "i.db", NOTAS)
        self.retriever = BrainRetriever(store=self.store, vault_dir=self.vault, generator=self.generator)

    def config(self, valores):
        for nome, valor in valores.items():
            patcher = mock.patch.object(settings, nome, valor)
            patcher.start()
            self.addCleanup(patcher.stop)

    def vazio(self):
        return self.BrainRetriever(store=IndiceTexto(self.tmp / "vazio.db"), vault_dir=self.vault,
                                   generator=self.generator)

    def test_query_devolve_fontes_com_citacao_verificavel(self):
        r = self.retriever.query(CONSULTA)
        self.assertTrue({"question", "context", "sources", "citations", "gaps", "index_version"} <= set(r))
        self.assertEqual([s["file_path"] for s in r["sources"]], ["systems/beta.md", "systems/alfa.md"])
        sha_beta = hashlib.sha256((self.vault / "systems/beta.md").read_bytes()).hexdigest()
        fonte = r["sources"][0]
        self.assertTrue({"file_path", "doc_title", "section", "category", "score", "sha256", "line_start",
                         "line_end", "stale"} <= set(fonte))
        self.assertEqual((fonte["sha256"], fonte["stale"]), (sha_beta, False))
        self.assertEqual((fonte["doc_title"], fonte["section"], fonte["category"]), ("Beta", "Webhook", "systems"))
        self.assertIsInstance(fonte["line_start"], int)
        self.assertGreaterEqual(fonte["line_end"], fonte["line_start"])
        self.assertNotIn("content", fonte)
        self.assertEqual(r["gaps"], [])
        for fonte, citacao in zip(r["sources"], r["citations"], strict=True):
            for chave in ("sha256", "line_start", "line_end", "stale"):
                self.assertEqual(fonte[chave], citacao[chave])
        self.assertEqual(set(r["citations"][0]),
                         {"document", "section", "line_start", "line_end", "sha256", "score", "stale"})

    def test_include_content_acrescenta_o_texto_do_trecho(self):
        fonte = self.retriever.query(CONSULTA, include_content=True)["sources"][0]
        self.assertIn("webhook", fonte["content"])

    def test_citacao_fica_stale_quando_a_nota_muda(self):
        (self.vault / "systems/beta.md").write_text("mudou", encoding="utf-8")
        r = self.retriever.query(CONSULTA)
        self.assertTrue(r["citations"][0]["stale"])
        self.assertTrue(r["sources"][0]["stale"])
        self.assertFalse(r["sources"][1]["stale"])
        self.assertIn(GAP_STALE, r["gaps"])

    def test_sem_evidencia_abaixo_do_piso(self):
        self.config({"retrieval_min_score": 2.0})  # topo de CONSULTA_FRACA e 1.83
        r = self.retriever.query(CONSULTA_FRACA)
        self.assertEqual((r["sources"], r["citations"], r["context"]), ([], [], ""))
        self.assertEqual(r["gaps"], [GAP_NO_EVIDENCE])

    def test_piso_absoluto_nao_barra_quando_o_topo_o_alcanca(self):
        self.config({"retrieval_min_score": 1.5})
        self.assertEqual([s["file_path"] for s in self.retriever.query(CONSULTA_FRACA)["sources"]],
                         ["systems/alfa.md"])

    def test_queda_relativa_ao_topo_deixa_resultado_de_fora(self):
        # topo 3.78: com max_drop 0.5 o piso vira 1.89 e alfa (1.26) sai; com 0.8 vira 0.76 e alfa volta.
        self.config({"retrieval_max_drop": 0.5})
        self.assertEqual([s["file_path"] for s in self.retriever.query(CONSULTA)["sources"]], ["systems/beta.md"])
        self.config({"retrieval_max_drop": 0.8})
        self.assertEqual([s["file_path"] for s in self.retriever.query(CONSULTA)["sources"]],
                         ["systems/beta.md", "systems/alfa.md"])

    def test_indice_vazio_avisa(self):
        r = self.vazio().query(CONSULTA)
        self.assertEqual((r["citations"], r["gaps"]), ([], [GAP_EMPTY_INDEX]))

    def test_filtro_sem_resultado_nao_e_indice_vazio(self):
        for filtro in ({"category": "inexistente"}, {"bounded_context": "Inexistente"}):
            r = self.retriever.query(CONSULTA, **filtro)
            self.assertEqual(r["citations"], [])
            self.assertEqual(r["gaps"], [GAP_NO_EVIDENCE])

    def test_filtro_de_categoria_restringe_o_resultado(self):
        self.config({"retrieval_max_drop": 1.0, "retrieval_min_score": 0.1})
        fontes = self.retriever.query(CONSULTA, category="domain")["sources"]
        self.assertEqual([s["file_path"] for s in fontes], ["domain/delta.md"])

    def test_termo_desconhecido_zera_a_selecao(self):
        r = self.retriever.query("Como a Acme recebe pedidos webhook?")
        self.assertEqual((r["citations"], r["sources"], r["context"]), ([], [], ""))
        self.assertEqual(r["gaps"], ["Termo(s) sem registro no vault: Acme; não há evidência para esta consulta."])

    def test_termo_conhecido_no_vault_mantem_os_resultados(self):
        (self.vault / "domain/gama.md").write_text("Integração com a Acme.", encoding="utf-8")
        r = self.retriever.query("Como a Acme recebe pedidos webhook?")
        self.assertEqual(r["sources"][0]["file_path"], "systems/beta.md")

    def test_entity_gate_false_mantem_os_resultados(self):
        r = self.retriever.query("Como a Acme recebe pedidos webhook?", entity_gate=False)
        self.assertTrue(r["sources"])

    def test_apply_floor_false_devolve_candidatos_brutos(self):
        self.config({"retrieval_min_score": 2.0})
        r = self.retriever.query(CONSULTA_FRACA, apply_floor=False)
        self.assertEqual([s["file_path"] for s in r["sources"]],
                         ["systems/alfa.md", "systems/beta.md", "domain/delta.md"])
        self.assertEqual(len(r["citations"]), 3)
        r = self.retriever.query("Como a Acme recebe pedidos?", apply_floor=False)  # sem piso e sem gate
        self.assertTrue(r["sources"])

    def test_limit_corta_os_candidatos_brutos(self):
        r = self.retriever.query(CONSULTA_FRACA, limit=2, apply_floor=False)
        self.assertEqual(len(r["sources"]), 2)

    def test_um_trecho_por_nota(self):
        # alfa tem dois trechos com "pedidos" (Pedidos e Despacho): so um entra.
        fontes = self.retriever.query("pedidos despacho", apply_floor=False, limit=10)["sources"]
        caminhos = [s["file_path"] for s in fontes]
        self.assertEqual(caminhos.count("systems/alfa.md"), 1)
        self.assertEqual(len(caminhos), len(set(caminhos)))

    def test_escopo_por_espaco(self):
        notas = {**NOTAS, "systems/alien.md": ("# Alien\n\n## X\n\nPedidos webhook fila fila fila fila.\n", "outro")}
        store = indexar_vault(self.vault, self.tmp / "o.db", notas)
        retriever = self.BrainRetriever(store=store, vault_dir=self.vault, generator=self.generator)
        # o trecho do outro espaco existe no indice e seria o melhor, mas nao aparece
        self.assertEqual(store.buscar(CONSULTA, limit=4)[0]["payload"]["file_path"], "systems/alien.md")
        r = retriever.query(CONSULTA, apply_floor=False)
        self.assertNotIn("systems/alien.md", [s["file_path"] for s in r["sources"]])
        self.assertEqual(r["sources"][0]["file_path"], "systems/beta.md")

    def test_busca_usa_espaco_e_o_triplo_do_limite(self):
        with mock.patch.object(self.store, "buscar", wraps=self.store.buscar) as buscar:
            self.retriever.query(CONSULTA, limit=2, category="systems")
        buscar.assert_called_once()
        self.assertEqual(buscar.call_args.args, (CONSULTA,))
        kwargs = buscar.call_args.kwargs
        self.assertEqual(
            (kwargs["limit"], kwargs["category"], kwargs["space_id"], kwargs["per_doc"], kwargs["bounded_context"]),
            (6, "systems", settings.space_id, settings.retrieval_max_per_doc, None))

    def test_vault_vazio_desliga_o_portao_de_termo_desconhecido(self):
        for nota in NOTAS:
            (self.vault / nota).unlink()
        r = self.retriever.query("Como a Acme recebe pedidos webhook?")
        self.assertTrue(r["sources"])
        self.assertNotIn("Acme", " ".join(r["gaps"]))

    def test_index_version_e_a_versao_do_indice(self):
        r = self.retriever.query(CONSULTA)
        self.assertEqual(r["index_version"], self.store.versao())
        self.assertNotEqual(r["index_version"], "vazio")

    def test_answer_ok_usa_o_gerador_injetado(self):
        r = self.retriever.answer(CONSULTA)
        self.assertEqual((r["status"], r["answer"]), ("ok", "resposta do modelo"))
        self.assertEqual([s["file_path"] for s in r["sources"]], ["systems/beta.md", "systems/alfa.md"])
        self.assertEqual(set(r), {"answer", "sources", "citations", "gaps", "status", "provider", "model",
                                  "cost_usd", "motivo"})
        self.assertEqual((r["provider"], r["model"], r["cost_usd"], r["motivo"]), ("nuvem-a", "m1", 0.0012, None))
        (sistema, usuario), = self.generator.calls
        self.assertIn(CONSULTA, usuario)
        self.assertIn("Pedidos chegam por webhook", usuario)
        self.assertTrue(sistema.strip())

    def test_answer_sem_fontes_nao_chama_o_gerador(self):
        r = self.retriever.answer("zzqx wwyk")
        self.assertEqual(r["status"], "sem_fontes")
        self.assertEqual(r["sources"], [])
        self.assertEqual(r["answer"], NO_DOC_TEXT)
        self.assertEqual(self.generator.calls, [])
        self.assertEqual((r["provider"], r["model"], r["cost_usd"], r["motivo"]), (None, None, 0.0, None))

    def test_answer_com_indice_vazio_e_sem_fontes(self):
        r = self.vazio().answer(CONSULTA)
        self.assertEqual(r["status"], "sem_fontes")
        self.assertIn(GAP_EMPTY_INDEX, r["gaps"])
        self.assertEqual(self.generator.calls, [])

    def test_answer_do_servidor_local_sem_cadeia_tem_provider_none(self):
        self.generator.resultado = AnswerResult("ok", "resposta local", None, None, custo("m-local", None, 0.0))
        r = self.retriever.answer(CONSULTA)
        self.assertEqual((r["status"], r["provider"], r["model"], r["cost_usd"]), ("ok", None, "m-local", 0.0))

    def test_answer_sem_gerador_traz_o_motivo_e_as_fontes(self):
        for motivo in ("budget_daily", "budget_monthly", "timeout", "empty_answer", "profile_not_found"):
            with self.subTest(motivo=motivo):
                self.generator.falha(motivo)
                r = self.retriever.answer(CONSULTA)
                self.assertEqual((r["status"], r["motivo"], r["provider"]), ("sem_gerador", motivo, None))
                self.assertTrue(r["sources"])
                self.assertTrue(r["answer"].strip())
                self.assertNotIn("Pedidos chegam por webhook", r["answer"])  # não cola trecho do contexto
                for proibido in ("Traceback", "ConnectError", "httpx", "None"):
                    self.assertNotIn(proibido, r["answer"])

    def test_texto_de_sistema_e_generico_e_pede_json(self):
        self.retriever.answer(CONSULTA)
        (sistema, _), = self.generator.calls
        self.assertIn('{"answer"', sistema)
        self.assertIn("contexto", sistema)
        self.assertIn("português", sistema)

    def test_perfil_inexistente_vira_sem_gerador_e_a_busca_segue(self):
        import os
        retriever = self.BrainRetriever(store=self.store, vault_dir=self.vault)  # gerador padrão
        with mock.patch.dict(os.environ, {"BRAIN_PROFILE": "perfil-que-nao-existe"}):
            self.assertTrue(retriever.query(CONSULTA)["sources"])
            r = retriever.answer(CONSULTA)
        self.assertEqual((r["status"], r["motivo"]), ("sem_gerador", "profile_not_found"))
        self.assertTrue(r["sources"])

    def test_nao_existe_mais_gerador_local(self):
        from core import retriever
        self.assertFalse(hasattr(retriever, "gerador_local"))
        self.assertFalse(hasattr(retriever, "GeradorIndisponivel"))
        self.assertFalse(hasattr(retriever, "httpx"))

    def test_answer_nao_engole_erro_que_nao_e_do_gerador(self):
        self.generator.erro = KeyError("defeito de programa")
        with self.assertRaises(KeyError):
            self.retriever.answer(CONSULTA)

    def test_pergunta_com_sintaxe_do_fts_nao_levanta(self):
        for pergunta in ('"', "*", "(", ")", "AND OR NOT", "NEAR(a b)", "a:b", "", "   ", '"aberta', "col:*", "-", "^"):
            with self.subTest(pergunta=pergunta):
                r = self.retriever.query(pergunta)
                self.assertEqual(r["sources"], [])
                self.assertEqual(self.retriever.answer(pergunta)["status"], "sem_fontes")

    def test_construtor_nao_aceita_embedder(self):
        with self.assertRaises(TypeError):
            self.BrainRetriever(embedder=object())

    def test_construtor_padrao_usa_o_indice_de_texto(self):
        with mock.patch("core.retriever.IndiceTexto") as indice:
            r = self.BrainRetriever()
        self.assertIs(r.store, indice.return_value)
        self.assertEqual(r.vault_dir, settings.vault_dir)
        self.assertTrue(callable(r.generator))
        self.assertFalse(hasattr(r, "embedder"))
