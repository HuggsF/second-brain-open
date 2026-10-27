"""Circuit Breaker por Tool — proteção contra cascata de falhas.

Sprint 3 (Gap G3 — Plano de Convergência AI-OS + MoE):
Implementa o padrão Circuit Breaker com 3 estados por ferramenta:
  CLOSED  → operação normal, falhas são contadas
  OPEN    → tool desabilitada, todas as chamadas rejeitadas imediatamente
  HALF_OPEN → permite 1 chamada de teste; sucesso fecha, falha reabre

Quando uma tool entra em OPEN, o Broker pode remover dinamicamente o schema
dessa tool da janela da persona ativa (dynamic tool unbind).

Thread-safe via threading.Lock.
"""
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitStats:
    """Estatísticas de um circuit breaker individual."""
    tool_name: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    opened_at: Optional[float] = None
    total_rejected: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "total_rejected": self.total_rejected,
            "last_failure_time": self.last_failure_time,
            "opened_at": self.opened_at,
        }


class ToolCircuitBreaker:
    """Circuit Breaker para uma única ferramenta.

    Args:
        tool_name: Nome da ferramenta.
        failure_threshold: Número de falhas consecutivas para abrir o circuito.
        recovery_timeout: Segundos para transicionar de OPEN para HALF_OPEN.
        success_threshold: Sucessos consecutivos em HALF_OPEN para fechar.
    """

    def __init__(
        self,
        tool_name: str,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
        success_threshold: int = 1,
    ):
        self.tool_name = tool_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self._lock = threading.Lock()
        self._stats = CircuitStats(tool_name=tool_name)
        self._consecutive_failures = 0
        self._consecutive_successes_half_open = 0
        self._half_open_permitted = False

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._resolve_state()

    @property
    def stats(self) -> CircuitStats:
        with self._lock:
            self._stats.state = self._resolve_state()
            return CircuitStats(**{
                k: getattr(self._stats, k) for k in self._stats.__dataclass_fields__
            })

    def _resolve_state(self) -> CircuitState:
        """Resolve o estado real (OPEN pode transicionar para HALF_OPEN por timeout)."""
        if self._stats.state == CircuitState.OPEN and self._stats.opened_at:
            elapsed = time.monotonic() - self._stats.opened_at
            if elapsed >= self.recovery_timeout:
                self._stats.state = CircuitState.HALF_OPEN
                self._consecutive_successes_half_open = 0
                self._half_open_permitted = False  # RESET: novo HALF_OPEN permite 1 probe
        return self._stats.state

    def allow_request(self) -> bool:
        """Verifica se a chamada é permitida. Incrementa rejected se bloqueada."""
        with self._lock:
            state = self._resolve_state()
            if state == CircuitState.CLOSED:
                return True
            if state == CircuitState.HALF_OPEN:
                if not self._half_open_permitted:
                    self._half_open_permitted = True
                    return True  # apenas 1 probe
                return False  # demais requisições bloqueadas
            # OPEN
            self._stats.total_rejected += 1
            return False

    def record_success(self) -> None:
        """Registra uma chamada bem-sucedida."""
        with self._lock:
            now = time.monotonic()
            self._stats.success_count += 1
            self._stats.last_success_time = now
            self._consecutive_failures = 0

            state = self._resolve_state()
            if state == CircuitState.HALF_OPEN:
                self._consecutive_successes_half_open += 1
                if self._consecutive_successes_half_open >= self.success_threshold:
                    self._stats.state = CircuitState.CLOSED
                    self._stats.opened_at = None
                    self._consecutive_successes_half_open = 0
                    self._half_open_permitted = False

    def record_failure(self) -> None:
        """Registra uma falha. Pode transicionar para OPEN."""
        with self._lock:
            now = time.monotonic()
            self._stats.failure_count += 1
            self._stats.last_failure_time = now
            self._consecutive_failures += 1

            state = self._resolve_state()
            if state == CircuitState.HALF_OPEN:
                # Falha em HALF_OPEN → reabre
                self._stats.state = CircuitState.OPEN
                self._stats.opened_at = now
                self._consecutive_successes_half_open = 0
                self._half_open_permitted = False
            elif state == CircuitState.CLOSED:
                if self._consecutive_failures >= self.failure_threshold:
                    self._stats.state = CircuitState.OPEN
                    self._stats.opened_at = now

    def reset(self) -> None:
        """Reset manual (para administração)."""
        with self._lock:
            self._stats = CircuitStats(tool_name=self.tool_name)
            self._consecutive_failures = 0
            self._consecutive_successes_half_open = 0


class CircuitBreakerRegistry:
    """Registry global de circuit breakers por tool.

    Args:
        failure_threshold: Padrão de falhas para abrir circuito.
        recovery_timeout: Padrão de timeout para recovery.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._breakers: Dict[str, ToolCircuitBreaker] = {}
        self._lock = threading.Lock()

    def get(self, tool_name: str) -> ToolCircuitBreaker:
        """Obtém ou cria um circuit breaker para a tool."""
        with self._lock:
            if tool_name not in self._breakers:
                self._breakers[tool_name] = ToolCircuitBreaker(
                    tool_name=tool_name,
                    failure_threshold=self.failure_threshold,
                    recovery_timeout=self.recovery_timeout,
                )
            return self._breakers[tool_name]

    def get_open_tools(self) -> list:
        """Retorna lista de tools com circuito aberto (para dynamic unbind)."""
        with self._lock:
            return [
                name for name, cb in self._breakers.items()
                if cb.state == CircuitState.OPEN
            ]

    def get_all_stats(self) -> Dict[str, Dict]:
        """Retorna stats de todos os breakers (para dashboard)."""
        with self._lock:
            return {name: cb.stats.to_dict() for name, cb in self._breakers.items()}

    def reset_all(self) -> int:
        """Reset de todos os breakers."""
        with self._lock:
            count = len(self._breakers)
            for cb in self._breakers.values():
                cb.reset()
            return count
