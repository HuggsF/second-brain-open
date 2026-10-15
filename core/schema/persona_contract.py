"""Schema Unificado de Contrato de Persona — kiosk.aios.io/v1.

Sprint 4 (Gap G7 — Plano de Convergência KIOSK AI-OS + MoE):
Unifica o contrato YAML da ontologia KIOSK com o modelo AgentPersona v3.1,
adicionando a seção `kiosk_quality_gates` por persona e políticas de
segurança declarativas.

O schema é agnóstico ao formato de persistência (YAML, JSON, dict Python)
e pode ser instanciado de qualquer um deles via `PersonaContract.from_dict()`.

Exemplo de contrato completo:
    {
        "schema_version": "kiosk.aios.io/v1",
        "persona_id": "maia-orchestrator",
        "display_name": "Maia — Orquestradora Principal",
        "role": "orchestrator",
        "kiosk_quality_gates": {
            "pre_mission": ["dlp_input", "rule_compliance", "dag_validation"],
            "post_mission": ["grounding_sha256"],
            "idempotency_required": true,
            "max_hops": 5
        },
        "security_policies": {
            "pii_handling": "mask_reversible",
            "scope_policy": "ORCHESTRATOR_FULL",
            "autonomy_level": "supervisor_approval",
            "auto_approve_up_to_brl": null
        },
        "moe_routing": {
            "embedding_tags": ["orquestração", "delegação", "planejamento"],
            "confidence_threshold": 0.15,
            "fallback_persona": null
        },
        "resilience": {
            "circuit_breaker_threshold": 3,
            "rate_limit_tokens": 30,
            "rate_limit_refill": 1.0
        },
        "audit": {
            "worm_enabled": true,
            "evidence_hash_chain": true
        }
    }
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Gates válidos no pipeline do KIOSK
VALID_GATES = frozenset({
    "dlp_input",
    "rule_compliance",
    "dag_validation",
    "grounding_sha256",
    "idempotency",
})

# Políticas de PII válidas
VALID_PII_POLICIES = frozenset({
    "mask_reversible",   # Tokens reversíveis [PII_TOKEN_01]
    "mask_permanent",    # Máscara irreversível
    "block",             # Rejeitar payload com PII
    "allow",             # Permitir (apenas para agentes internos)
})

# Políticas de escopo de contexto (alinhado com session_store.py ScopePolicy)
VALID_SCOPE_POLICIES = frozenset({
    "ORCHESTRATOR_FULL",
    "SCOPED_SUMMARY",
    "FINANCIAL_ISOLATED_VIEW",
    "TECHNICAL_METRICS_ONLY",
    "CUSTOMER_FACING_ONLY",
})

# Níveis de autonomia (alinhado com decide.py)
VALID_AUTONOMY_LEVELS = frozenset({
    "auto_execute",
    "supervisor_approval",
    "conditional_hitl",
})

VALID_ROLES = frozenset({
    "orchestrator",
    "specialist",
    "supervisor",
    "executor",
})


@dataclass
class QualityGatesConfig:
    """Declaração de quais gates são obrigatórios para esta persona."""
    pre_mission: List[str] = field(default_factory=list)
    post_mission: List[str] = field(default_factory=list)
    idempotency_required: bool = False
    max_hops: int = 5

    def validate(self) -> List[str]:
        errors = []
        all_gates = set(self.pre_mission) | set(self.post_mission)
        invalid = all_gates - VALID_GATES
        if invalid:
            errors.append(f"gates desconhecidos: {', '.join(sorted(invalid))}")
        if self.idempotency_required and "idempotency" not in self.pre_mission:
            errors.append("idempotency_required=True mas 'idempotency' não está em pre_mission")
        if self.max_hops < 1 or self.max_hops > 20:
            errors.append(f"max_hops deve ser entre 1 e 20, recebido: {self.max_hops}")
        return errors


@dataclass
class SecurityPolicies:
    """Políticas de segurança da persona."""
    pii_handling: str = "mask_reversible"
    scope_policy: str = "SCOPED_SUMMARY"
    autonomy_level: str = "supervisor_approval"
    auto_approve_up_to_brl: Optional[float] = None

    def validate(self) -> List[str]:
        errors = []
        if self.pii_handling not in VALID_PII_POLICIES:
            errors.append(f"pii_handling inválido: '{self.pii_handling}'")
        if self.scope_policy not in VALID_SCOPE_POLICIES:
            errors.append(f"scope_policy inválido: '{self.scope_policy}'")
        if self.autonomy_level not in VALID_AUTONOMY_LEVELS:
            errors.append(f"autonomy_level inválido: '{self.autonomy_level}'")
        if self.auto_approve_up_to_brl is not None and self.auto_approve_up_to_brl < 0:
            errors.append("auto_approve_up_to_brl não pode ser negativo")
        return errors


@dataclass
class MoERoutingConfig:
    """Configuração de roteamento MoE para esta persona."""
    embedding_tags: List[str] = field(default_factory=list)
    confidence_threshold: float = 0.15
    fallback_persona: Optional[str] = None

    def validate(self) -> List[str]:
        errors = []
        if not self.embedding_tags:
            errors.append("embedding_tags não pode ser vazio")
        if not 0.0 <= self.confidence_threshold <= 1.0:
            errors.append(f"confidence_threshold deve ser entre 0.0 e 1.0, recebido: {self.confidence_threshold}")
        return errors


@dataclass
class ResilienceConfig:
    """Configuração de resiliência por persona."""
    circuit_breaker_threshold: int = 3
    rate_limit_tokens: int = 30
    rate_limit_refill: float = 1.0

    def validate(self) -> List[str]:
        errors = []
        if self.circuit_breaker_threshold < 1:
            errors.append("circuit_breaker_threshold deve ser >= 1")
        if self.rate_limit_tokens < 1:
            errors.append("rate_limit_tokens deve ser >= 1")
        if self.rate_limit_refill <= 0:
            errors.append("rate_limit_refill deve ser > 0")
        return errors


@dataclass
class AuditConfig:
    """Configuração de auditoria WORM por persona."""
    worm_enabled: bool = True
    evidence_hash_chain: bool = True

    def validate(self) -> List[str]:
        return []  # Sem restrições — apenas flags booleanas


@dataclass
class RBACConfig:
    """Configuração RBAC explícita por persona.

    Define o papel RBAC e a lista de ferramentas permitidas.
    Se `allowed_tools` estiver vazio, herda do TOOL_REGISTRY.
    """
    rbac_role: str = ""
    allowed_tools: List[str] = field(default_factory=list)
    denied_tools: List[str] = field(default_factory=list)

    def validate(self) -> List[str]:
        errors = []
        overlap = set(self.allowed_tools) & set(self.denied_tools)
        if overlap:
            errors.append(f"tools em allowed e denied simultaneamente: {', '.join(sorted(overlap))}")
        return errors


@dataclass
class IOContractConfig:
    """Contrato de input/output por persona.

    Define campos obrigatórios no input e formato esperado no output.
    """
    required_input_fields: List[str] = field(default_factory=list)
    output_schema_strict: bool = False
    required_output_fields: List[str] = field(default_factory=list)

    def validate(self) -> List[str]:
        return []  # Validation-free — just declarative


@dataclass
class PersonaContract:
    """Contrato unificado kiosk.aios.io/v1.

    Combina a ontologia KIOSK com o modelo AgentPersona v3.1, incluindo:
    - Quality Gates declarativos por persona
    - Políticas de segurança (PII, escopo, autonomia)
    - Roteamento MoE
    - Resiliência (circuit breaker + rate limiter)
    - Auditoria WORM

    Args:
        schema_version: Versão do schema (padrão: kiosk.aios.io/v1).
        persona_id: Identificador único da persona.
        display_name: Nome para exibição.
        role: Papel na orquestração (orchestrator, specialist, supervisor, executor).
        quality_gates: Configuração de quality gates.
        security: Políticas de segurança.
        moe_routing: Configuração de roteamento MoE.
        resilience: Configuração de resiliência.
        audit: Configuração de auditoria WORM.
        forbidden_topics: Lista de tópicos proibidos por persona.
        io_contract: Configuração de contratos de input/output por persona.
        rbac: Configuração RBAC explícita por persona.
    """
    schema_version: str = "kiosk.aios.io/v1"
    persona_id: str = ""
    display_name: str = ""
    role: str = "specialist"
    quality_gates: QualityGatesConfig = field(default_factory=QualityGatesConfig)
    security: SecurityPolicies = field(default_factory=SecurityPolicies)
    moe_routing: MoERoutingConfig = field(default_factory=lambda: MoERoutingConfig(embedding_tags=["geral"]))
    resilience: ResilienceConfig = field(default_factory=ResilienceConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
    forbidden_topics: List[str] = field(default_factory=list)
    io_contract: IOContractConfig = field(default_factory=IOContractConfig)
    rbac: RBACConfig = field(default_factory=RBACConfig)

    def validate(self) -> List[str]:
        """Valida o contrato completo. Retorna lista de erros (vazia = válido)."""
        errors = []
        if self.schema_version != "kiosk.aios.io/v1":
            errors.append(f"schema_version esperado: 'kiosk.aios.io/v1', recebido: '{self.schema_version}'")
        if not self.persona_id:
            errors.append("persona_id é obrigatório")
        if not self.display_name:
            errors.append("display_name é obrigatório")
        if self.role not in VALID_ROLES:
            errors.append(f"role inválido: '{self.role}' (válidos: {', '.join(sorted(VALID_ROLES))})")
        errors.extend(self.quality_gates.validate())
        errors.extend(self.security.validate())
        errors.extend(self.moe_routing.validate())
        errors.extend(self.resilience.validate())
        errors.extend(self.audit.validate())
        if self.rbac:
            errors.extend(self.rbac.validate())
        if self.io_contract:
            errors.extend(self.io_contract.validate())
        return errors

    def to_dict(self) -> Dict[str, Any]:
        """Serializa para dicionário (compatível com YAML/JSON)."""
        return {
            "schema_version": self.schema_version,
            "persona_id": self.persona_id,
            "display_name": self.display_name,
            "role": self.role,
            "kiosk_quality_gates": {
                "pre_mission": list(self.quality_gates.pre_mission),
                "post_mission": list(self.quality_gates.post_mission),
                "idempotency_required": self.quality_gates.idempotency_required,
                "max_hops": self.quality_gates.max_hops,
            },
            "security_policies": {
                "pii_handling": self.security.pii_handling,
                "scope_policy": self.security.scope_policy,
                "autonomy_level": self.security.autonomy_level,
                "auto_approve_up_to_brl": self.security.auto_approve_up_to_brl,
            },
            "moe_routing": {
                "embedding_tags": list(self.moe_routing.embedding_tags),
                "confidence_threshold": self.moe_routing.confidence_threshold,
                "fallback_persona": self.moe_routing.fallback_persona,
            },
            "resilience": {
                "circuit_breaker_threshold": self.resilience.circuit_breaker_threshold,
                "rate_limit_tokens": self.resilience.rate_limit_tokens,
                "rate_limit_refill": self.resilience.rate_limit_refill,
            },
            "audit": {
                "worm_enabled": self.audit.worm_enabled,
                "evidence_hash_chain": self.audit.evidence_hash_chain,
            },
            "forbidden_topics": list(self.forbidden_topics),
            "rbac": {
                "rbac_role": self.rbac.rbac_role,
                "allowed_tools": list(self.rbac.allowed_tools),
                "denied_tools": list(self.rbac.denied_tools),
            },
            "io_contract": {
                "required_input_fields": list(self.io_contract.required_input_fields),
                "output_schema_strict": self.io_contract.output_schema_strict,
                "required_output_fields": list(self.io_contract.required_output_fields),
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonaContract":
        """Cria PersonaContract a partir de dicionário (YAML/JSON/dict)."""
        gates_raw = data.get("kiosk_quality_gates", {})
        sec_raw = data.get("security_policies", {})
        moe_raw = data.get("moe_routing", {})
        res_raw = data.get("resilience", {})
        aud_raw = data.get("audit", {})
        rbac_raw = data.get("rbac", {})
        io_raw = data.get("io_contract", {})

        if isinstance(rbac_raw, RBACConfig):
            rbac_obj = rbac_raw
        elif isinstance(rbac_raw, dict):
            rbac_obj = RBACConfig(
                rbac_role=rbac_raw.get("rbac_role", ""),
                allowed_tools=list(rbac_raw.get("allowed_tools", [])),
                denied_tools=list(rbac_raw.get("denied_tools", [])),
            )
        else:
            rbac_obj = RBACConfig()

        if isinstance(io_raw, IOContractConfig):
            io_obj = io_raw
        elif isinstance(io_raw, dict):
            io_obj = IOContractConfig(
                required_input_fields=list(io_raw.get("required_input_fields", [])),
                output_schema_strict=bool(io_raw.get("output_schema_strict", False)),
                required_output_fields=list(io_raw.get("required_output_fields", [])),
            )
        else:
            io_obj = IOContractConfig()

        return cls(
            schema_version=data.get("schema_version", "kiosk.aios.io/v1"),
            persona_id=data.get("persona_id", ""),
            display_name=data.get("display_name", ""),
            role=data.get("role", "specialist"),
            quality_gates=QualityGatesConfig(
                pre_mission=gates_raw.get("pre_mission", []),
                post_mission=gates_raw.get("post_mission", []),
                idempotency_required=gates_raw.get("idempotency_required", False),
                max_hops=gates_raw.get("max_hops", 5),
            ),
            security=SecurityPolicies(
                pii_handling=sec_raw.get("pii_handling", "mask_reversible"),
                scope_policy=sec_raw.get("scope_policy", "SCOPED_SUMMARY"),
                autonomy_level=sec_raw.get("autonomy_level", "supervisor_approval"),
                auto_approve_up_to_brl=sec_raw.get("auto_approve_up_to_brl"),
            ),
            moe_routing=MoERoutingConfig(
                embedding_tags=moe_raw.get("embedding_tags", ["geral"]),
                confidence_threshold=moe_raw.get("confidence_threshold", 0.15),
                fallback_persona=moe_raw.get("fallback_persona"),
            ),
            resilience=ResilienceConfig(
                circuit_breaker_threshold=res_raw.get("circuit_breaker_threshold", 3),
                rate_limit_tokens=res_raw.get("rate_limit_tokens", 30),
                rate_limit_refill=res_raw.get("rate_limit_refill", 1.0),
            ),
            audit=AuditConfig(
                worm_enabled=aud_raw.get("worm_enabled", True),
                evidence_hash_chain=aud_raw.get("evidence_hash_chain", True),
            ),
            forbidden_topics=list(data.get("forbidden_topics", [])),
            io_contract=io_obj,
            rbac=rbac_obj,
        )


# ─── Contratos Pré-Definidos ─────────────────────────────────────────────────

BUILTIN_CONTRACTS: Dict[str, Dict[str, Any]] = {
    "maia-orchestrator": {
        "schema_version": "kiosk.aios.io/v1",
        "persona_id": "maia-orchestrator",
        "display_name": "Maia — Orquestradora Principal",
        "role": "orchestrator",
        "kiosk_quality_gates": {
            "pre_mission": ["dlp_input", "rule_compliance", "dag_validation", "idempotency"],
            "post_mission": ["grounding_sha256"],
            "idempotency_required": True,
            "max_hops": 5,
        },
        "security_policies": {
            "pii_handling": "mask_reversible",
            "scope_policy": "ORCHESTRATOR_FULL",
            "autonomy_level": "supervisor_approval",
        },
        "moe_routing": {
            "embedding_tags": ["orquestração", "delegação", "planejamento", "missão"],
            "confidence_threshold": 0.15,
        },
        "resilience": {
            "circuit_breaker_threshold": 3,
            "rate_limit_tokens": 30,
            "rate_limit_refill": 1.0,
        },
        "audit": {
            "worm_enabled": True,
            "evidence_hash_chain": True,
        },
        "forbidden_topics": ["dados financeiros de clientes", "senhas de produção"],
        "rbac": {
            "rbac_role": "role:agent:orchestrator",
            "allowed_tools": ["search_knowledge_base", "get_brain_status", "list_rules", "get_rule_evidence"],
            "denied_tools": ["run_safe_command"],
        },
        "io_contract": {
            "required_input_fields": ["query"],
            "output_schema_strict": False,
            "required_output_fields": [],
        },
    },
    "eva-supervisor": {
        "schema_version": "kiosk.aios.io/v1",
        "persona_id": "eva-supervisor",
        "display_name": "Eva — Supervisora de Qualidade",
        "role": "supervisor",
        "kiosk_quality_gates": {
            "pre_mission": ["dlp_input", "rule_compliance"],
            "post_mission": ["grounding_sha256"],
            "idempotency_required": False,
            "max_hops": 3,
        },
        "security_policies": {
            "pii_handling": "mask_reversible",
            "scope_policy": "SCOPED_SUMMARY",
            "autonomy_level": "supervisor_approval",
        },
        "moe_routing": {
            "embedding_tags": ["qualidade", "revisão", "compliance", "auditoria"],
            "confidence_threshold": 0.12,
            "fallback_persona": "maia-orchestrator",
        },
        "resilience": {
            "circuit_breaker_threshold": 3,
            "rate_limit_tokens": 20,
            "rate_limit_refill": 0.5,
        },
        "audit": {
            "worm_enabled": True,
            "evidence_hash_chain": True,
        },
        "forbidden_topics": [],
        "rbac": {
            "rbac_role": "role:agent:supervisor",
            "allowed_tools": ["search_knowledge_base", "get_adr", "list_rules", "get_rule_evidence"],
            "denied_tools": [],
        },
        "io_contract": {
            "required_input_fields": [],
            "output_schema_strict": True,
            "required_output_fields": ["verdict", "confidence"],
        },
    },
    "persona-devops": {
        "schema_version": "kiosk.aios.io/v1",
        "persona_id": "persona-devops",
        "display_name": "DevOps Specialist",
        "role": "executor",
        "kiosk_quality_gates": {
            "pre_mission": ["dlp_input", "rule_compliance", "dag_validation", "idempotency"],
            "post_mission": [],
            "idempotency_required": True,
            "max_hops": 8,
        },
        "security_policies": {
            "pii_handling": "block",
            "scope_policy": "TECHNICAL_METRICS_ONLY",
            "autonomy_level": "conditional_hitl",
            "auto_approve_up_to_brl": 0,
        },
        "moe_routing": {
            "embedding_tags": ["infraestrutura", "deploy", "ci-cd", "monitoramento", "kubernetes"],
            "confidence_threshold": 0.10,
            "fallback_persona": "maia-orchestrator",
        },
        "resilience": {
            "circuit_breaker_threshold": 5,
            "rate_limit_tokens": 10,
            "rate_limit_refill": 0.2,
        },
        "audit": {
            "worm_enabled": True,
            "evidence_hash_chain": True,
        },
        "forbidden_topics": ["dados pessoais de clientes", "informações financeiras"],
        "rbac": {
            "rbac_role": "role:agent:devops_executor",
            "allowed_tools": ["search_knowledge_base", "get_system_architecture", "get_brain_status", "run_safe_command"],
            "denied_tools": [],
        },
        "io_contract": {
            "required_input_fields": ["command"],
            "output_schema_strict": False,
            "required_output_fields": ["status"],
        },
    },
    "persona-finops": {
        "schema_version": "kiosk.aios.io/v1",
        "persona_id": "persona-finops",
        "display_name": "FinOps Specialist",
        "role": "specialist",
        "kiosk_quality_gates": {
            "pre_mission": ["dlp_input", "rule_compliance"],
            "post_mission": ["grounding_sha256"],
            "idempotency_required": False,
            "max_hops": 3,
        },
        "security_policies": {
            "pii_handling": "mask_permanent",
            "scope_policy": "FINANCIAL_ISOLATED_VIEW",
            "autonomy_level": "conditional_hitl",
            "auto_approve_up_to_brl": 500.0,
        },
        "moe_routing": {
            "embedding_tags": ["financeiro", "custo", "orçamento", "billing", "nf-e"],
            "confidence_threshold": 0.12,
            "fallback_persona": "maia-orchestrator",
        },
        "resilience": {
            "circuit_breaker_threshold": 3,
            "rate_limit_tokens": 15,
            "rate_limit_refill": 0.3,
        },
        "audit": {
            "worm_enabled": True,
            "evidence_hash_chain": True,
        },
        "forbidden_topics": ["dados técnicos de infraestrutura", "credenciais de deploy"],
        "rbac": {
            "rbac_role": "role:agent:finops_specialist",
            "allowed_tools": ["search_knowledge_base", "list_rules", "get_rule_evidence"],
            "denied_tools": ["run_safe_command", "get_system_architecture"],
        },
        "io_contract": {
            "required_input_fields": ["amount_brl"],
            "output_schema_strict": True,
            "required_output_fields": ["transaction_id", "status"],
        },
    },
    "cx-triage": {
        "schema_version": "kiosk.aios.io/v1",
        "persona_id": "cx-triage",
        "display_name": "CX Triage — Atendimento ao Cliente",
        "role": "specialist",
        "kiosk_quality_gates": {
            "pre_mission": ["dlp_input", "rule_compliance"],
            "post_mission": ["grounding_sha256"],
            "idempotency_required": False,
            "max_hops": 2,
        },
        "security_policies": {
            "pii_handling": "mask_reversible",
            "scope_policy": "CUSTOMER_FACING_ONLY",
            "autonomy_level": "auto_execute",
            "auto_approve_up_to_brl": None,
        },
        "moe_routing": {
            "embedding_tags": ["atendimento", "cliente", "suporte", "reclamação", "cx", "triage", "sac"],
            "confidence_threshold": 0.12,
            "fallback_persona": "maia-orchestrator",
        },
        "resilience": {
            "circuit_breaker_threshold": 3,
            "rate_limit_tokens": 20,
            "rate_limit_refill": 0.5,
        },
        "audit": {
            "worm_enabled": True,
            "evidence_hash_chain": True,
        },
        "forbidden_topics": ["estorno acima de R$500", "acesso a sistemas internos", "dados financeiros corporativos"],
        "rbac": {
            "rbac_role": "role:agent:cx_readonly",
            "allowed_tools": ["search_knowledge_base", "get_brain_status"],
            "denied_tools": ["run_safe_command", "get_system_architecture", "read_vault_file"],
        },
        "io_contract": {
            "required_input_fields": ["customer_query"],
            "output_schema_strict": False,
            "required_output_fields": ["response", "sentiment"],
        },
    },
    "persona-researcher": {
        "schema_version": "kiosk.aios.io/v1",
        "persona_id": "persona-researcher",
        "display_name": "Researcher — Persona de Pesquisa",
        "role": "specialist",
        "kiosk_quality_gates": {
            "pre_mission": ["dlp_input", "rule_compliance"],
            "post_mission": [],
            "idempotency_required": False,
            "max_hops": 3,
        },
        "security_policies": {
            "pii_handling": "mask_permanent",
            "scope_policy": "SCOPED_SUMMARY",
            "autonomy_level": "auto_execute",
            "auto_approve_up_to_brl": 0,
        },
        "moe_routing": {
            "embedding_tags": ["pesquisa", "busca", "análise", "dados"],
            "confidence_threshold": 0.15,
            "fallback_persona": "maia-orchestrator",
        },
        "resilience": {
            "circuit_breaker_threshold": 3,
            "rate_limit_tokens": 20,
            "rate_limit_refill": 0.5,
        },
        "audit": {
            "worm_enabled": True,
            "evidence_hash_chain": True,
        },
        "forbidden_topics": [],
        "rbac": {
            "rbac_role": "role:agent:researcher_readonly",
            "allowed_tools": ["search_knowledge_base", "query_database", "read_document", "get_context", "list_sources"],
            "denied_tools": ["run_safe_command", "write_file", "delete_file", "deploy"],
        },
        "io_contract": {
            "required_input_fields": [],
            "output_schema_strict": False,
            "required_output_fields": ["summary"],
        },
    },
    "persona-writer": {
        "schema_version": "kiosk.aios.io/v1",
        "persona_id": "persona-writer",
        "display_name": "Writer — Persona de Redação",
        "role": "specialist",
        "kiosk_quality_gates": {
            "pre_mission": ["dlp_input", "rule_compliance"],
            "post_mission": ["grounding_sha256"],
            "idempotency_required": False,
            "max_hops": 3,
        },
        "security_policies": {
            "pii_handling": "mask_permanent",
            "scope_policy": "SCOPED_SUMMARY",
            "autonomy_level": "auto_execute",
            "auto_approve_up_to_brl": 0,
        },
        "moe_routing": {
            "embedding_tags": ["redação", "conteúdo", "escrita", "texto"],
            "confidence_threshold": 0.15,
            "fallback_persona": "maia-orchestrator",
        },
        "resilience": {
            "circuit_breaker_threshold": 3,
            "rate_limit_tokens": 20,
            "rate_limit_refill": 0.5,
        },
        "audit": {
            "worm_enabled": True,
            "evidence_hash_chain": True,
        },
        "forbidden_topics": [],
        "rbac": {
            "rbac_role": "role:agent:writer",
            "allowed_tools": ["write_content", "draft_response", "compose_email", "edit_text", "format_document"],
            "denied_tools": ["run_safe_command", "delete_file", "deploy", "query_database"],
        },
        "io_contract": {
            "required_input_fields": [],
            "output_schema_strict": False,
            "required_output_fields": ["content"],
        },
    },
}


def get_builtin_contract(persona_id: str) -> Optional[PersonaContract]:
    """Retorna contrato built-in ou None se não existir."""
    raw = BUILTIN_CONTRACTS.get(persona_id)
    if raw is None:
        return None
    return PersonaContract.from_dict(raw)


def list_builtin_personas() -> List[str]:
    """Lista IDs de personas com contrato built-in."""
    return sorted(BUILTIN_CONTRACTS.keys())
