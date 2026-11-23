"""Ficha de projeto: uma pasta de Markdown por projeto, com documentação mínima, registros de
auditoria por etapa e processos humanos. Este módulo lê, valida e cria fichas; nunca reescreve uma.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

PORTES = ("pequeno", "medio", "grande")
ESTADOS = ("ativo", "pausado", "encerrado")
ETAPAS = ("descoberta", "desenho", "construcao", "lancamento", "operacao")
VEREDITOS = ("verde", "ambar", "vermelho")
STATUS_ADR = ("proposto", "aceito", "substituido")
TIPOS_PROCESSO = ("pop", "runbook", "playbook")
OBRIGATORIAS: Dict[str, Tuple[int, ...]] = {
    "pequeno": (0, 1, 3, 4),
    "medio": (0, 1, 2, 3, 4, 5, 6, 8),
    "grande": tuple(range(11)),
}
ARQUIVOS: Dict[int, str] = {
    0: "ficha.md", 1: "01-visao.md", 2: "02-especificacao.md", 3: "03-arquitetura.md", 4: "04-decisoes",
    5: "05-prontidao.md", 6: "06-auditorias", 7: "07-operacao.md", 8: "08-processos",
    9: "09-privacidade.md", 10: "10-execucao.md",
}
CATEGORIAS_PRONTIDAO = ("arquitetura", "maquinas", "volume", "confiabilidade", "monitoramento",
                        "seguranca", "automacao", "crescimento", "dependencias", "lancamento")
MARCADOR = "<!-- preencher -->"

_PASTAS = (4, 6, 8)
_FRENTE = re.compile(r"\A---\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
_OPCOES = re.compile(r"^## Opções consideradas[ \t]*$", re.M)
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class FichaRecusada(ValueError):
    """Pedido de criação que não pode ser atendido."""


@dataclass
class SecaoResultado:
    numero: int
    situacao: str  # "ok", "nao_se_aplica" ou "problema"
    problemas: List[str] = field(default_factory=list)


@dataclass
class FichaResultado:
    slug: str
    secoes: List[SecaoResultado] = field(default_factory=list)
    problemas: List[str] = field(default_factory=list)
    situacao: str = "sem auditoria"

    @property
    def valida(self) -> bool:
        return not self.problemas and all(s.situacao != "problema" for s in self.secoes)


def _ler(caminho: Path) -> Tuple[Optional[Dict[str, Any]], str, Optional[str]]:
    try:
        texto = caminho.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError) as erro:
        return None, "", f"não foi possível ler ({type(erro).__name__})"
    achado = _FRENTE.match(texto)
    if not achado:
        return None, texto, "sem bloco de campos (--- no começo do arquivo)"
    try:
        dados = yaml.safe_load(achado.group(1))
    except (yaml.YAMLError, ValueError, RecursionError) as erro:
        return None, texto, f"bloco de campos malformado ({type(erro).__name__})"
    if not isinstance(dados, dict):
        return None, texto, "bloco de campos não é um mapa de chave e valor"
    return dados, texto[achado.end():], None


def _texto(valor: Any) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def _como_data(valor: Any) -> Optional[date]:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor.strip())
        except ValueError:
            return None
    return None


def _exigir(dados: Dict[str, Any], campos: Tuple[str, ...], nome: str, problemas: List[str]) -> None:
    for campo in campos:
        valor = dados.get(campo)
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            problemas.append(f"{nome}: campo '{campo}' ausente ou vazio")


def _lista(dados: Dict[str, Any], campo: str, aceitos: Tuple[str, ...], nome: str, problemas: List[str]) -> None:
    valor = dados.get(campo)
    if valor is not None and valor not in aceitos:
        problemas.append(f"{nome}: campo '{campo}' vale '{valor}', aceitos: {', '.join(aceitos)}")


def _datas(dados: Dict[str, Any], campos: Tuple[str, ...], nome: str, problemas: List[str]) -> None:
    for campo in campos:
        if dados.get(campo) is not None and _como_data(dados[campo]) is None:
            problemas.append(f"{nome}: campo '{campo}' não é uma data AAAA-MM-DD")


def _evidencia(valor: Any, raiz: Path) -> Optional[str]:
    texto = _texto(valor)
    if not texto:
        return "evidencia ausente ou vazia"
    if texto.startswith(("http://", "https://")):
        return None
    base = raiz.resolve()
    alvo = (base / texto).resolve()
    if alvo != base and base not in alvo.parents:
        return f"evidencia '{texto}' aponta para fora do repositório"
    if not alvo.exists():
        return f"evidencia '{texto}' não existe"
    return None


def _itens(pasta: Path, padrao: str) -> List[Path]:
    return sorted(p for p in pasta.glob(padrao) if p.is_file() and p.name != "_secao.md")


def _adrs(pasta: Path, problemas: List[str]) -> None:
    arquivos = _itens(pasta, "ADR-*.md")
    if not arquivos:
        problemas.append(f"{pasta.name}: nenhum ADR (arquivo ADR-*.md)")
    for arquivo in arquivos:
        dados, corpo, erro = _ler(arquivo)
        if erro:
            problemas.append(f"{arquivo.name}: {erro}")
            continue
        _exigir(dados, ("id", "status", "data"), arquivo.name, problemas)
        _lista(dados, "status", STATUS_ADR, arquivo.name, problemas)
        _datas(dados, ("data",), arquivo.name, problemas)
        if "externo" in dados:
            if not _texto(dados["externo"]).startswith(("http://", "https://")):
                problemas.append(f"{arquivo.name}: campo 'externo' precisa ser uma URL http ou https")
        elif not _OPCOES.search(corpo):
            problemas.append(f"{arquivo.name}: falta o título '## Opções consideradas'")


def _prontidao(dados: Dict[str, Any], nome: str, raiz: Path, problemas: List[str]) -> None:
    categorias = dados.get("categorias")
    if not isinstance(categorias, dict):
        problemas.append(f"{nome}: campo 'categorias' ausente ou não é um mapa")
        return
    for chave in CATEGORIAS_PRONTIDAO:
        item = categorias.get(chave)
        if not isinstance(item, dict):
            problemas.append(f"{nome}: categoria '{chave}' ausente")
        elif _texto(item.get("motivo")):
            continue
        elif "evidencia" not in item:
            problemas.append(f"{nome}: categoria '{chave}' sem evidencia nem motivo")
        else:
            erro = _evidencia(item["evidencia"], raiz)
            if erro:
                problemas.append(f"{nome}: categoria '{chave}': {erro}")


def _auditorias(pasta: Path, raiz: Path, problemas: List[str]) -> List[Tuple[str, date, str]]:
    arquivos = _itens(pasta, "*.md")
    if not arquivos:
        problemas.append(f"{pasta.name}: nenhuma auditoria registrada")
    validas = []
    for arquivo in arquivos:
        antes = len(problemas)
        dados, _, erro = _ler(arquivo)
        if erro:
            problemas.append(f"{arquivo.name}: {erro}")
            continue
        _exigir(dados, ("etapa", "data", "veredito", "criterio"), arquivo.name, problemas)
        _lista(dados, "etapa", ETAPAS, arquivo.name, problemas)
        _lista(dados, "veredito", VEREDITOS, arquivo.name, problemas)
        erro = _evidencia(dados.get("evidencia"), raiz)
        if erro:
            problemas.append(f"{arquivo.name}: {erro}")
        if dados.get("veredito") in ("ambar", "vermelho"):
            _exigir(dados, ("pendencia", "prazo", "dono"), arquivo.name, problemas)
        _datas(dados, ("data", "prazo"), arquivo.name, problemas)
        if len(problemas) == antes:
            validas.append((dados["etapa"], _como_data(dados["data"]), dados["veredito"]))
    return validas


def _processos(pasta: Path, problemas: List[str]) -> None:
    arquivos = _itens(pasta, "*.md")
    if not arquivos:
        problemas.append(f"{pasta.name}: nenhum processo registrado")
    for arquivo in arquivos:
        dados, _, erro = _ler(arquivo)
        if erro:
            problemas.append(f"{arquivo.name}: {erro}")
            continue
        _exigir(dados, ("tipo", "dono", "revisado_em"), arquivo.name, problemas)
        _lista(dados, "tipo", TIPOS_PROCESSO, arquivo.name, problemas)
        _datas(dados, ("revisado_em",), arquivo.name, problemas)


def _marcadores(arquivos: List[Path], problemas: List[str]) -> None:
    for arquivo in arquivos:
        try:
            texto = arquivo.read_bytes().decode("utf-8-sig", errors="replace")
        except OSError:
            continue
        if MARCADOR in texto:
            problemas.append(f"{arquivo.name}: texto de modelo não preenchido")


def _situacao(auditorias: List[Tuple[str, date, str]]) -> str:
    ultima: Dict[str, Tuple[date, str]] = {}
    for etapa, quando, veredito in auditorias:
        if etapa not in ultima or quando >= ultima[etapa][0]:
            ultima[etapa] = (quando, veredito)
    if not ultima:
        return "sem auditoria"
    return max((v for _, v in ultima.values()), key=VEREDITOS.index)


def _secao(numero: int, pasta: Path, raiz: Path, auditorias: List[Tuple[str, date, str]]) -> SecaoResultado:
    alvo = pasta / ARQUIVOS[numero]
    indice = alvo / "_secao.md" if numero in _PASTAS else alvo
    problemas: List[str] = []
    dados, corpo, erro = _ler(indice)
    arquivos = sorted(p for p in alvo.rglob("*.md")) if numero in _PASTAS else [alvo]
    _marcadores(arquivos, problemas)
    if erro:
        return SecaoResultado(numero, "problema", problemas + [f"{ARQUIVOS[numero]}: {erro}"])
    nome = ARQUIVOS[numero]
    _exigir(dados, ("secao", "origem", "aplica"), nome, problemas)
    if dados.get("secao") is not None and dados.get("secao") != numero:
        problemas.append(f"{nome}: campo 'secao' vale {dados.get('secao')}, esperado {numero}")
    _lista(dados, "aplica", ("sim", "nao"), nome, problemas)
    if dados.get("aplica") == "nao":
        if not _texto(dados.get("motivo")):
            problemas.append(f"{nome}: 'aplica: nao' exige o campo 'motivo'")
        return SecaoResultado(numero, "problema" if problemas else "nao_se_aplica", problemas)
    if numero == 3 and "```mermaid" not in corpo:
        problemas.append(f"{nome}: falta ao menos um diagrama em bloco mermaid")
    elif numero == 4:
        _adrs(alvo, problemas)
    elif numero == 5:
        _prontidao(dados, nome, raiz, problemas)
    elif numero == 6:
        auditorias.extend(_auditorias(alvo, raiz, problemas))
    elif numero == 8:
        _processos(alvo, problemas)
    return SecaoResultado(numero, "problema" if problemas else "ok", problemas)


def validar(pasta: Path, raiz: Path) -> FichaResultado:
    """Valida a ficha em `pasta`; `raiz` é a raiz do repositório, base dos caminhos de evidência."""
    resultado = FichaResultado(slug=pasta.name)
    principal = pasta / ARQUIVOS[0]
    if not principal.is_file():
        resultado.problemas.append(f"{pasta.name}: ficha.md ausente")
        return resultado
    problemas: List[str] = []
    _marcadores([principal], problemas)
    dados, _, erro = _ler(principal)
    if erro:
        resultado.secoes.append(SecaoResultado(0, "problema", problemas + [f"ficha.md: {erro}"]))
        return resultado
    _exigir(dados, ("slug", "nome", "porte", "estado", "repositorio", "data", "origem"), "ficha.md", problemas)
    _lista(dados, "porte", PORTES, "ficha.md", problemas)
    _lista(dados, "estado", ESTADOS, "ficha.md", problemas)
    _datas(dados, ("data",), "ficha.md", problemas)
    if dados.get("slug") is not None and dados.get("slug") != pasta.name:
        problemas.append(f"ficha.md: campo 'slug' vale '{dados.get('slug')}', mas a pasta é '{pasta.name}'")
    resultado.secoes.append(SecaoResultado(0, "problema" if problemas else "ok", problemas))
    porte = dados.get("porte")
    obrigatorias = OBRIGATORIAS.get(porte, (0,)) if isinstance(porte, str) else (0,)
    auditorias: List[Tuple[str, date, str]] = []
    for numero in range(1, 11):
        if (pasta / ARQUIVOS[numero]).exists():
            resultado.secoes.append(_secao(numero, pasta, raiz, auditorias))
        elif numero in obrigatorias:
            resultado.secoes.append(SecaoResultado(
                numero, "problema", [f"{ARQUIVOS[numero]}: seção obrigatória para o porte e ausente"]))
    resultado.situacao = _situacao(auditorias)
    return resultado


def validar_todas(fichas_dir: Path, raiz: Path) -> List[FichaResultado]:
    if not fichas_dir.is_dir():
        return []
    pastas = sorted(p for p in fichas_dir.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))
    return [validar(p, raiz) for p in pastas]


def criar(fichas_dir: Path, slug: str, nome: str, porte: str, hoje: date) -> Path:
    """Cria `fichas_dir/slug` com os modelos das seções obrigatórias para o porte."""
    if not isinstance(slug, str) or not _SLUG.match(slug):
        raise FichaRecusada("slug inválido: use letras minúsculas, números e hífen, começando por letra ou número")
    if porte not in PORTES:
        raise FichaRecusada(f"porte inválido: aceitos {', '.join(PORTES)}")
    modelos = fichas_dir / "_modelos"
    origens = [modelos / ARQUIVOS[n] / "_secao.md" if n in _PASTAS else modelos / ARQUIVOS[n] for n in OBRIGATORIAS[porte]]
    faltando = [o.name for o in origens if not o.is_file()]
    if faltando:
        raise FichaRecusada(f"modelos ausentes em {modelos}: {', '.join(faltando)}")
    destino = fichas_dir / slug
    if destino.exists():
        raise FichaRecusada(f"já existe uma ficha em {destino}")
    # json.dumps gera um texto entre aspas que também é YAML válido, mesmo com ':' ou aspas no nome
    trocas = {"{{slug}}": slug, "{{nome}}": json.dumps(nome, ensure_ascii=False), "{{titulo}}": nome,
              "{{porte}}": porte, "{{data}}": hoje.isoformat()}
    for origem in origens:
        texto = origem.read_text(encoding="utf-8")
        for marca, valor in trocas.items():
            texto = texto.replace(marca, valor)
        alvo = destino / origem.relative_to(modelos)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(texto, encoding="utf-8", newline="\n")
    return destino
