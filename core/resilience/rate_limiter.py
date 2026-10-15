"""Token Bucket Rate Limiter por Tool.

Sprint 3 (Gap G5 — Plano de Convergência KIOSK AI-OS + MoE):
Implementa rate limiting por ferramenta usando o algoritmo Token Bucket.
Cada tool tem um bucket com capacidade e taxa de recarga configuráveis.

Exemplo: run_safe_command com max_tokens=5, refill_rate=1/s permite
no máximo 5 chamadas em burst, depois 1 chamada por segundo.

Thread-safe via threading.Lock.
"""
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class BucketConfig:
    """Configuração de um token bucket."""
    max_tokens: int = 30         # Capacidade máxima do bucket
    refill_rate: float = 0.5     # Tokens adicionados por segundo
    initial_tokens: Optional[int] = None  # Se None, começa cheio

    def __post_init__(self):
        if self.initial_tokens is None:
            self.initial_tokens = self.max_tokens


# Configurações padrão por tool (derivadas da ontologia KIOSK)
DEFAULT_BUCKET_CONFIGS: Dict[str, BucketConfig] = {
    "search_knowledge_base": BucketConfig(max_tokens=30, refill_rate=1.0),   # 60/min
    "get_adr":               BucketConfig(max_tokens=20, refill_rate=0.5),   # 30/min
    "get_brain_status":      BucketConfig(max_tokens=10, refill_rate=0.2),   # 12/min
    "list_rules":            BucketConfig(max_tokens=20, refill_rate=0.5),   # 30/min
    "get_rule_evidence":     BucketConfig(max_tokens=20, refill_rate=0.5),   # 30/min
    "get_system_architecture": BucketConfig(max_tokens=10, refill_rate=0.2), # 12/min
    "read_vault_file":       BucketConfig(max_tokens=15, refill_rate=0.5),   # 30/min
    "record_test_execution": BucketConfig(max_tokens=10, refill_rate=0.2),   # 12/min
    "run_safe_command":      BucketConfig(max_tokens=5, refill_rate=0.1),    # 6/min (mais restritivo)
}

# Config padrão para tools não registradas
_DEFAULT_CONFIG = BucketConfig(max_tokens=30, refill_rate=1.0)


class TokenBucket:
    """Token Bucket individual para uma ferramenta.

    Args:
        tool_name: Nome da ferramenta.
        config: Configuração do bucket. Se None, usa padrão.
    """

    def __init__(self, tool_name: str, config: Optional[BucketConfig] = None):
        self.tool_name = tool_name
        self.config = config or DEFAULT_BUCKET_CONFIGS.get(tool_name, _DEFAULT_CONFIG)
        self._lock = threading.Lock()
        self._tokens: float = float(self.config.initial_tokens)
        self._last_refill: float = time.monotonic()
        self._total_allowed: int = 0
        self._total_rejected: int = 0

    def _refill(self) -> None:
        """Recarga tokens baseado no tempo decorrido."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        new_tokens = elapsed * self.config.refill_rate
        self._tokens = min(self._tokens + new_tokens, float(self.config.max_tokens))
        self._last_refill = now

    def try_acquire(self, tokens: int = 1) -> bool:
        """Tenta consumir tokens. Retorna True se permitido."""
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                self._total_allowed += 1
                return True
            self._total_rejected += 1
            return False

    @property
    def available_tokens(self) -> float:
        """Tokens disponíveis no momento."""
        with self._lock:
            self._refill()
            return self._tokens

    def get_stats(self) -> Dict[str, Any]:
        """Estatísticas do bucket."""
        with self._lock:
            self._refill()
            return {
                "tool_name": self.tool_name,
                "available_tokens": round(self._tokens, 2),
                "max_tokens": self.config.max_tokens,
                "refill_rate": self.config.refill_rate,
                "total_allowed": self._total_allowed,
                "total_rejected": self._total_rejected,
            }

    def reset(self) -> None:
        """Reset manual: enche o bucket."""
        with self._lock:
            self._tokens = float(self.config.max_tokens)
            self._last_refill = time.monotonic()
            self._total_allowed = 0
            self._total_rejected = 0


class RateLimiterRegistry:
    """Registry global de rate limiters por tool.

    Args:
        configs: Dicionário de configurações por tool. Se None, usa DEFAULT_BUCKET_CONFIGS.
    """

    def __init__(self, configs: Optional[Dict[str, BucketConfig]] = None):
        self._configs = configs or DEFAULT_BUCKET_CONFIGS
        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def get(self, tool_name: str) -> TokenBucket:
        """Obtém ou cria um token bucket para a tool."""
        with self._lock:
            if tool_name not in self._buckets:
                config = self._configs.get(tool_name, _DEFAULT_CONFIG)
                self._buckets[tool_name] = TokenBucket(tool_name, config)
            return self._buckets[tool_name]

    def try_acquire(self, tool_name: str) -> bool:
        """Atalho: tenta adquirir 1 token para a tool."""
        return self.get(tool_name).try_acquire()

    def get_all_stats(self) -> Dict[str, Dict]:
        """Stats de todos os buckets (para dashboard)."""
        with self._lock:
            return {name: bucket.get_stats() for name, bucket in self._buckets.items()}

    def get_throttled_tools(self) -> list:
        """Lista tools com bucket vazio (throttled)."""
        with self._lock:
            return [
                name for name, bucket in self._buckets.items()
                if bucket.available_tokens < 1
            ]

    def reset_all(self) -> int:
        """Reset de todos os buckets."""
        with self._lock:
            count = len(self._buckets)
            for bucket in self._buckets.values():
                bucket.reset()
            return count
