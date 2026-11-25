import json
import unittest
from types import SimpleNamespace

from core.geracao.contexto import montar
from core.produtos import Produto
from core.geracao.plano import ItemDeGeracao


def demanda(artefacts=None):
    return SimpleNamespace(id="DEM-1", title="Título X", description="Descrição Y",
                           artefacts=artefacts if artefacts is not None else {"trilha": "feature"})


VISAO = ItemDeGeracao("visao", "visao@1", "p/demandas/dem-1/visao.mdx", True)
SPEC = ItemDeGeracao("historias", "historias@1", "p/demandas/dem-1/historias.mdx", True)


class ContextoTests(unittest.TestCase):
    def test_texto_tem_titulo_descricao_e_triagem(self):
        texto, com = montar(demanda({"triagem": {"trilha": "feature"}}), VISAO, lambda q: ["trecho a"], lambda r: None)
        self.assertIn("Título X", texto)
        self.assertIn("Descrição Y", texto)
        self.assertIn(json.dumps({"trilha": "feature"}, ensure_ascii=False), texto)
        self.assertIn("trecho a", texto)
        self.assertIn("visao@1", texto)
        self.assertTrue(com)

    def test_nao_envia_artefatos_fora_da_triagem(self):
        arts = {"triagem": {"trilha": "feature"}, "geracao": {"estado": "x"},
                "visao": {"pagina": "p/visao.mdx", "aprovada_por": "analista"}}
        texto, _ = montar(demanda(arts), SPEC, lambda q: [], lambda r: None)
        self.assertNotIn("analista", texto)
        self.assertNotIn("geracao", texto)
        self.assertNotIn("p/visao.mdx", texto)

    def test_spec_inclui_a_visao(self):
        arts = {"visao": {"pagina": "p/visao.mdx", "aprovada_por": "x"}, "cronograma": "p/cron.mdx"}
        paginas = {"p/visao.mdx": "CONTEUDO-VISAO", "p/cron.mdx": "CONTEUDO-CRON"}
        texto, _ = montar(demanda(arts), SPEC, lambda q: [], paginas.get)
        self.assertIn("CONTEUDO-VISAO", texto)
        self.assertIn("CONTEUDO-CRON", texto)
        self.assertLess(texto.index("CONTEUDO-VISAO"), texto.index("CONTEUDO-CRON"))

    def test_paginas_vao_sem_frontmatter_e_triagem_sem_aprovador(self):
        arts = {"triagem": {"trilha": "completa", "aprovada_por": "gestor-demandas", "produto": "p",
                            "rebaixamentos": [{"autor": "diretoria", "motivo": "m"}]},
                "regras": ["p/regras/r.mdx"]}
        pagina = ("---\nid: p.r\ndono:\n  area: Fin\n  pessoa: Ana Pessoa\navais:\n"
                  "  - area: Fin\n    email: area-solicitante@empresa.example\n---\n\n## Regra\n\nCORPO-DA-REGRA\n")
        texto, _ = montar(demanda(arts), SPEC, lambda q: [], {"p/regras/r.mdx": pagina}.get)
        self.assertIn("CORPO-DA-REGRA", texto)
        for segredo in ("area-solicitante@empresa.example", "Ana Pessoa", "gestor-demandas", "diretoria",
                        "aprovada_por", "rebaixamentos"):
            self.assertNotIn(segredo, texto)
        self.assertIn('"produto": "p"', texto)

    def test_busca_falhando_segue_sem_vault(self):
        def busca(q):
            raise RuntimeError("índice fora")
        texto, com = montar(demanda(), VISAO, busca, lambda r: None)
        self.assertFalse(com)
        self.assertIn("Título X", texto)

    def test_limita_quatro_trechos(self):
        texto, com = montar(demanda(), VISAO, lambda q: [f"TRECHO{i}" for i in range(7)], lambda r: None)
        self.assertEqual(sum(f"TRECHO{i}" in texto for i in range(7)), 4)
        self.assertTrue(com)


if __name__ == "__main__":
    unittest.main()


TRIAGEM_ITEM = ItemDeGeracao("triagem", "triagem@1", None, True)
CATALOGO = {"produto-a": Produto("produto-a", "Faz A.", ("categoria A no chamado", "palavra-a")),
            "produto-b": Produto("produto-b", "Faz B.")}


class CatalogoNoContextoTests(unittest.TestCase):
    def test_triagem_recebe_os_slugs_descricoes_e_pistas(self):
        texto, _ = montar(demanda({}), TRIAGEM_ITEM, lambda q: [], lambda r: None, produtos=CATALOGO)
        self.assertIn("# Produtos do catálogo", texto)
        self.assertIn("- produto-a: Faz A. Pistas: categoria A no chamado; palavra-a", texto)
        self.assertIn("- produto-b: Faz B.", texto)
        self.assertLess(texto.index("# Produtos do catálogo"), texto.index("# Tarefa"))

    def test_outros_artefatos_nao_recebem_o_catalogo(self):
        texto, _ = montar(demanda({"triagem": {"produto": "produto-a"}}), VISAO, lambda q: [], lambda r: None,
                          produtos=CATALOGO)
        self.assertNotIn("Produtos do catálogo", texto)

    def test_sem_catalogo_nao_muda_o_texto(self):
        a, _ = montar(demanda({}), TRIAGEM_ITEM, lambda q: [], lambda r: None)
        b, _ = montar(demanda({}), TRIAGEM_ITEM, lambda q: [], lambda r: None, produtos={})
        self.assertEqual(a, b)
        self.assertNotIn("Produtos do catálogo", a)


class GuiaNoContextoTests(unittest.TestCase):
    def test_triagem_recebe_o_guia_antes_do_catalogo(self):
        texto, _ = montar(demanda({}), TRIAGEM_ITEM, lambda q: [], lambda r: None, produtos=CATALOGO,
                          guia="T1: muda regra?")
        self.assertIn("# Como triar\nT1: muda regra?", texto)
        self.assertLess(texto.index("# Como triar"), texto.index("# Produtos do catálogo"))

    def test_outros_artefatos_nao_recebem_o_guia(self):
        texto, _ = montar(demanda({}), VISAO, lambda q: [], lambda r: None, guia="T1: muda regra?")
        self.assertNotIn("Como triar", texto)

    def test_guia_vazio_nao_entra(self):
        texto, _ = montar(demanda({}), TRIAGEM_ITEM, lambda q: [], lambda r: None, guia="  ")
        self.assertNotIn("Como triar", texto)


class RascunhoAnteriorTests(unittest.TestCase):
    def test_triagem_nao_recebe_o_rascunho_anterior(self):
        antigo = {"trilha_sugerida": "correcao_direta", "justificativa": "RASCUNHO-ANTIGO", "t2": False}
        texto, _ = montar(demanda({"triagem": antigo}), TRIAGEM_ITEM, lambda q: [], lambda r: None)
        self.assertNotIn("RASCUNHO-ANTIGO", texto)
        self.assertNotIn("# Triagem", texto)

    def test_outros_artefatos_seguem_recebendo_a_triagem(self):
        texto, _ = montar(demanda({"triagem": {"justificativa": "APROVADA"}}), VISAO, lambda q: [], lambda r: None)
        self.assertIn("APROVADA", texto)
