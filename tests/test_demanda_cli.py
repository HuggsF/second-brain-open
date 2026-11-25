"""Grupo `demanda` e `gerar-artefatos` do cli, com banco, fichas e catálogo em pasta temporária e IA falsa."""
import json
import re
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

import yaml
from click.testing import CliRunner

import cli
from config import settings
from core import ficha
from core.geracao import ligacao

RAIZ = Path(__file__).resolve().parent.parent
PAYLOADS = {
    "triagem@1": {
        "produto": "portal", "t1": False, "t2": True, "t3": False, "t4": False,
        "trilha": "completa", "atividade": "Evolução de sistema", "faixa": "C",
        "criterios_de_aceite": ["o cliente vê a reserva na tela"], "mais_de_uma_sprint": False,
        "justificativa": "tela nova",
    },
    "visao@1": {
        "problema": "O cliente não vê a reserva", "cenario_atual": "Consulta por telefone",
        "cenario_desejado": "Consulta no portal", "escopo_dentro": ["tela de reservas"],
        "escopo_fora": ["pagamento"], "setores": [{"area": "Atendimento", "papel": "aprova"}],
        "riscos": [{"risco": "dado desatualizado", "mitigacao": "mostrar a hora da leitura"}],
    },
}


class Ambiente(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.fichas = self.base / "fichas"
        shutil.copytree(RAIZ / "fichas" / "_modelos", self.fichas / "_modelos")
        ficha.criar(self.fichas, "portal", "Portal", "pequeno", date(2026, 11, 24))
        self.produtos = self.base / "perfil" / "produtos.yaml"
        self.catalogo({"portal": {"descricao": "Portal do cliente", "pistas": ["reserva"]}})
        self.respostas = dict(PAYLOADS)
        self.status_ia = "ok"
        self.chamadas = []
        for alvo, nome, valor in (
            (settings, "base_dir", self.base),
            (settings, "fichas_dir", self.fichas),
            (ligacao, "caminho_produtos", lambda perfil=None: self.produtos),
            (ligacao, "_cliente_ia", self.ia),
            (ligacao, "_busca", lambda pergunta: []),
        ):
            troca = mock.patch.object(alvo, nome, valor)
            troca.start()
            self.addCleanup(troca.stop)
        troca = mock.patch.dict("os.environ", {}, clear=False)
        troca.start()
        self.addCleanup(troca.stop)
        import os
        os.environ.pop("DOCS_REPO_PATH", None)

    def catalogo(self, produtos):
        self.produtos.parent.mkdir(parents=True, exist_ok=True)
        self.produtos.write_text(yaml.safe_dump(produtos, allow_unicode=True), encoding="utf-8")

    def ia(self, template, texto, *args, **kwargs):
        self.chamadas.append(template)
        if self.status_ia != "ok":
            return {"status": self.status_ia, "reason": "budget_daily", "payload": None,
                    "cost": {"actual_usd": 0.0}, "trace_id": "tr"}
        return {"status": "ok", "reason": "", "payload": self.respostas[template],
                "cost": {"actual_usd": 0.0, "provider": "falso"}, "trace_id": f"tr-{template}"}

    def rodar(self, *args):
        r = CliRunner().invoke(cli.cli, list(args))
        self.assertTrue(r.exception is None or isinstance(r.exception, SystemExit), repr(r.exception))
        r.texto = " ".join(re.sub(r"\x1b\[[0-9;]*m", "", r.output).split())
        self.assertNotIn("Traceback", r.output)
        return r

    def nova(self, titulo="Tela de reservas"):
        r = self.rodar("demanda", "nova", titulo, "--descricao", "O cliente quer ver a reserva no portal.")
        self.assertEqual(r.exit_code, 0, r.output)
        return re.search(r"DEM-\d+", r.output).group(0)

    def triagem_em_arquivo(self, **campos):
        arq = self.base / "triagem.json"
        arq.write_text(json.dumps({**PAYLOADS["triagem@1"], "trilha": "", **campos}, ensure_ascii=False), encoding="utf-8")
        return str(arq)

    def em_spike(self):
        did = self.nova()
        self.assertEqual(self.rodar("gerar-artefatos", did).exit_code, 0)
        r = self.rodar("demanda", "triar", did, "--aprovar-por", "gestor-demandas", "--trilha", "completa")
        self.assertEqual(r.exit_code, 0, r.output)
        r = self.rodar("demanda", "avancar", did, "--ator", "gestor-demandas")
        self.assertEqual(r.exit_code, 0, r.output)
        return did

    def visao(self, did):
        return self.fichas / "portal" / "demandas" / did.lower() / "visao.mdx"


class TestBasico(Ambiente):
    def test_nova_listar_mostrar(self):
        self.assertIn("Nenhuma demanda.", self.rodar("demanda", "listar").texto)
        did = self.nova()
        r = self.rodar("demanda", "listar")
        self.assertRegex(r.texto, rf"{did} intake - - Tela de reservas")
        r = self.rodar("demanda", "mostrar", did)
        self.assertEqual(r.exit_code, 0, r.output)
        for trecho in ("Fase: intake", "Triagem: ausente", "Falta para sair de intake:", "triagem aprovada"):
            self.assertIn(trecho, r.texto)
        self.assertIn("Nenhuma demanda.", self.rodar("demanda", "listar", "--fase", "dev").texto)
        self.assertTrue((self.base / ".runtime" / "demands.db").is_file())

    def test_id_em_minusculas_e_com_espacos_e_aceito(self):
        did = self.nova()
        for forma in (did.lower(), f"  {did.lower()} "):
            with self.subTest(forma=forma):
                r = self.rodar("demanda", "mostrar", forma)
                self.assertEqual(r.exit_code, 0, r.output)
                self.assertIn("Fase: intake", r.texto)

    def test_demanda_inexistente_sai_1_em_todos_os_comandos(self):
        arq = self.triagem_em_arquivo()
        for args in (("demanda", "mostrar", "DEM-999"), ("demanda", "triar", "DEM-999", "--arquivo", arq),
                     ("demanda", "triar", "DEM-999", "--aprovar-por", "gestor-demandas", "--trilha", "leve"),
                     ("demanda", "trilha", "DEM-999", "leve", "--motivo", "m", "--ator", "gestor-demandas"),
                     ("demanda", "aprovar-visao", "DEM-999", "--por", "gestor-demandas"),
                     ("demanda", "artefato", "DEM-999", "evidence", "--valor", '"ok"'),
                     ("demanda", "avancar", "DEM-999", "--ator", "gestor-demandas"),
                     ("gerar-artefatos", "DEM-999")):
            with self.subTest(args=args):
                r = self.rodar(*args)
                self.assertEqual(r.exit_code, 1, r.output)
                self.assertIn("Demanda DEM-999 não encontrada.", r.texto)

    def test_banco_de_demandas_corrompido_avisa_e_sai_1(self):
        (self.base / ".runtime").mkdir()
        (self.base / ".runtime" / "demands.db").write_bytes(b"isto nao e um banco sqlite " * 40)
        for args in (("demanda", "listar"), ("demanda", "nova", "x"), ("gerar-artefatos", "DEM-001")):
            with self.subTest(args=args):
                r = self.rodar(*args)
                self.assertEqual(r.exit_code, 1, r.output)
                self.assertIn("Não foi possível ler o banco de demandas", r.texto)

    def test_buscar_sync_e_budget_nao_dependem_do_banco_de_demandas(self):
        (self.base / ".runtime").mkdir()
        (self.base / ".runtime" / "demands.db").write_bytes(b"lixo" * 100)
        vault = self.base / "vault" / "systems"
        vault.mkdir(parents=True)
        (vault / "portal.md").write_text("# Portal\n\n## Reserva\n\nA reserva expira em quinze minutos.\n", encoding="utf-8")
        with mock.patch.object(settings, "vault_dir", self.base / "vault"), \
                mock.patch.object(settings, "index_path", self.base / "indice.db"):
            self.assertEqual(self.rodar("sync").exit_code, 0)
            r = self.rodar("buscar", "reserva expira")
            self.assertEqual(r.exit_code, 0, r.output)
            self.assertIn("systems/portal.md", r.texto)
        self.assertEqual(self.rodar("budget").exit_code, 0)


class TestTriagem(Ambiente):
    def test_triar_por_arquivo_grava_pendente_e_aprovar_exige_trilha(self):
        did = self.nova()
        r = self.rodar("demanda", "triar", did, "--arquivo", self.triagem_em_arquivo())
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("Triagem gravada (pendente de aprovação).", r.texto)
        self.assertIn("Triagem: pendente de aprovação", self.rodar("demanda", "mostrar", did).texto)
        self.assertEqual(self.rodar("demanda", "triar", did, "--aprovar-por", "gestor-demandas").exit_code, 2)
        r = self.rodar("demanda", "triar", did, "--aprovar-por", "gestor-demandas", "--trilha", "completa")
        self.assertEqual(r.exit_code, 0, r.output)
        r = self.rodar("demanda", "mostrar", did)
        self.assertIn("Triagem: aprovada por gestor-demandas", r.texto)
        self.assertIn("Trilha: completa", r.texto)
        self.assertIn("Produto: portal", r.texto)
        self.assertIn("Nada falta para sair de intake.", r.texto)

    def test_triar_por_arquivo_ja_aprovado(self):
        did = self.nova()
        arq = self.triagem_em_arquivo(trilha="completa", aprovada_por="gestor-demandas", aprovada_em="2026-11-24")
        r = self.rodar("demanda", "triar", did, "--arquivo", arq)
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("Triagem gravada e aprovada.", r.texto)

    def test_triar_sem_modo_ou_com_os_dois_e_erro_de_uso(self):
        did = self.nova()
        self.assertEqual(self.rodar("demanda", "triar", did).exit_code, 2)
        r = self.rodar("demanda", "triar", did, "--arquivo", self.triagem_em_arquivo(),
                       "--aprovar-por", "gestor-demandas", "--trilha", "leve")
        self.assertEqual(r.exit_code, 2)

    def test_aprovar_sem_triagem_recusa(self):
        did = self.nova()
        r = self.rodar("demanda", "triar", did, "--aprovar-por", "gestor-demandas", "--trilha", "leve")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn(f"Demanda {did} não tem triagem para aprovar.", r.texto)

    def test_triar_com_produto_fora_do_catalogo_recusa(self):
        did = self.nova()
        for produto in ("estoque", "../fora", "a/b", ""):
            with self.subTest(produto=produto):
                r = self.rodar("demanda", "triar", did, "--arquivo", self.triagem_em_arquivo(produto=produto))
                self.assertEqual(r.exit_code, 1, r.output)
                self.assertIn("produto", r.texto)
        self.assertIn("Triagem: ausente", self.rodar("demanda", "mostrar", did).texto)

    def test_triar_com_produto_sem_ficha_recusa(self):
        self.catalogo({"portal": {"descricao": "Portal"}, "estoque": {"descricao": "Estoque"}})
        did = self.nova()
        r = self.rodar("demanda", "triar", did, "--arquivo", self.triagem_em_arquivo(produto="estoque"))
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("Produto estoque não tem ficha em", r.texto)
        self.assertIn("cli.py ficha nova", r.texto)
        self.assertFalse((self.fichas / "estoque").exists())

    def test_triar_com_json_ilegivel_recusa_sem_traceback(self):
        did = self.nova()
        arq = self.base / "ruim.json"
        for conteudo in ("{aberto", "[1, 2]", '"texto"', ""):
            with self.subTest(conteudo=conteudo):
                arq.write_text(conteudo, encoding="utf-8")
                r = self.rodar("demanda", "triar", did, "--arquivo", str(arq))
                self.assertEqual(r.exit_code, 1, r.output)
                self.assertIn("Arquivo de triagem inválido", r.texto)

    def test_triar_mostra_todos_os_erros_e_nao_grava(self):
        did = self.nova()
        arq = self.triagem_em_arquivo(trilha="leve", t1=None, criterios_de_aceite=[], aprovada_por="gestor-demandas")
        r = self.rodar("demanda", "triar", did, "--arquivo", arq)
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("pergunta t1 sem resposta", r.texto)
        self.assertIn("criterios_de_aceite", r.texto)
        self.assertIn("Triagem: ausente", self.rodar("demanda", "mostrar", did).texto)

    def test_trilha_troca_com_motivo_e_recusa_sem_motivo(self):
        did = self.em_spike()
        r = self.rodar("demanda", "triar", did, "--aprovar-por", "gestor-demandas", "--trilha", "operacional")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("demanda trilha", r.texto)
        self.assertIn("Trilha: completa", self.rodar("demanda", "mostrar", did).texto)
        r = self.rodar("demanda", "trilha", did, "operacional", "--motivo", "   ", "--ator", "gestor-demandas")
        self.assertEqual(r.exit_code, 1, r.output)
        r = self.rodar("demanda", "trilha", did, "operacional", "--motivo", "era só um pedido de operação", "--ator", "gestor-demandas")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("Trilha: operacional", self.rodar("demanda", "mostrar", did).texto)

    def test_avancar_sem_triagem_aprovada_diz_que_falta_a_triagem(self):
        did = self.nova()
        r = self.rodar("demanda", "avancar", did, "--ator", "gestor-demandas")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("Não avançou. Falta:", r.texto)
        self.assertIn("triagem aprovada", r.texto)
        self.assertIn("Fase: intake", self.rodar("demanda", "mostrar", did).texto)


class TestGeracao(Ambiente):
    def test_sessao_ate_a_visao_em_proposta(self):
        did = self.nova()
        r = self.rodar("gerar-artefatos", did)
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("triagem: gerado", r.texto)
        self.assertIn("Triagem: pendente de aprovação", self.rodar("demanda", "mostrar", did).texto)
        r = self.rodar("demanda", "triar", did, "--aprovar-por", "gestor-demandas", "--trilha", "completa")
        self.assertEqual(r.exit_code, 0, r.output)
        r = self.rodar("demanda", "avancar", did, "--ator", "gestor-demandas")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn(f"Demanda {did}: intake → spike.", r.texto)
        r = self.rodar("gerar-artefatos", did)
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn(f"visao: gerado portal/demandas/{did.lower()}/visao.mdx", r.texto)
        pagina = self.visao(did)
        self.assertTrue(pagina.is_file())
        self.assertEqual(yaml.safe_load(pagina.read_text(encoding="utf-8").split("---\n", 2)[1])["status"], "proposta")
        r = self.rodar("demanda", "avancar", did, "--ator", "gestor-demandas")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("ainda está em proposta", r.texto)
        self.assertIn("quem aprovou a visão", r.texto)
        self.assertIn("Fase: spike", self.rodar("demanda", "mostrar", did).texto)

    def test_validada_e_aprovada_a_visao_abre_o_portao(self):
        did = self.em_spike()
        self.assertEqual(self.rodar("gerar-artefatos", did).exit_code, 0)
        pagina = self.visao(did)
        pagina.write_text(pagina.read_text(encoding="utf-8").replace("status: proposta", "status: validada"), encoding="utf-8")
        r = self.rodar("demanda", "aprovar-visao", did, "--por", "gestor-demandas")
        self.assertEqual(r.exit_code, 0, r.output)
        r = self.rodar("demanda", "avancar", did, "--ator", "gestor-demandas")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("spike → spec", r.texto)

    def test_aprovar_visao_preserva_a_pagina_e_recusa_sem_visao(self):
        did = self.em_spike()
        r = self.rodar("demanda", "aprovar-visao", did, "--por", "gestor-demandas")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn(f"Demanda {did} não tem visão gerada.", r.texto)
        self.rodar("gerar-artefatos", did)
        self.assertEqual(self.rodar("demanda", "aprovar-visao", did, "--por", "gestor-demandas").exit_code, 0)
        visao = cli._servico_demandas()[0].get_demand(did).artefacts["visao"]
        self.assertEqual(visao["pagina"], f"portal/demandas/{did.lower()}/visao.mdx")
        self.assertEqual(visao["aprovada_por"], "gestor-demandas")

    def test_gerar_duas_vezes_nao_altera_e_refazer_so_regera_proposta(self):
        did = self.em_spike()
        self.rodar("gerar-artefatos", did)
        pagina = self.visao(did)
        pagina.write_text(pagina.read_text(encoding="utf-8") + "\nNota escrita à mão.\n", encoding="utf-8")
        editada = pagina.read_bytes()
        self.assertEqual(self.rodar("gerar-artefatos", did).exit_code, 0)
        self.assertEqual(pagina.read_bytes(), editada)
        self.assertEqual(self.rodar("gerar-artefatos", did, "--refazer").exit_code, 0)
        self.assertNotIn("Nota escrita à mão.", pagina.read_text(encoding="utf-8"))
        pagina.write_text(pagina.read_text(encoding="utf-8").replace("status: proposta", "status: validada")
                          + "\nRevisado.\n", encoding="utf-8")
        validada = pagina.read_bytes()
        self.assertEqual(self.rodar("gerar-artefatos", did, "--refazer").exit_code, 0)
        self.assertEqual(pagina.read_bytes(), validada)

    def test_gerar_sem_provedor_marca_falhou_e_nao_deixa_pagina(self):
        did = self.em_spike()
        for status in ("budget_exceeded", "escalate"):
            with self.subTest(status=status):
                self.status_ia = status
                r = self.rodar("gerar-artefatos", did)
                self.assertEqual(r.exit_code, 1, r.output)
                self.assertIn("visao: falhou", r.texto)
                self.assertFalse(self.visao(did).exists())
                self.assertEqual(list((self.fichas / "portal").rglob("*.mdx")), [])

    def test_produto_com_cara_de_caminho_no_rascunho_nao_grava_fora(self):
        self.respostas["triagem@1"] = {**PAYLOADS["triagem@1"], "produto": "../fora"}
        did = self.nova()
        self.rodar("gerar-artefatos", did)
        r = self.rodar("demanda", "triar", did, "--aprovar-por", "gestor-demandas", "--trilha", "completa")
        self.assertEqual(r.exit_code, 1, r.output)
        # o gerador já descarta o rascunho com produto inválido; se um dia guardar, a aprovação recusa
        self.assertTrue("produto" in r.texto or "não tem triagem para aprovar" in r.texto, r.texto)
        self.assertEqual([p for p in self.base.rglob("*.mdx")], [])
        self.assertFalse((self.base / "fora").exists())

    def test_gerar_recusa_produto_sem_ficha(self):
        did = self.em_spike()
        shutil.rmtree(self.fichas / "portal")
        r = self.rodar("gerar-artefatos", did)
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("Produto portal não tem ficha em", r.texto)
        self.assertFalse((self.fichas / "portal").exists())

    def test_pagina_com_frontmatter_quebrado_da_mensagem_sem_traceback(self):
        did = self.em_spike()
        self.rodar("gerar-artefatos", did)
        self.visao(did).write_text("---\nstatus: [aberto\n---\ntexto\n", encoding="utf-8")
        r = self.rodar("demanda", "mostrar", did)
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("não pôde ser lida", r.texto)
        r = self.rodar("demanda", "avancar", did, "--ator", "gestor-demandas")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("não pôde ser lida", r.texto)
        self.assertIn("visao.mdx", r.texto)


class TestAchadosDaRevisao(Ambiente):
    def test_trilha_nao_aprova_triagem_pendente(self):
        did = self.nova()
        self.assertEqual(self.rodar("gerar-artefatos", did).exit_code, 0)
        r = self.rodar("demanda", "trilha", did, "leve", "--motivo", "atalho", "--ator", "gestor-demandas")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("demanda triar", r.texto)
        self.assertIn("Triagem: pendente de aprovação", self.rodar("demanda", "mostrar", did).texto)
        self.assertEqual(self.rodar("demanda", "avancar", did, "--ator", "gestor-demandas").exit_code, 1)

    def test_trilha_sem_triagem_recusa(self):
        did = self.nova()
        r = self.rodar("demanda", "trilha", did, "leve", "--motivo", "m", "--ator", "gestor-demandas")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("demanda triar", r.texto)

    def test_artefato_com_arquivo_que_nao_e_utf8_recusa(self):
        did = self.nova()
        arq = self.base / "ruim.json"
        arq.write_bytes(bytes([34, 116, 255, 254, 34]))
        r = self.rodar("demanda", "artefato", did, "evidence", "--arquivo", str(arq))
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("Arquivo ilegível", r.texto)

    def test_runtime_sendo_um_arquivo_avisa_e_sai_1(self):
        (self.base / ".runtime").write_text("não sou uma pasta", encoding="utf-8")
        for args in (("demanda", "listar"), ("demanda", "nova", "x"), ("gerar-artefatos", "DEM-001")):
            with self.subTest(args=args):
                r = self.rodar(*args)
                self.assertEqual(r.exit_code, 1, r.output)
                self.assertIn("Não foi possível ler o banco de demandas", r.texto)

    def test_perfil_inexistente_ou_invalido_recusa_dizendo_que_e_o_perfil(self):
        from core.local_tasks import profile as perfil
        for nome in ("perfil-que-nao-existe", "../x"):
            with self.subTest(nome=nome):
                with mock.patch.object(ligacao, "caminho_produtos", lambda p=None, nome=nome: (
                        (_ for _ in ()).throw(perfil.ProfileNotFound(nome)) if not perfil._NAME_RE.match(nome)
                        else self.base / "perfis" / nome / "produtos.yaml")):
                    r = self.rodar("demanda", "nova", "x")
                self.assertEqual(r.exit_code, 1, r.output)
                self.assertIn("Perfil", r.texto)
                self.assertIn("não encontrado", r.texto)
                self.assertNotIn("Catálogo de produtos inválido", r.texto)

    def test_perfil_sem_catalogo_avisa_que_nao_confere_o_produto(self):
        self.produtos.unlink()
        r = self.rodar("demanda", "nova", "x")
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("sem catálogo de produtos", r.texto)


class TestArtefato(Ambiente):
    def test_artefato_recusa_triagem_geracao_e_json_invalido(self):
        did = self.nova()
        for nome, dica in (("triagem", "demanda triar"), ("geracao", "gerar-artefatos")):
            with self.subTest(nome=nome):
                r = self.rodar("demanda", "artefato", did, nome, "--valor", "{}")
                self.assertEqual(r.exit_code, 1, r.output)
                self.assertIn(dica, r.texto)
        r = self.rodar("demanda", "artefato", did, "evidence", "--valor", "texto solto")
        self.assertEqual(r.exit_code, 1, r.output)
        self.assertIn("JSON", r.texto)
        self.assertEqual(self.rodar("demanda", "artefato", did, "evidence").exit_code, 2)
        arq = self.base / "e.json"
        arq.write_text('{"link": "x"}', encoding="utf-8")
        self.assertEqual(self.rodar("demanda", "artefato", did, "evidence", "--valor", '"a"', "--arquivo", str(arq)).exit_code, 2)
        r = self.rodar("demanda", "artefato", did, "evidence", "--arquivo", str(arq))
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("evidence", self.rodar("demanda", "mostrar", did).texto)

    def test_rastreio_para_arquivo_inexistente_grava_e_o_portao_explica(self):
        did = self.nova()
        r = self.rodar("demanda", "artefato", did, "rastreio", "--valor", json.dumps(str(self.base / "nao-existe.json")))
        self.assertEqual(r.exit_code, 0, r.output)
        self.assertIn("rastreio", self.rodar("demanda", "mostrar", did).texto)


if __name__ == "__main__":
    unittest.main()
