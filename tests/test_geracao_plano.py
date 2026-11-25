import unittest

from core.demand_lifecycle import Demand, Phase
from core.geracao.plano import ItemDeGeracao, plano


def _triagem(**kw):
    base = {"t1": False, "t2": False, "t3": False, "t4": False, "trilha": "completa",
            "aprovada_por": "gestor", "aprovada_em": "2026-11-09", "produto": "portal",
            "mais_de_uma_sprint": False}
    base.update(kw)
    return base


def _demanda(fase, triagem="padrao", **extra):
    arte = dict(extra)
    if triagem == "padrao":
        triagem = _triagem()
    if triagem is not None:
        arte["triagem"] = triagem
    return Demand(id="DEM-005", title="t", description="d", source="manual",
                  priority="medium", phase=Phase(fase), artefacts=arte)


def _nomes(itens):
    return [i.artefato for i in itens]


class TestPlano(unittest.TestCase):
    def test_sem_triagem_gera_so_triagem(self):
        self.assertEqual(plano(_demanda("intake", triagem=None)),
                         [ItemDeGeracao("triagem", "triagem@1", None, True)])

    def test_triagem_existente_nao_aprovada_nao_gera_nada(self):
        self.assertEqual(plano(_demanda("intake", triagem=_triagem(aprovada_por=""))), [])

    def test_completa_em_spike_gera_visao(self):
        self.assertEqual(_nomes(plano(_demanda("spike"))), ["visao"])

    def test_completa_em_spike_com_mais_de_uma_sprint_gera_cronograma(self):
        d = _demanda("spike", triagem=_triagem(mais_de_uma_sprint=True))
        self.assertEqual(_nomes(plano(d)), ["visao", "cronograma"])

    def test_completa_em_spec_t1_t2_t3_gera_regras_historias_telas_cu_rnf(self):
        d = _demanda("spec", triagem=_triagem(t1=True, t2=True, t3=True))
        itens = {i.artefato: i for i in plano(d)}
        self.assertEqual(set(itens), {"regras", "historias", "telas", "casos_de_uso", "rnf"})
        self.assertEqual(itens["regras"], ItemDeGeracao("regras", "regras@1", None, True))
        self.assertEqual(itens["casos_de_uso"].template, "casos-de-uso@1")
        self.assertEqual(itens["casos_de_uso"].caminho,
                         "portal/demandas/dem-005/casos-de-uso.mdx")

    def test_leve_em_spike_nao_gera_nada(self):
        d = _demanda("spike", triagem=_triagem(trilha="leve", t4=True,
                                               criterios_de_aceite=["x"]))
        self.assertEqual(plano(d), [])

    def test_artefato_existente_sai_do_plano(self):
        self.assertEqual(plano(_demanda("spike", visao={"x": 1})), [])

    def test_completa_em_dev_gera_plano_de_testes(self):
        d = _demanda("dev", triagem=_triagem(t1=True))
        self.assertEqual(plano(d), [ItemDeGeracao("plano_de_testes", None, None, False)])
        self.assertEqual(plano(_demanda("dev", triagem=_triagem(t1=True), plano_de_testes={})), [])
        self.assertEqual(plano(_demanda("dev")), [])

    def test_completa_em_review_gera_rastreio(self):
        self.assertEqual(plano(_demanda("review")),
                         [ItemDeGeracao("rastreio", None, None, False)])

    def test_rastreio_entra_no_plano_mesmo_ja_no_card(self):
        # Deterministic and not a page: recalculated on every run in review.
        self.assertEqual(_nomes(plano(_demanda("review", rastreio="/x/DEM-005.json"))), ["rastreio"])

    def test_caminho_por_demanda(self):
        (item,) = plano(_demanda("spike"))
        self.assertEqual(item.template, "visao@1")
        self.assertEqual(item.caminho, "portal/demandas/dem-005/visao.mdx")
        self.assertTrue(item.usa_ia)

    def test_produto_invalido_com_pagina_levanta(self):
        for produto in ("", None, 5, "Portal", "../x"):
            with self.subTest(produto=produto):
                d = _demanda("spike", triagem=_triagem(produto=produto))
                with self.assertRaisesRegex(ValueError, "triagem sem produto válido"):
                    plano(d)
        d = _demanda("spike", triagem=_triagem())
        d.artefacts["triagem"].pop("produto")
        with self.assertRaises(ValueError):
            plano(d)

    def test_produto_invalido_sem_pagina_nao_levanta(self):
        for produto in ("", None, 5, "../x"):
            with self.subTest(produto=produto):
                self.assertEqual(
                    _nomes(plano(_demanda("review", triagem=_triagem(produto=produto)))),
                    ["rastreio"])
                self.assertEqual(
                    _nomes(plano(_demanda("dev", triagem=_triagem(t1=True, produto=produto)))),
                    ["plano_de_testes"])
        self.assertEqual(_nomes(plano(_demanda("intake", triagem=None))), ["triagem"])


if __name__ == "__main__":
    unittest.main()
