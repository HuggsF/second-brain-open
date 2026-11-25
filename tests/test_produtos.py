"""Catálogo de produtos e guia de triagem do perfil."""
import tempfile
import unittest
from pathlib import Path

from config import settings
from core.produtos import Produto, ProdutosInvalidos, ler_guia_triagem, ler_produtos


class TestLerProdutos(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.arquivo = Path(tmp.name) / "produtos.yaml"

    def ler(self, texto):
        self.arquivo.write_text(texto, encoding="utf-8")
        return ler_produtos(self.arquivo)

    def test_arquivo_ausente_e_catalogo_vazio(self):
        self.assertEqual(ler_produtos(self.arquivo), {})

    def test_arquivo_vazio_e_catalogo_vazio(self):
        self.assertEqual(self.ler(""), {})
        self.assertEqual(self.ler("# só comentário\n"), {})

    def test_le_slug_descricao_pistas_e_testes(self):
        produtos = self.ler(
            "portal:\n  descricao: Portal do cliente\n  pistas: [login, cadastro]\n  testes_rastreio: tests/**/*.py\n"
            "estoque:\n  descricao: '  Reserva de estoque  '\n"
        )
        self.assertEqual(produtos["portal"], Produto("portal", "Portal do cliente", ("login", "cadastro"), "tests/**/*.py"))
        self.assertEqual(produtos["estoque"], Produto("estoque", "Reserva de estoque"))
        self.assertEqual(list(produtos), ["portal", "estoque"])

    def test_campo_repositorio_e_aceito_e_ignorado(self):
        produtos = self.ler("portal:\n  descricao: Portal\n  repositorio:\n    caminho: /x\n    base: main\n")
        self.assertEqual(produtos["portal"], Produto("portal", "Portal"))

    def test_slug_invalido_e_recusado(self):
        for slug in ("Portal", "a/b", "'../x'", "''", "a b", "-x"):
            with self.subTest(slug=slug):
                with self.assertRaises(ProdutosInvalidos):
                    self.ler(f"{slug}:\n  descricao: x\n")

    def test_slug_que_nao_e_texto_e_recusado(self):
        with self.assertRaises(ProdutosInvalidos):
            self.ler("1:\n  descricao: x\n")

    def test_descricao_ausente_ou_vazia_e_recusada(self):
        for corpo in ("portal: {}\n", "portal:\n  descricao: ''\n", "portal:\n  descricao: '   '\n",
                      "portal:\n  descricao: 3\n", "portal: texto solto\n", "portal:\n"):
            with self.subTest(corpo=corpo):
                with self.assertRaises(ProdutosInvalidos):
                    self.ler(corpo)

    def test_pistas_e_testes_malformados_sao_recusados(self):
        for corpo in ("portal:\n  descricao: x\n  pistas: solta\n", "portal:\n  descricao: x\n  pistas: [1, 2]\n",
                      "portal:\n  descricao: x\n  testes_rastreio: 3\n", "portal:\n  descricao: x\n  testes_rastreio: ' '\n"):
            with self.subTest(corpo=corpo):
                with self.assertRaises(ProdutosInvalidos):
                    self.ler(corpo)

    def test_topo_que_nao_e_mapa_e_recusado(self):
        for corpo in ("- portal\n", "portal\n"):
            with self.subTest(corpo=corpo):
                with self.assertRaises(ProdutosInvalidos):
                    self.ler(corpo)

    def test_yaml_quebrado_vira_produtos_invalidos(self):
        with self.assertRaises(ProdutosInvalidos):
            self.ler("portal: [aberto\n")

    def test_erro_e_um_value_error(self):
        self.assertTrue(issubclass(ProdutosInvalidos, ValueError))


class TestGuiaDeTriagem(unittest.TestCase):
    def test_guia_ausente_e_vazio_e_guia_presente_vem_sem_espacos_nas_pontas(self):
        with tempfile.TemporaryDirectory() as tmp:
            guia = Path(tmp) / "guia_triagem.md"
            self.assertEqual(ler_guia_triagem(guia), "")
            guia.write_text("\n\n  T1: muda regra?  \n\n", encoding="utf-8")
            self.assertEqual(ler_guia_triagem(guia), "T1: muda regra?")


class TestPerfilDeExemplo(unittest.TestCase):
    PERFIL = settings.base_dir / "profiles" / "example"

    def test_catalogo_de_exemplo_tem_uma_ficha_por_produto(self):
        produtos = ler_produtos(self.PERFIL / "produtos.yaml")
        self.assertTrue(produtos)
        for slug in produtos:
            with self.subTest(slug=slug):
                self.assertTrue((settings.base_dir / "fichas" / slug / "ficha.md").is_file())

    def test_guia_de_exemplo_cobre_o_metodo(self):
        guia = ler_guia_triagem(self.PERFIL / "guia_triagem.md")
        for trecho in ("T1", "T2", "T3", "T4", "operacional", "correcao_direta", "leve", "completa",
                       "atividade", "faixa", "criterios_de_aceite", "mais_de_uma_sprint", "fictício"):
            with self.subTest(trecho=trecho):
                self.assertIn(trecho, guia)


if __name__ == "__main__":
    unittest.main()
