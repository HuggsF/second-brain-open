"""Schemas de extração dos artefatos de fase (S2b)."""
import pytest

from core.protocol import registry

REFS = ["triagem@1", "visao@1", "cronograma@1", "regras@1", "historias@1",
        "casos-de-uso@1", "rnf@1", "telas@1"]

TRIAGEM = {
    "produto": "portal", "t1": True, "t2": False, "t3": False, "t4": True,
    "trilha": "leve", "atividade": "ajuste", "faixa": "P",
    "criterios_de_aceite": ["a"], "mais_de_uma_sprint": False, "justificativa": "x",
}


def _regra(n_exemplos=2):
    ex = {"dado": "d", "quando": "q", "entao": "e"}
    return {"slug": "r", "titulo": "t", "regra": "r", "exemplos": [ex] * n_exemplos,
            "por_que": "p", "se_nao_existisse": "s", "perguntas": []}


@pytest.mark.parametrize("ref", REFS)
def test_cada_template_carrega(ref):
    schema = registry.load_schema(ref)
    assert schema["title"] == ref
    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["additionalProperties"] is True
    assert ref in registry.available()


def test_triagem_valida_passa():
    assert registry.validate("triagem@1", TRIAGEM) == []


@pytest.mark.parametrize("produto", ["Portal de Reserva", "", "../x"])
def test_triagem_produto_invalido(produto):
    assert registry.validate("triagem@1", {**TRIAGEM, "produto": produto})


def test_trilha_fora_do_enum_falha():
    assert registry.validate("triagem@1", {**TRIAGEM, "trilha": "rapida"})


def test_triagem_campo_obrigatorio_ausente():
    obj = dict(TRIAGEM)
    del obj["justificativa"]
    assert registry.validate("triagem@1", obj)


def test_regras_exige_dois_exemplos():
    assert registry.validate("regras@1", {"regras": [_regra(2)]}) == []
    assert registry.validate("regras@1", {"regras": [_regra(1)]})
    assert registry.validate("regras@1", {"regras": []})


def test_vazios_validos_e_tipos():
    assert registry.validate("cronograma@1", {"marcos": [{"nome": "n", "semana": "1", "portao": "p"}]}) == []
    assert registry.validate("cronograma@1", {"marcos": [{"nome": "n"}]})
    assert registry.validate("rnf@1", {"requisitos": []}) == []
    assert registry.validate("telas@1", {"telas": [{"nome": "n"}]})
