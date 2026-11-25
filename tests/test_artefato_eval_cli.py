import json
from pathlib import Path

from click.testing import CliRunner

import cli as cli_module
from core.geracao import ligacao
from core.protocol import registry

FIXTURE = Path(__file__).parent / "fixtures" / "artefato_eval.json"
TEMPLATES = ["triagem@1", "visao@1", "cronograma@1", "regras@1",
             "historias@1", "casos-de-uso@1", "rnf@1", "telas@1"]


def _envelope(payload, custo=0.0003):
    return {"status": "ok", "payload": payload, "cost": {"actual_usd": custo}}


def test_dataset_de_fixture_tem_demandas_ficticias():
    demandas = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert 2 <= len(demandas) <= 3
    assert all(d["titulo"] and d["descricao"] for d in demandas)


def test_artefato_eval_sai_1_abaixo_de_60_por_cento(monkeypatch):
    chamadas = []

    def falso(template, texto):
        chamadas.append(template)
        return _envelope({})  # vazio: invalida em todo template com campos obrigatórios

    monkeypatch.setattr(ligacao, "_cliente_ia", falso)
    r = CliRunner().invoke(cli_module.cli, ["artefato-eval", "--dataset", str(FIXTURE)])
    assert r.exit_code == 1
    n = len(json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert len(chamadas) == n * len(TEMPLATES)
    for t in TEMPLATES:
        assert t in r.output


def test_artefato_eval_sai_0_quando_a_maioria_valida(monkeypatch):
    def falso(template, texto):
        return _envelope(_VALIDOS[template])

    monkeypatch.setattr(ligacao, "_cliente_ia", falso)
    r = CliRunner().invoke(cli_module.cli, ["artefato-eval", "--dataset", str(FIXTURE)])
    assert r.exit_code == 0, r.output
    assert "válido" in r.output
    assert "0.0003" in r.output


def test_artefato_eval_erro_do_cliente_conta_como_invalido(monkeypatch):
    def falso(template, texto):
        raise RuntimeError("provedor fora")

    monkeypatch.setattr(ligacao, "_cliente_ia", falso)
    r = CliRunner().invoke(cli_module.cli, ["artefato-eval", "--dataset", str(FIXTURE)])
    assert r.exit_code == 1


def _gerar_validos():
    """Minimal payloads built from each schema's required keys (the schemas are the contract)."""
    saida = {}
    for t in TEMPLATES:
        saida[t] = _minimo(registry.load_schema(t))
    return saida


def _minimo(schema):
    tipo = schema.get("type")
    if "enum" in schema:
        return schema["enum"][0]
    if tipo == "object":
        props = schema.get("properties", {})
        return {k: _minimo(props[k]) for k in schema.get("required", [])}
    if tipo == "array":
        n = schema.get("minItems", 0)
        return [_minimo(schema.get("items", {})) for _ in range(n)]
    if tipo == "boolean":
        return False
    if tipo in ("integer", "number"):
        return schema.get("minimum", 0)
    return "x" * schema.get("minLength", 1)


_VALIDOS = _gerar_validos()
