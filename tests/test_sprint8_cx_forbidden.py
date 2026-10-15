"""Testes para Sprint 8 — R4 (CX Triage Persona) e R8 (Forbidden Topics per-persona).

Cobre:
- Validação do contrato da nova persona `cx-triage` em BUILTIN_CONTRACTS
- Validação de todos os 5 BUILTIN_CONTRACTS
- Serialização e deserialização do campo `forbidden_topics` em PersonaContract
- Bloqueio por tópicos proibidos específicos por persona via check_forbidden_topics()
- Liberação para personas sem tópicos proibidos (ex: eva-supervisor)
- Isolamento de regras entre personas (tópico proibido em uma é permitido em outra)
- Backward compatibility: chamadas sem persona_id ou com persona desconhecida
- Integração no pre_call_pipeline() com persona_id
"""

import pytest

from core.schema.persona_contract import (
    PersonaContract,
    QualityGatesConfig,
    SecurityPolicies,
    MoERoutingConfig,
    ResilienceConfig,
    AuditConfig,
    BUILTIN_CONTRACTS,
    get_builtin_contract,
    list_builtin_personas,
)
from core.integration import (
    check_forbidden_topics,
    pre_call_pipeline,
    reset_all_singletons,
)


@pytest.fixture(autouse=True)
def setup_teardown():
    """Garante ambiente limpo antes e depois de cada teste."""
    reset_all_singletons()
    yield
    reset_all_singletons()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Validação de BUILTIN_CONTRACTS (Todos os 5)
# ─────────────────────────────────────────────────────────────────────────────

class TestBuiltinContractsSprint8:
    """Valida o conjunto completo de contratos em BUILTIN_CONTRACTS."""

    def test_all_five_contracts_present(self):
        """BUILTIN_CONTRACTS deve conter exatamente 5 contratos."""
        expected = {
            "maia-orchestrator",
            "eva-supervisor",
            "persona-devops",
            "persona-finops",
            "cx-triage",
            "persona-researcher",
            "persona-writer",
        }
        assert set(BUILTIN_CONTRACTS.keys()) == expected

    def test_list_builtin_personas_includes_all_seven(self):
        """list_builtin_personas deve listar ordenadamente as 7 personas."""
        personas = list_builtin_personas()
        assert personas == [
            "cx-triage",
            "eva-supervisor",
            "maia-orchestrator",
            "persona-devops",
            "persona-finops",
            "persona-researcher",
            "persona-writer",
        ]

    def test_all_builtin_contracts_validate_successfully(self):
        """Todos os 5 contratos devem ser válidos segundo o schema kiosk.aios.io/v1."""
        for persona_id in BUILTIN_CONTRACTS:
            contract = get_builtin_contract(persona_id)
            assert contract is not None, f"Contrato {persona_id} retornou None"
            errors = contract.validate()
            assert errors == [], f"Contrato {persona_id} possui erros de validação: {errors}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. R4 — Contrato CX Triage
# ─────────────────────────────────────────────────────────────────────────────

class TestCXTriageContract:
    """Verifica todos os atributos e configurações do contrato cx-triage."""

    def test_cx_triage_contract_attributes(self):
        """Valida que cx-triage segue a especificação completa do simulador."""
        contract = get_builtin_contract("cx-triage")
        assert contract is not None

        # Identificação e Papel
        assert contract.schema_version == "kiosk.aios.io/v1"
        assert contract.persona_id == "cx-triage"
        assert contract.display_name == "CX Triage — Atendimento ao Cliente"
        assert contract.role == "specialist"

        # Quality Gates
        assert contract.quality_gates.pre_mission == ["dlp_input", "rule_compliance"]
        assert contract.quality_gates.post_mission == ["grounding_sha256"]
        assert contract.quality_gates.idempotency_required is False
        assert contract.quality_gates.max_hops == 2

        # Segurança e Políticas
        assert contract.security.pii_handling == "mask_reversible"
        assert contract.security.scope_policy == "CUSTOMER_FACING_ONLY"
        assert contract.security.autonomy_level == "auto_execute"
        assert contract.security.auto_approve_up_to_brl is None

        # Roteamento MoE
        expected_tags = ["atendimento", "cliente", "suporte", "reclamação", "cx", "triage", "sac"]
        assert contract.moe_routing.embedding_tags == expected_tags
        assert contract.moe_routing.confidence_threshold == 0.12
        assert contract.moe_routing.fallback_persona == "maia-orchestrator"

        # Resiliência
        assert contract.resilience.circuit_breaker_threshold == 3
        assert contract.resilience.rate_limit_tokens == 20
        assert contract.resilience.rate_limit_refill == 0.5

        # Auditoria WORM
        assert contract.audit.worm_enabled is True
        assert contract.audit.evidence_hash_chain is True

        # Validação sem erros
        assert contract.validate() == []


# ─────────────────────────────────────────────────────────────────────────────
# 3. R8 — forbidden_topics no PersonaContract (Schema & Roundtrip)
# ─────────────────────────────────────────────────────────────────────────────

class TestPersonaContractForbiddenTopicsSchema:
    """Testa definição e serialização de forbidden_topics no dataclass."""

    def test_default_forbidden_topics_is_empty_list(self):
        """PersonaContract criado com defaults deve ter forbidden_topics=[]."""
        p = PersonaContract(persona_id="test", display_name="Test")
        assert p.forbidden_topics == []
        assert isinstance(p.forbidden_topics, list)

    def test_forbidden_topics_roundtrip_to_dict_from_dict(self):
        """Serialização to_dict() e instanciação from_dict() preservam forbidden_topics."""
        topics = ["tema a", "tema b", "palavra proibida"]
        contract = PersonaContract(
            persona_id="custom-sec",
            display_name="Custom Sec",
            forbidden_topics=topics,
        )

        serialized = contract.to_dict()
        assert "forbidden_topics" in serialized
        assert serialized["forbidden_topics"] == topics

        restored = PersonaContract.from_dict(serialized)
        assert restored.forbidden_topics == topics
        # Garantir que é cópia independente
        assert restored.forbidden_topics is not serialized["forbidden_topics"]

    def test_builtin_forbidden_topics_definitions(self):
        """Cada contrato built-in deve ter suas forbidden_topics específicas configuradas."""
        expected_topics = {
            "maia-orchestrator": [
                "dados financeiros de clientes",
                "senhas de produção",
            ],
            "eva-supervisor": [],
            "persona-devops": [
                "dados pessoais de clientes",
                "informações financeiras",
            ],
            "persona-finops": [
                "dados técnicos de infraestrutura",
                "credenciais de deploy",
            ],
            "cx-triage": [
                "estorno acima de R$500",
                "acesso a sistemas internos",
                "dados financeiros corporativos",
            ],
        }

        for persona_id, topics in expected_topics.items():
            contract = get_builtin_contract(persona_id)
            assert contract is not None
            assert contract.forbidden_topics == topics, f"Divergência de topics para {persona_id}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. R8 — check_forbidden_topics per-persona
# ─────────────────────────────────────────────────────────────────────────────

class TestForbiddenTopicsPerPersona:
    """Testa a avaliação per-persona com check_forbidden_topics()."""

    def test_cx_triage_blocks_configured_topics(self):
        """cx-triage deve bloquear estorno acima de R$500, acessos internos e dados corporativos."""
        # 1. Estorno acima de R$500
        r1 = check_forbidden_topics(
            "Cliente solicitou estorno acima de R$500 imediatamente",
            persona_id="cx-triage",
        )
        assert r1.allowed is False
        assert r1.reason == "forbidden_topic"
        assert "estorno acima de r$500" in r1.details["message"].lower() or "bloqueado" in r1.details["message"].lower()

        # 2. Acesso a sistemas internos
        r2 = check_forbidden_topics(
            "Preciso de acesso a sistemas internos para consultar a conta",
            persona_id="cx-triage",
        )
        assert r2.allowed is False
        assert r2.reason == "forbidden_topic"

        # 3. Dados financeiros corporativos
        r3 = check_forbidden_topics(
            "Favor enviar relatorio com dados financeiros corporativos da empresa",
            persona_id="cx-triage",
        )
        assert r3.allowed is False
        assert r3.reason == "forbidden_topic"

    def test_cx_triage_allows_legitimate_customer_requests(self):
        """cx-triage deve permitir solicitações de suporte dentro do escopo."""
        r = check_forbidden_topics(
            "Cliente quer rastrear o pedido 987654 e alterar endereco de entrega",
            persona_id="cx-triage",
        )
        assert r.allowed is True

    def test_persona_without_forbidden_topics_passes_through(self):
        """eva-supervisor (auditora) possui forbidden_topics=[] e passa por qualquer texto."""
        # Tópico proibido no cx-triage passa na auditora
        r1 = check_forbidden_topics(
            "Auditoria de estorno acima de R$500 e acesso a sistemas internos",
            persona_id="eva-supervisor",
        )
        assert r1.allowed is True

        # Tópico proibido na Maia — agora é SYSTEM_BASE, bloqueia para todos (INV-N04)
        r2 = check_forbidden_topics(
            "Revisando logs com senhas de produção e dados financeiros de clientes",
            persona_id="eva-supervisor",
        )
        assert r2.allowed is False  # INV-N04: base topics always active

    def test_cross_persona_topic_isolation(self):
        """Tópico proibido em uma persona NÃO deve bloquear outra persona não configurada."""
        text_cx_only = "Aprovar estorno acima de R$500"
        text_devops_only = "Ajustar credenciais de deploy no cluster"
        text_finops_only = "Verificar dados técnicos de infraestrutura"

        # No cx-triage: bloqueia estorno, e credenciais de deploy (SYSTEM_BASE — INV-N04)
        assert check_forbidden_topics(text_cx_only, persona_id="cx-triage").allowed is False
        assert check_forbidden_topics(text_devops_only, persona_id="cx-triage").allowed is False  # INV-N04

        # No DevOps: bloqueia dados pessoais, mas não estorno
        assert check_forbidden_topics(text_cx_only, persona_id="persona-devops").allowed is True
        assert check_forbidden_topics(
            "Extrair dados pessoais de clientes", persona_id="persona-devops"
        ).allowed is False

        # No FinOps: bloqueia infra/deploy, mas não dados de estorno de atendimento
        assert check_forbidden_topics(text_finops_only, persona_id="persona-finops").allowed is False
        assert check_forbidden_topics(text_cx_only, persona_id="persona-finops").allowed is True

    def test_backward_compatibility_without_persona_id(self):
        """Chamadas sem persona_id: base topics still block (INV-N04/N05)."""
        # Tópicos que NÃO são base → passam
        r1 = check_forbidden_topics("estorno acima de R$500")
        assert r1.allowed is True

        # Tópicos que SÃO SYSTEM_BASE → bloqueiam mesmo sem persona_id
        r2 = check_forbidden_topics("senhas de produção")
        assert r2.allowed is False  # INV-N04/N05: base topics always active

        r3 = check_forbidden_topics("dados técnicos de infraestrutura")
        assert r3.allowed is True

    def test_unknown_persona_id_passes_safely(self):
        """persona_id desconhecido não causa erro e passa verificação."""
        r = check_forbidden_topics(
            "estorno acima de R$500",
            persona_id="non-existent-persona-12345",
        )
        assert r.allowed is True


# ─────────────────────────────────────────────────────────────────────────────
# 5. pre_call_pipeline Integration com persona_id
# ─────────────────────────────────────────────────────────────────────────────

class TestPreCallPipelineForbiddenTopicsSprint8:
    """Testa a integração de forbidden_topics dentro do pre_call_pipeline()."""

    def test_pipeline_blocks_cx_triage_forbidden_topic(self):
        """pre_call_pipeline bloqueia cx-triage quando task_text tem tópico proibido."""
        result = pre_call_pipeline(
            persona_id="cx-triage",
            tool_name="search_knowledge_base",
            args={"query": "reembolso"},
            task_text="Cliente exige estorno acima de R$500 imediatamente",
        )
        assert result.allowed is False
        assert result.reason == "forbidden_topic"

    def test_pipeline_allows_cx_triage_clean_task(self):
        """pre_call_pipeline aprova cx-triage para task limpa com autonomia auto_execute."""
        result = pre_call_pipeline(
            persona_id="cx-triage",
            tool_name="search_knowledge_base",
            args={"query": "politica_trocas", "customer_query": "troca de produto com defeito"},
            task_text="Como proceder com troca de produto com defeito?",
        )
        assert result.allowed is True
        assert result.reason in ("all_checks_passed", "auto_execute_approved", "input_contract_valid")

    def test_pipeline_passes_eva_supervisor_even_with_sensitive_terms(self):
        """pre_call_pipeline avalia forbidden_topics para supervisor sem bloquear."""
        # Note: eva-supervisor tem autonomia supervisor_approval, portanto o check
        # de forbidden_topics passa, mas a autonomia bloqueia com 'requires_hitl'.
        # Isso confirma que NÃO foi bloqueado por 'forbidden_topic'!
        result = pre_call_pipeline(
            persona_id="eva-supervisor",
            tool_name="search_knowledge_base",
            args={},
            task_text="Revisar auditoria de estorno acima de R$500",
        )
        # O gate de forbidden topics permitiu, então caiu no check de autonomia (requires_hitl)
        assert result.reason == "requires_hitl"
        assert result.reason != "forbidden_topic"
