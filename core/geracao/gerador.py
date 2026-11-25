"""Gerador de artefatos por fase: plano -> contexto -> IA -> render -> escrita -> card.

Nunca aprova, nunca dá aval, nunca sobrescreve: páginas nascem ``proposta`` e a
triagem nasce sem aprovador. Cliente de IA, busca e executor do rastreio são injetados.
"""
from __future__ import annotations

import copy
import re
import threading
from collections.abc import Callable
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

import yaml

from core.demand_lifecycle import DemandNotFoundError
from core.docs_registry import (
    REGRA_REL_RE, RULE_ID_RE, DocsRegistryError, exemplos_da_regra, page_status, pagina_path,
    regras_aprovadas,
)
from core.geracao.contexto import montar
from core.geracao.escrita import escrever
from core.geracao.plano import ItemDeGeracao, plano
from core.geracao.render import render_pagina, render_regras
from core.protocol import registry
from core.triagem import TRIAGEM_TEMPLATE

# artefato -> trace_id da etapa que o redige; só durante executar(traces=...).
_traces_da_execucao: ContextVar[dict | None] = ContextVar("traces_da_execucao", default=None)

PROVEDOR = "provedor"
ORCAMENTO = "orçamento"
RASCUNHO_INVALIDO = "rascunho inválido"
PAGINA_INVALIDA = "página inválida"
DOCS_REPO = "docs_repo"
RASTREIO = "rastreio"

_PRODUTO_VALIDO = re.compile(r"^[a-z0-9-]+$")

# Artefatos com página no repositório de documentação (o que ``refazer`` pode regerar).
_PAGINAS = ("visao", "cronograma", "historias", "casos_de_uso", "rnf", "telas", "regras")


class _Falha(Exception):
    def __init__(self, motivo: str, detalhe: str = "", **extra):
        super().__init__(motivo)
        self.motivo = f"{motivo}: {detalhe}" if detalhe else motivo
        self.extra = extra


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _registro(estado: str, caminho=None, motivo: str = "", custo_usd: float = 0.0,
              trace_id: str = "", contexto: str | None = None) -> dict:
    return {"estado": estado, "caminho": caminho, "motivo": motivo, "custo_usd": custo_usd,
            "trace_id": trace_id, "em": _agora(), "contexto": contexto}


def _frontmatter(mdx: str) -> dict:
    partes = mdx.split("---\n", 2)
    dados = yaml.safe_load(partes[1]) if len(partes) == 3 else None
    return dados if isinstance(dados, dict) else {}


def _erros_regra(rel: str, mdx: str, produto: str) -> list[str]:
    """Light check of a rendered rule page (the full one is the docs repo's validator)."""
    erros = []
    if not REGRA_REL_RE.match(rel) or not rel.startswith(f"{produto}/regras/"):
        erros.append(f"caminho de regra inválido: {rel}")
    fm = _frontmatter(mdx)
    rid = fm.get("id")
    if not (isinstance(rid, str) and RULE_ID_RE.match(rid)):
        erros.append(f"id de regra inválido: {rid!r}")
    if fm.get("status") != "proposta":
        erros.append(f"regra gerada fora de proposta: {fm.get('status')!r}")
    return erros


def _rascunho_da_ia(triagem) -> bool:
    """Triage drafted by the model and not approved yet: the only kind *refazer* replaces."""
    return (isinstance(triagem, dict) and triagem.get("sugerida_por") == "ia"
            and not str(triagem.get("aprovada_por") or "").strip())


class GeradorDeArtefatos:
    def __init__(self, svc, cliente_ia: Callable[[str, str], dict], busca,
                 docs_root: Callable[[], Path],
                 executar_rastreio: Callable[[Path, str, str, Path], int],
                 testes_por_produto: dict[str, str], runtime: Path,
                 produtos: dict | None = None, guia_triagem: str = ""):
        self._svc = svc
        self._cliente_ia = cliente_ia
        self._busca = busca
        self._docs_root = docs_root
        self._executar_rastreio = executar_rastreio
        self._testes = dict(testes_por_produto or {})
        self._produtos = dict(produtos or {})  # slug -> Produto, vai ao rascunho da triagem
        self._guia_triagem = guia_triagem or ""  # perguntas e trilhas do perfil, idem
        self._runtime = Path(runtime)
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guarda = threading.Lock()

    # -- lock -----------------------------------------------------------------

    def _lock(self, demanda_id: str) -> threading.Lock:
        with self._locks_guarda:
            return self._locks.setdefault(demanda_id, threading.Lock())

    # -- entrada --------------------------------------------------------------

    def executar(self, demanda_id: str, refazer: bool = False,
                 traces: dict[str, str] | None = None) -> dict[str, dict]:
        """*traces* (artefato → trace_id) liga cada chamada de modelo à etapa que a pediu."""
        lock = self._lock(demanda_id)
        if not lock.acquire(blocking=False):
            return {}
        token = _traces_da_execucao.set(dict(traces) if traces else None)
        try:
            return self._executar(demanda_id, refazer)
        finally:
            _traces_da_execucao.reset(token)
            lock.release()

    def _executar(self, demanda_id: str, refazer: bool) -> dict[str, dict]:
        demanda = self._svc.get_demand(demanda_id)
        if demanda is None:
            raise DemandNotFoundError(f"Demand {demanda_id} not found")
        try:
            itens = plano(self._para_plano(demanda, refazer))
        except ValueError as exc:
            resultados = {"triagem": _registro("falhou", motivo=f"{RASCUNHO_INVALIDO}: {exc}")}
            self._gravar_estado(demanda_id, resultados)
            return resultados
        resultados: dict[str, dict] = {}
        for item in itens:
            try:
                registro, demanda = self._gerar(demanda, item, refazer)
            except _Falha as f:
                registro = _registro("falhou", motivo=f.motivo, **f.extra)
            except (DocsRegistryError, OSError) as exc:
                registro = _registro("falhou", motivo=f"{DOCS_REPO}: {exc}")
            resultados[item.artefato] = registro
        if resultados:
            self._gravar_estado(demanda_id, resultados)
        return resultados

    @staticmethod
    def _para_plano(demanda, refazer: bool):
        """With *refazer*, the pages already on the card enter the plan again.

        So does a triage that is still the model's unapproved draft (never one a person wrote
        or approved).
        """
        if not refazer:
            return demanda
        vista = copy.copy(demanda)
        vista.artefacts = {k: v for k, v in (demanda.artefacts or {}).items() if k not in _PAGINAS}
        if _rascunho_da_ia(vista.artefacts.get("triagem")):
            del vista.artefacts["triagem"]
        return vista

    def _gravar_estado(self, demanda_id: str, resultados: dict) -> None:
        atual = (self._svc.get_demand(demanda_id).artefacts or {}).get("geracao")
        geracao = dict(atual) if isinstance(atual, dict) else {}
        geracao.update(resultados)
        self._svc.update_artefact(demanda_id, "geracao", geracao)

    # -- por item -------------------------------------------------------------

    def _gerar(self, demanda, item: ItemDeGeracao, refazer: bool):
        if item.artefato == "triagem":
            return self._triagem(demanda, item, refazer)
        if item.artefato == "plano_de_testes":
            return self._plano_de_testes(demanda)
        if item.artefato == "rastreio":
            return self._rastreio(demanda)
        root = self._docs_root()
        if item.artefato == "regras":
            return self._regras(demanda, item, root, refazer)
        return self._pagina(demanda, item, root, refazer)

    def _rascunho(self, demanda, item: ItemDeGeracao, ler_pagina) -> tuple[dict, dict]:
        """Ask the model for the template's JSON; returns (payload, meta)."""
        texto, com_vault = montar(demanda, item, self._busca, ler_pagina, self._produtos,
                                  self._guia_triagem)
        meta = {"contexto": "vault" if com_vault else "sem vault"}
        try:
            traces = _traces_da_execucao.get()
            trace_id = traces.get(item.artefato) if traces else None
            if trace_id:
                env = self._cliente_ia(item.template, texto, trace_id=trace_id)
            else:
                env = self._cliente_ia(item.template, texto)
        except Exception as exc:  # provider down, timeout, client bug
            raise _Falha(PROVEDOR, str(exc), **meta) from exc
        env = env if isinstance(env, dict) else {}
        custo = env.get("cost") if isinstance(env.get("cost"), dict) else {}
        meta["custo_usd"] = float(custo.get("actual_usd") or 0.0)
        meta["trace_id"] = str(env.get("trace_id") or "")
        status = env.get("status")
        if status == "budget_exceeded":
            raise _Falha(ORCAMENTO, str(env.get("reason") or ""), **meta)
        if status == "invalid":
            raise _Falha(RASCUNHO_INVALIDO, str(env.get("reason") or ""), **meta)
        if status != "ok":
            raise _Falha(PROVEDOR, str(env.get("reason") or status or ""), **meta)
        payload = env.get("payload")
        if not isinstance(payload, dict):
            raise _Falha(RASCUNHO_INVALIDO, "payload ausente", **meta)
        erros = registry.validate(item.template, payload)
        if erros:
            raise _Falha(RASCUNHO_INVALIDO, "; ".join(erros), **meta)
        return payload, meta

    def _triagem(self, demanda, item, refazer: bool = False):
        payload, meta = self._rascunho(demanda, item, lambda rel: None)
        # The model's track is a suggestion: ``trilha`` stays empty for the manager's
        # choice, written together with ``aprovada_por`` (no downgrade needed).
        triagem = {**TRIAGEM_TEMPLATE, **payload, "trilha": "",
                   "trilha_sugerida": payload.get("trilha", ""),
                   "aprovada_por": "", "aprovada_em": "", "rebaixamentos": [], "sugerida_por": "ia"}
        atual = self._svc.get_demand(demanda.id)
        existente = (atual.artefacts or {}).get("triagem")
        if existente is not None and not (refazer and _rascunho_da_ia(existente)):
            return _registro("pulado", motivo="triagem já existe", **meta), atual
        try:
            demanda = self._svc.update_artefact(demanda.id, "triagem", triagem)
        except ValueError as exc:
            return _registro("pulado", motivo=str(exc), **meta), atual
        return _registro("gerado", **meta), demanda

    @staticmethod
    def _leitor(root: Path):
        def ler(rel: str):
            try:
                return pagina_path(root, rel).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError, DocsRegistryError):
                return None
        return ler

    @staticmethod
    def _situacao(root: Path, rel: str, refazer: bool) -> str:
        """``livre`` (absent), ``substituir`` (``proposta`` under *refazer*) or ``ocupada``."""
        if not pagina_path(root, rel).exists():
            return "livre"
        if not refazer:
            return "ocupada"
        try:
            status = page_status(root, rel).get("status")
        except DocsRegistryError:
            return "ocupada"  # unreadable page is not ours to replace
        return "substituir" if status == "proposta" else "ocupada"

    def _escrever(self, root: Path, rel: str, mdx: str, refazer: bool) -> str:
        situacao = self._situacao(root, rel, refazer)
        if situacao == "ocupada":
            return "pulado"
        if situacao == "substituir":
            pagina_path(root, rel).unlink()
        return escrever(root, rel, mdx)

    def _vincular(self, demanda, artefato: str, valor):
        """Put the page on the card only when the card has nothing there yet."""
        if (demanda.artefacts or {}).get(artefato):
            return demanda
        return self._svc.update_artefact(demanda.id, artefato, valor)

    def _pagina(self, demanda, item, root, refazer):
        rel = item.caminho
        valor = self._valor_card(item.artefato, rel)
        no_card = (demanda.artefacts or {}).get(item.artefato)
        if refazer and isinstance(no_card, dict) and str(no_card.get("aprovada_por") or "").strip():
            return _registro("pulado", caminho=rel, motivo="visão já aprovada"), demanda
        if self._situacao(root, rel, refazer) == "ocupada":
            return _registro("pulado", caminho=rel), self._vincular(demanda, item.artefato, valor)
        payload, meta = self._rascunho(demanda, item, self._leitor(root))
        try:
            mdx = render_pagina(item.template, payload, demanda)
        except (KeyError, TypeError, ValueError) as exc:
            raise _Falha(PAGINA_INVALIDA, str(exc), **meta) from exc
        try:
            estado = self._escrever(root, rel, mdx, refazer)
        except (DocsRegistryError, OSError) as exc:
            raise _Falha(DOCS_REPO, str(exc), **meta) from exc
        return _registro(estado, caminho=rel, **meta), self._vincular(demanda, item.artefato, valor)

    @staticmethod
    def _valor_card(artefato: str, rel: str):
        return {"pagina": rel, "aprovada_por": ""} if artefato == "visao" else rel

    def _regras(self, demanda, item, root, refazer):
        produto = (demanda.artefacts or {}).get("triagem", {}).get("produto")
        if not (isinstance(produto, str) and _PRODUTO_VALIDO.fullmatch(produto)):
            raise _Falha(RASCUNHO_INVALIDO, f"triagem sem produto válido: {produto!r}")
        anteriores = (demanda.artefacts or {}).get("regras")
        anteriores = [r for r in anteriores if isinstance(r, str)] if isinstance(anteriores, list) else []
        payload, meta = self._rascunho(demanda, item, self._leitor(root))
        try:
            paginas = render_regras(payload, produto)
        except (KeyError, TypeError, ValueError) as exc:
            raise _Falha(PAGINA_INVALIDA, str(exc), **meta) from exc
        if not paginas:
            raise _Falha(PAGINA_INVALIDA, "nenhuma regra com slug válido", **meta)
        erros = [e for rel, mdx in paginas for e in _erros_regra(rel, mdx, produto)]
        if erros:
            raise _Falha(PAGINA_INVALIDA, "; ".join(erros), **meta)
        # A rule page is product-level: only what this run wrote, or what this card
        # already held, is this demand's; anything else may carry someone else's approval.
        nossas, alheias, estados = [], [], []
        for rel, mdx in paginas:
            try:
                estado = self._escrever(root, rel, mdx, refazer and rel in anteriores)
            except (DocsRegistryError, OSError) as exc:
                raise _Falha(DOCS_REPO, str(exc), **meta) from exc
            estados.append(estado)
            if estado == "gerado" or rel in anteriores:
                nossas.append(rel)
            else:
                alheias.append(rel)
        card = anteriores + [r for r in nossas if r not in anteriores]
        if card != anteriores:
            demanda = self._svc.update_artefact(demanda.id, "regras", card)
        motivo = "; ".join(f"regra já existe: {rel}" for rel in alheias)
        estado = "gerado" if "gerado" in estados else "pulado"
        return _registro(estado, caminho=nossas, motivo=motivo, **meta), demanda

    def _plano_de_testes(self, demanda):
        root = self._docs_root()
        rels = (demanda.artefacts or {}).get("regras")
        rels = [r for r in rels if isinstance(r, str)] if isinstance(rels, list) else []
        existentes = [r for r in rels if pagina_path(root, r).is_file()]
        nao = set(regras_aprovadas(root, existentes))
        casos = []
        for rel in existentes:
            if rel in nao:
                continue
            casos += [{**e, "regra": rel} for e in exemplos_da_regra(root, rel)]
        if not casos:
            return _registro("pulado", motivo="nenhuma regra aprovada com exemplos"), demanda
        demanda = self._svc.update_artefact(demanda.id, "plano_de_testes", casos)
        return _registro("gerado"), demanda

    def _rastreio(self, demanda):
        root = self._docs_root()
        produto = (demanda.artefacts or {}).get("triagem", {}).get("produto")
        testes = self._testes.get(produto) if isinstance(produto, str) else None
        if not testes:
            raise _Falha(RASTREIO, f"sem testes configurados para o produto {produto!r}")
        saida = self._runtime / ".rastreio" / f"{demanda.id}.json"
        try:
            saida.parent.mkdir(parents=True, exist_ok=True)
            # A previous result must not stand in for a rerun that fails.
            saida.unlink(missing_ok=True)
        except OSError as exc:
            raise _Falha(RASTREIO, f"saída inacessível: {exc}") from exc
        try:
            codigo = self._executar_rastreio(root, produto, testes, saida)
        except Exception as exc:
            raise _Falha(RASTREIO, f"verificador não rodou: {exc}") from exc
        if codigo not in (0, 1):
            raise _Falha(RASTREIO, f"verificador saiu com código {codigo}")
        if not saida.is_file():
            raise _Falha(RASTREIO, f"verificador não gravou o arquivo {saida}")
        demanda = self._svc.update_artefact(demanda.id, "rastreio", str(saida))
        return _registro("gerado", caminho=str(saida)), demanda
