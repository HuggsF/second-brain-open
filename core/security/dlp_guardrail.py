"""DLP Guardrail Engine: masking de PII pré-LLM e detecção de Prompt Injection.

Sprint 1 (Gap G1 — Plano de Convergência KIOSK AI-OS + MoE):
Atua ANTES do LLM, interceptando o texto de entrada para:
  1. Mascarar dados sensíveis (CPF, CNPJ, cartões de crédito, chaves de API)
     com tokens reversíveis [PII_CPF_01], [PII_CARD_01], etc.
  2. Calcular um score heurístico de Prompt Injection (0.0–1.0) com base em
     padrões conhecidos de jailbreak e injeção indireta.

Não requer dependências externas — usa apenas regex da stdlib.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ─── Padrões de PII ───────────────────────────────────────────────────────────

# CPF: 000.000.000-00 ou 00000000000
_CPF_PATTERN = re.compile(r"\b(\d{3}[.\s]?\d{3}[.\s]?\d{3}[-.\s]?\d{2})\b")

# CNPJ: 00.000.000/0000-00 ou 00000000000000
_CNPJ_PATTERN = re.compile(r"\b(\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\\]?\d{4}[-.\s]?\d{2})\b")

# Cartão de crédito: 4 grupos de 4 dígitos (Visa, Mastercard, etc.)
_CARD_PATTERN = re.compile(r"\b(\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4})\b")

# Chaves de API / Tokens (strings longas alfanuméricas com prefixos comuns)
_API_KEY_PATTERN = re.compile(
    r"\b(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{36,}|xoxb-[a-zA-Z0-9\-]{24,}|"
    r"AKIA[A-Z0-9]{16}|AIza[a-zA-Z0-9_-]{35})\b"
)

# E-mail
_EMAIL_PATTERN = re.compile(r"\b([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,})\b")

# Telefone BR: (11) 99999-9999 ou +55 11 999999999
_PHONE_PATTERN = re.compile(
    r"(?:\+55\s?)?\(?\d{2}\)?\s?\d{4,5}[-.\s]?\d{4}\b"
)


# Mapa tipo → (regex, prefixo do token)
_PII_RULES: List[Tuple[str, re.Pattern, str]] = [
    ("CPF", _CPF_PATTERN, "PII_CPF"),
    ("CNPJ", _CNPJ_PATTERN, "PII_CNPJ"),
    ("CARD", _CARD_PATTERN, "PII_CARD"),
    ("API_KEY", _API_KEY_PATTERN, "PII_APIKEY"),
    ("EMAIL", _EMAIL_PATTERN, "PII_EMAIL"),
    ("PHONE", _PHONE_PATTERN, "PII_PHONE"),
]


# ─── Padrões de Prompt Injection ──────────────────────────────────────────────

_INJECTION_PATTERNS: List[Tuple[re.Pattern, float]] = [
    # Tentativas diretas de override de system prompt
    (re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)"), 0.95),
    (re.compile(r"(?i)disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)"), 0.95),
    (re.compile(r"(?i)forget\s+(everything|all)\s+(you\s+)?(were\s+told|know|learned)"), 0.90),

    # System prompt extraction
    (re.compile(r"(?i)(print|show|reveal|display|output|repeat)\s+(your\s+)?(system\s+prompt|instructions?|rules?)"), 0.85),
    (re.compile(r"(?i)what\s+(are|were)\s+your\s+(initial|system|original)\s+(instructions?|prompts?|rules?)"), 0.80),

    # Role play / DAN jailbreaks
    (re.compile(r"(?i)you\s+are\s+now\s+(DAN|evil|unrestricted|uncensored|jailbr[oe]ken)"), 0.90),
    (re.compile(r"(?i)pretend\s+(you\s+)?(are|to\s+be)\s+(a|an)\s+(evil|unrestricted|hacker)"), 0.85),
    (re.compile(r"(?i)act\s+as\s+if\s+(you\s+)?ha(ve|d)\s+no\s+(restrictions?|limits?|rules?)"), 0.85),

    # Indirect injection / data exfiltration
    (re.compile(r"(?i)(fetch|load|read|access|open)\s+(the\s+)?(url|link|website|http)"), 0.60),
    (re.compile(r"(?i)(send|transmit|exfiltrate|post)\s+(data|info|information|results?)\s+to"), 0.75),

    # Delimiter injection (tentativa de fechar/abrir blocos)
    (re.compile(r"```\s*(system|assistant|user)\s*\n"), 0.70),
    (re.compile(r"<\|?(system|endoftext|im_start|im_end)\|?>"), 0.80),

    # Portuguese variants
    (re.compile(r"(?i)ignore\s+(todas?\s+)?(as\s+)?(instruções|regras|ordens)\s+(anteriores|prévias)"), 0.95),
    (re.compile(r"(?i)esquec[aê]\s+(tudo|todas?\s+as\s+regras)"), 0.90),
    (re.compile(r"(?i)(mostre|revele|imprima)\s+(o\s+)?(seu\s+)?(prompt\s+de\s+sistema|system\s+prompt)"), 0.85),
]

_ZERO_WIDTH_RE = re.compile(r'[\u200b-\u200d\u200e\u200f\uFEFF\u00AD]')

def _strip_zero_width(text: str) -> str:
    """Remove zero-width characters que podem ser usados para evasão."""
    return _ZERO_WIDTH_RE.sub('', text)

# Common Cyrillic/Greek/etc confusable homoglyphs used in injection evasion
_CONFUSABLES = str.maketrans({
    '\u0430': 'a', '\u0435': 'e', '\u043e': 'o', '\u0440': 'p',  # Cyrillic
    '\u0441': 'c', '\u0443': 'y', '\u0456': 'i', '\u0455': 's',
    '\u04bb': 'h', '\u0501': 'd', '\u051b': 'q',
    '\u0410': 'A', '\u0415': 'E', '\u041e': 'O', '\u0420': 'P',
    '\u0421': 'C', '\u0423': 'Y', '\u0406': 'I', '\u0405': 'S',
    '\u0397': 'H', '\u0392': 'B', '\u039a': 'K', '\u039c': 'M',  # Greek
    '\u039d': 'N', '\u03a1': 'P', '\u03a4': 'T', '\u03a7': 'X',
})

def _deconfuse(text: str) -> str:
    """Replace common confusable homoglyphs with their ASCII equivalents."""
    return text.translate(_CONFUSABLES)


@dataclass
class PIIMatch:
    """Um match de PII encontrado no texto."""
    pii_type: str
    original: str
    token: str
    start: int
    end: int


@dataclass
class DLPResult:
    """Resultado da inspeção DLP."""
    original_text: str
    redacted_text: str
    pii_matches: List[PIIMatch] = field(default_factory=list)
    injection_score: float = 0.0
    injection_patterns_matched: List[str] = field(default_factory=list)
    is_blocked: bool = False
    block_reason: Optional[str] = None

    @property
    def has_pii(self) -> bool:
        return len(self.pii_matches) > 0

    @property
    def pii_count(self) -> int:
        return len(self.pii_matches)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_pii": self.has_pii,
            "pii_count": self.pii_count,
            "pii_types": list({m.pii_type for m in self.pii_matches}),
            "injection_score": round(self.injection_score, 3),
            "injection_patterns_matched": self.injection_patterns_matched,
            "is_blocked": self.is_blocked,
            "block_reason": self.block_reason,
        }


class DLPGuardrailEngine:
    """Motor de DLP que mascara PII e detecta prompt injection.

    Args:
        injection_threshold: Score mínimo para considerar a entrada como
            prompt injection e bloquear. Default: 0.80.
        mask_pii: Se True, substitui PII por tokens reversíveis. Default: True.
    """

    def __init__(
        self,
        injection_threshold: float = 0.80,
        mask_pii: bool = True,
    ):
        self.injection_threshold = injection_threshold
        self.mask_pii = mask_pii

    def inspect(self, text: str) -> DLPResult:
        """Inspeciona o texto e retorna resultado com PII mascarada e score de injection."""
        if not isinstance(text, str) or not text.strip():
            return DLPResult(
                original_text=text or "",
                redacted_text=text or "",
            )

        # 1. Detectar Prompt Injection
        injection_score, matched_patterns = self._detect_injection(text)

        # 2. Mascarar PII
        redacted_text, pii_matches = self._mask_pii(text) if self.mask_pii else (text, [])

        # 3. Determinar se bloqueia
        is_blocked = injection_score >= self.injection_threshold
        block_reason = None
        if is_blocked:
            block_reason = (
                f"Prompt Injection detectado (score={injection_score:.2f}, "
                f"threshold={self.injection_threshold:.2f}). "
                f"Padrões: {', '.join(matched_patterns[:3])}"
            )

        return DLPResult(
            original_text=text,
            redacted_text=redacted_text,
            pii_matches=pii_matches,
            injection_score=injection_score,
            injection_patterns_matched=matched_patterns,
            is_blocked=is_blocked,
            block_reason=block_reason,
        )

    def _detect_injection(self, text: str) -> Tuple[float, List[str]]:
        """Calcula score de prompt injection (0.0–1.0) usando heurísticas regex.

        PD-OVR-002: Normaliza com NFKC e strip zero-width antes do scan.
        PII scan roda no texto original (não normalizado).
        """
        # Normalizar para detecção de evasão
        normalized = unicodedata.normalize("NFKC", text)
        normalized = _strip_zero_width(normalized)
        normalized = _deconfuse(normalized)

        max_score = 0.0
        matched = []

        for pattern, score in _INJECTION_PATTERNS:
            if pattern.search(normalized):
                matched.append(pattern.pattern[:60])
                max_score = max(max_score, score)

        return max_score, matched

    def _mask_pii(self, text: str) -> Tuple[str, List[PIIMatch]]:
        """Substitui PII por tokens reversíveis [PII_TYPE_NN]."""
        matches: List[PIIMatch] = []
        counters: Dict[str, int] = {}
        result = text

        for pii_type, pattern, token_prefix in _PII_RULES:
            for match in pattern.finditer(text):
                count = counters.get(pii_type, 0) + 1
                counters[pii_type] = count
                token = f"[{token_prefix}_{count:02d}]"
                matches.append(PIIMatch(
                    pii_type=pii_type,
                    original=match.group(),
                    token=token,
                    start=match.start(),
                    end=match.end(),
                ))

        # Substitui de trás para frente para manter índices consistentes
        for m in sorted(matches, key=lambda x: x.start, reverse=True):
            result = result[:m.start] + m.token + result[m.end:]

        return result, matches


def inspect_text(text: str, injection_threshold: float = 0.80) -> DLPResult:
    """Atalho funcional: inspeciona texto com configurações padrão."""
    return DLPGuardrailEngine(injection_threshold=injection_threshold).inspect(text)
