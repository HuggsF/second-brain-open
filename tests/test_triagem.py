from core.triagem import Trilha, TRIAGEM_TEMPLATE, trilha_sugerida, erros_triagem, artefatos_exigidos


def _triagem(**kw):
    t = {**TRIAGEM_TEMPLATE, "t1": False, "t2": False, "t3": False, "t4": True,
         "trilha": "leve", "aprovada_por": "gestor", "aprovada_em": "2026-11-09",
         "criterios_de_aceite": ["ok"]}
    t.update(kw)
    return t


def test_trilha_operacional_vem_do_tipo():
    assert trilha_sugerida(True, True, True, False, "operacional") == Trilha.OPERACIONAL


def test_bug_sem_regra_de_negocio_e_correcao_direta():
    assert trilha_sugerida(False, False, False, False, "bug") == Trilha.CORRECAO_DIRETA


def test_t4_sem_outros_sim_e_leve():
    assert trilha_sugerida(False, False, False, True, "outro") == Trilha.LEVE


def test_caso_29132_e_completa():
    assert trilha_sugerida(True, True, True, False, "outro") == Trilha.COMPLETA


def test_template_tem_mais_de_uma_sprint():
    assert TRIAGEM_TEMPLATE["mais_de_uma_sprint"] is False


def test_triagem_sem_aprovador_tem_erro():
    assert erros_triagem(_triagem(aprovada_por=""))
    assert erros_triagem(_triagem()) == []


def test_leve_sem_criterios_tem_erro():
    assert erros_triagem(_triagem(criterios_de_aceite=[]))


def test_completa_spec_dev_com_t1_exige_regras():
    r = artefatos_exigidos(Trilha.COMPLETA, "spec", "dev", True, False, False, False)
    assert "regras" in r and "historias" in r


def test_completa_spec_dev_sem_t2_nao_exige_telas():
    r = artefatos_exigidos(Trilha.COMPLETA, "spec", "dev", True, False, True, False)
    assert "telas" not in r and "casos_de_uso" in r and "rnf" in r


def test_completa_review_done_exige_rastreio():
    r = artefatos_exigidos(Trilha.COMPLETA, "review", "done", False, False, False, False)
    assert r == ["evidence", "aceite_area", "rastreio"]


def test_demais_celulas():
    f = artefatos_exigidos
    assert f(Trilha.COMPLETA, "spike", "spec", 0, 0, 0, True) == ["visao", "cronograma"]
    assert f(Trilha.LEVE, "spike", "spec", 0, 0, 0, True) == []
    assert f(Trilha.CORRECAO_DIRETA, "spec", "dev", 0, 0, 0, False) == ["teste_reproducao"]
    assert f(Trilha.OPERACIONAL, "intake", "spike", 0, 0, 0, False) == ["triagem"]
    assert f(Trilha.LEVE, "review", "done", 0, 0, 0, False) == ["evidence"]


# -- F2: T1 a T3 = SIM exigem trilha completa, salvo rebaixamento registrado ------

import pytest  # noqa: E402

_REB = [{"de": "completa", "para": "leve", "motivo": "escopo", "autor": "gestor-demandas", "em": "2026-11-09"}]


@pytest.mark.parametrize("trilha,pergunta", [
    ("leve", "t1"), ("leve", "t2"), ("leve", "t3"), ("correcao_direta", "t1"),
])
def test_sim_que_a_trilha_nao_admite_tem_erro(pergunta, trilha):
    erros = erros_triagem(_triagem(trilha=trilha, **{pergunta: True}))
    assert any(pergunta in e and trilha in e and "completa" in e for e in erros), erros


def test_trilhas_que_a_spec_admite_com_sim_passam():
    # correcao direta so exige T1 = NAO; operacional vem do tipo do pedido
    assert erros_triagem(_triagem(trilha="correcao_direta", t2=True, t3=True, t4=False)) == []
    assert erros_triagem(_triagem(trilha="operacional", t1=True, t2=True, t3=True, t4=False)) == []


def test_completa_com_t1_sim_passa():
    assert erros_triagem(_triagem(trilha="completa", t1=True, t4=False)) == []


def test_leve_com_t1_sim_e_rebaixamento_registrado_passa():
    assert erros_triagem(_triagem(t1=True, rebaixamentos=_REB)) == []


# -- produto do catálogo ---------------------------------------------

def test_produto_do_catalogo_passa():
    assert erros_triagem(_triagem(produto="produto-a"), produtos={"produto-a", "produto-b"}) == []


def test_produto_fora_do_catalogo_tem_erro_com_os_validos():
    [erro] = erros_triagem(_triagem(produto="inventado"), produtos={"produto-b", "produto-a"})
    assert "inventado" in erro and "fora do catálogo" in erro and "produto-a, produto-b" in erro


def test_triagem_sem_produto_tem_erro_quando_ha_catalogo():
    assert erros_triagem(_triagem(), produtos={"produto-a"}) == ["triagem sem produto"]
    assert erros_triagem(_triagem(produto="  "), produtos={"produto-a"}) == ["triagem sem produto"]


def test_sem_catalogo_nao_confere_produto():
    assert erros_triagem(_triagem(produto="qualquer")) == []
    assert erros_triagem(_triagem(produto="qualquer"), produtos=None) == []
