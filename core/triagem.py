"""Triagem da demanda: trilhas e artefatos exigidos por trilha (funcoes puras)."""
from __future__ import annotations

import json
from collections.abc import Collection
from enum import Enum
from pathlib import Path


class Trilha(str, Enum):
    OPERACIONAL = "operacional"
    CORRECAO_DIRETA = "correcao_direta"
    LEVE = "leve"
    COMPLETA = "completa"


AGUARDANDO = ("gestor", "area_solicitante", "infraestrutura", "fornecedor", "outra_tarefa", "outro_externo")

TRIAGEM_TEMPLATE: dict = {
    "t1": None, "t2": None, "t3": None, "t4": None,
    "trilha": "", "aprovada_por": "", "aprovada_em": "",
    "atividade": "", "faixa": "",
    "criterios_de_aceite": [], "rebaixamentos": [],
    "mais_de_uma_sprint": False,
}


def trilha_sugerida(t1: bool, t2: bool, t3: bool, t4: bool, tipo: str) -> Trilha:
    if tipo == "operacional":
        return Trilha.OPERACIONAL
    if tipo == "bug" and not t1:
        return Trilha.CORRECAO_DIRETA
    if t4 and not (t1 or t2 or t3):
        return Trilha.LEVE
    return Trilha.COMPLETA


def _erros_produto(triagem: dict, produtos: Collection[str]) -> list[str]:
    """Com catálogo, o ``produto`` da triagem tem de ser um dos slugs dele."""
    produto = triagem.get("produto")
    if not isinstance(produto, str) or not produto.strip():
        return ["triagem sem produto"]
    if produto not in produtos:
        return [f"produto {produto!r} fora do catálogo do perfil (válidos: {', '.join(sorted(produtos))})"]
    return []


def erros_triagem(triagem: dict, produtos: Collection[str] | None = None) -> list[str]:
    """Erros que impedem a triagem de valer; *produtos* é o catálogo do perfil (``None`` não confere)."""
    erros: list[str] = []
    if produtos is not None:
        erros.extend(_erros_produto(triagem, produtos))
    try:
        trilha = Trilha(triagem.get("trilha"))
    except ValueError:
        trilha = None
        erros.append("trilha ausente ou invalida")
    for k in ("t1", "t2", "t3", "t4"):
        if triagem.get(k) is None:
            erros.append(f"pergunta {k} sem resposta")
    if not triagem.get("aprovada_por"):
        erros.append("trilha sem aprovacao do gestor (aprovada_por vazio)")
    if trilha == Trilha.LEVE and not triagem.get("criterios_de_aceite"):
        erros.append("trilha leve exige criterios_de_aceite")
    # leve so com T1 a T3 = NAO; correcao direta so com T1 = NAO.
    # Um rebaixamento registrado (motivo e autor) libera a trilha mais leve.
    if trilha in _SIM_PROIBIDO and not triagem.get("rebaixamentos"):
        for k in _SIM_PROIBIDO[trilha]:
            if triagem.get(k):
                erros.append(
                    f"{k} = SIM nao cabe na trilha {trilha.value}: use a trilha completa "
                    "ou registre o rebaixamento com motivo"
                )
    return erros


_SIM_PROIBIDO: dict[Trilha, tuple[str, ...]] = {
    Trilha.LEVE: ("t1", "t2", "t3"),
    Trilha.CORRECAO_DIRETA: ("t1",),
}


def artefatos_exigidos(trilha: Trilha, origem: str, destino: str, t1: bool, t2: bool,
                       t3: bool, mais_de_uma_sprint: bool) -> list[str]:
    trilha = Trilha(trilha)
    par = (origem, destino)
    if par == ("intake", "spike"):
        return ["triagem"]
    if par == ("spike", "spec"):
        if trilha == Trilha.COMPLETA:
            return ["visao"] + (["cronograma"] if mais_de_uma_sprint else [])
        return []
    if par == ("spec", "dev"):
        if trilha == Trilha.CORRECAO_DIRETA:
            return ["teste_reproducao"]
        if trilha == Trilha.COMPLETA:
            r = ["historias"]
            if t1:
                r.append("regras")
            if t2:
                r.append("telas")
            if t3:
                r += ["casos_de_uso", "rnf"]
            return r
        return []
    if par == ("review", "done"):
        r = ["evidence"]
        if trilha == Trilha.COMPLETA:
            r += ["aceite_area", "rastreio"]
        return r
    return []


PROXIMA_FASE = {"intake": "spike", "spike": "spec", "spec": "dev", "dev": "review", "review": "done"}


def exigidos_da_fase(triagem: dict | None, fase: str) -> list[str]:
    """Artefatos que a fase precisa produzir para sair dela (portão e geração usam a mesma conta)."""
    if fase == "intake":
        return ["triagem"]
    if not isinstance(triagem, dict) or erros_triagem(triagem):
        return []
    destino = PROXIMA_FASE.get(fase)
    if destino is None:
        return []
    trilha = Trilha(triagem["trilha"])
    t1, t2, t3 = (bool(triagem.get(k)) for k in ("t1", "t2", "t3"))
    exigidos = artefatos_exigidos(trilha, fase, destino, t1, t2, t3,
                                  bool(triagem.get("mais_de_uma_sprint", False)))
    if fase == "dev" and trilha == Trilha.COMPLETA and t1:
        exigidos = [*exigidos, "plano_de_testes"]
    return exigidos


def erros_rastreio(caminho: Path, produto: str | None = None) -> list[str]:
    """Confere o JSON do verificador de rastreio (versão 1); lista os erros legíveis.

    Com *produto*, o campo ``produto`` do JSON tem de ser igual a ele.
    """
    caminho = Path(caminho)
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"rastreio: arquivo não encontrado: {caminho}"]
    except (OSError, ValueError) as exc:
        return [f"rastreio: arquivo inválido ({caminho}): {exc}"]
    if not isinstance(dados, dict):
        return [f"rastreio: arquivo inválido ({caminho}): esperado um objeto JSON"]
    if dados.get("versao") != 1:
        return [f"rastreio: versão {dados.get('versao')!r} não suportada (esperado 1)"]
    erros: list[str] = []
    if produto is not None and dados.get("produto") != produto:
        erros.append(
            f"rastreio: produto {dados.get('produto')!r} no arquivo, esperado {produto!r} "
            "(produto das regras da demanda)"
        )
    for campo in ("orfaos", "fantasmas"):
        if not isinstance(dados.get(campo) or [], list):
            return [f"rastreio: arquivo inválido ({caminho}): {campo} deve ser uma lista"]
    orfaos = [str(x) for x in dados.get("orfaos") or []]
    fantasmas = [str(x) for x in dados.get("fantasmas") or []]
    if orfaos:
        erros.append(f"rastreio: {len(orfaos)} exemplos sem teste: {', '.join(orfaos)}")
    if fantasmas:
        erros.append(f"rastreio: {len(fantasmas)} testes sem exemplo: {', '.join(fantasmas)}")
    if dados.get("ok") is not True and not erros:
        erros.append("rastreio: verificador reprovou (ok falso)")
    return erros
