"""Testes para core/schema e core/audit — Schema Unificado e WORM Audit.

Sprint 4 (Gaps G7 + G8): Cobertura completa do contrato de persona
unificado e do audit trail com hash-chain.
"""

import json
import tempfile
from pathlib import Path

import pytest

from core.schema.persona_contract import (
    PersonaContract,
    QualityGatesConfig,
    SecurityPolicies,
    MoERoutingConfig,
    ResilienceConfig,
    AuditConfig,
    BUILTIN_CONTRACTS,
    VALID_GATES,
    VALID_PII_POLICIES,
    VALID_SCOPE_POLICIES,
    VALID_AUTONOMY_LEVELS,
    VALID_ROLES,
    get_builtin_contract,
    list_builtin_personas,
)
from core.audit.worm_audit import (
    GENESIS_HASH,
    AuditRecord,
    WORMAuditLog,
    VerificationResult,
    hash_payload,
    verify_chain,
)


# ─────────────────────────────────────────────
# QualityGatesConfig
# ─────────────────────────────────────────────

class TestQualityGatesConfig:
    def test_valid_gates(self):
        cfg = QualityGatesConfig(
            pre_mission=["dlp_input", "rule_compliance"],
            post_mission=["grounding_sha256"],
        )
        assert cfg.validate() == []

    def test_invalid_gate_name(self):
        cfg = QualityGatesConfig(pre_mission=["unknown_gate"])
        errors = cfg.validate()
        assert any("desconhecidos" in e for e in errors)

    def test_idempotency_required_without_gate(self):
        cfg = QualityGatesConfig(idempotency_required=True, pre_mission=[])
        errors = cfg.validate()
        assert any("idempotency" in e for e in errors)

    def test_idempotency_required_with_gate(self):
        cfg = QualityGatesConfig(
            idempotency_required=True,
            pre_mission=["idempotency"],
        )
        assert cfg.validate() == []

    def test_max_hops_out_of_range(self):
        cfg = QualityGatesConfig(max_hops=0)
        errors = cfg.validate()
        assert any("max_hops" in e for e in errors)

        cfg2 = QualityGatesConfig(max_hops=21)
        errors2 = cfg2.validate()
        assert any("max_hops" in e for e in errors2)


# ─────────────────────────────────────────────
# SecurityPolicies
# ─────────────────────────────────────────────

class TestSecurityPolicies:
    def test_valid_defaults(self):
        sp = SecurityPolicies()
        assert sp.validate() == []

    def test_invalid_pii_handling(self):
        sp = SecurityPolicies(pii_handling="invalid")
        errors = sp.validate()
        assert any("pii_handling" in e for e in errors)

    def test_invalid_scope_policy(self):
        sp = SecurityPolicies(scope_policy="GLOBAL_ACCESS")
        errors = sp.validate()
        assert any("scope_policy" in e for e in errors)

    def test_invalid_autonomy_level(self):
        sp = SecurityPolicies(autonomy_level="unrestricted")
        errors = sp.validate()
        assert any("autonomy_level" in e for e in errors)

    def test_negative_auto_approve(self):
        sp = SecurityPolicies(auto_approve_up_to_brl=-10.0)
        errors = sp.validate()
        assert any("negativo" in e for e in errors)

    def test_zero_auto_approve_is_valid(self):
        sp = SecurityPolicies(auto_approve_up_to_brl=0.0)
        assert sp.validate() == []


# ─────────────────────────────────────────────
# MoERoutingConfig
# ─────────────────────────────────────────────

class TestMoERoutingConfig:
    def test_valid_config(self):
        cfg = MoERoutingConfig(embedding_tags=["test"], confidence_threshold=0.5)
        assert cfg.validate() == []

    def test_empty_tags(self):
        cfg = MoERoutingConfig(embedding_tags=[])
        errors = cfg.validate()
        assert any("embedding_tags" in e for e in errors)

    def test_threshold_out_of_range(self):
        cfg = MoERoutingConfig(embedding_tags=["x"], confidence_threshold=1.5)
        errors = cfg.validate()
        assert any("confidence_threshold" in e for e in errors)


# ─────────────────────────────────────────────
# ResilienceConfig
# ─────────────────────────────────────────────

class TestResilienceConfig:
    def test_valid_defaults(self):
        cfg = ResilienceConfig()
        assert cfg.validate() == []

    def test_invalid_threshold(self):
        cfg = ResilienceConfig(circuit_breaker_threshold=0)
        errors = cfg.validate()
        assert any("circuit_breaker_threshold" in e for e in errors)

    def test_invalid_rate_limit(self):
        cfg = ResilienceConfig(rate_limit_tokens=0, rate_limit_refill=-1.0)
        errors = cfg.validate()
        assert len(errors) == 2


# ─────────────────────────────────────────────
# PersonaContract
# ─────────────────────────────────────────────

class TestPersonaContract:
    def test_valid_contract(self):
        contract = PersonaContract(
            persona_id="test-agent",
            display_name="Test Agent",
            role="specialist",
            quality_gates=QualityGatesConfig(
                pre_mission=["dlp_input"],
                post_mission=["grounding_sha256"],
            ),
            moe_routing=MoERoutingConfig(embedding_tags=["test"]),
        )
        assert contract.validate() == []

    def test_missing_persona_id(self):
        contract = PersonaContract(display_name="Test")
        errors = contract.validate()
        assert any("persona_id" in e for e in errors)

    def test_missing_display_name(self):
        contract = PersonaContract(persona_id="test")
        errors = contract.validate()
        assert any("display_name" in e for e in errors)

    def test_invalid_role(self):
        contract = PersonaContract(
            persona_id="x", display_name="X", role="admin",
            moe_routing=MoERoutingConfig(embedding_tags=["x"]),
        )
        errors = contract.validate()
        assert any("role" in e for e in errors)

    def test_invalid_schema_version(self):
        contract = PersonaContract(
            schema_version="v2",
            persona_id="x", display_name="X",
            moe_routing=MoERoutingConfig(embedding_tags=["x"]),
        )
        errors = contract.validate()
        assert any("schema_version" in e for e in errors)

    def test_to_dict_roundtrip(self):
        original = PersonaContract(
            persona_id="roundtrip",
            display_name="Roundtrip Test",
            role="executor",
            quality_gates=QualityGatesConfig(
                pre_mission=["dlp_input", "dag_validation"],
                post_mission=["grounding_sha256"],
                idempotency_required=False,
                max_hops=7,
            ),
            security=SecurityPolicies(
                pii_handling="block",
                scope_policy="TECHNICAL_METRICS_ONLY",
                autonomy_level="auto_execute",
            ),
            moe_routing=MoERoutingConfig(
                embedding_tags=["infra", "deploy"],
                confidence_threshold=0.2,
                fallback_persona="maia-orchestrator",
            ),
            resilience=ResilienceConfig(
                circuit_breaker_threshold=5,
                rate_limit_tokens=10,
                rate_limit_refill=0.3,
            ),
            audit=AuditConfig(worm_enabled=True, evidence_hash_chain=True),
        )
        d = original.to_dict()
        restored = PersonaContract.from_dict(d)
        assert restored.persona_id == original.persona_id
        assert restored.quality_gates.max_hops == 7
        assert restored.security.pii_handling == "block"
        assert restored.moe_routing.fallback_persona == "maia-orchestrator"
        assert restored.resilience.circuit_breaker_threshold == 5
        assert restored.audit.worm_enabled is True

    def test_from_dict_with_defaults(self):
        """from_dict com dict mínimo aplica defaults seguros."""
        contract = PersonaContract.from_dict({
            "persona_id": "minimal",
            "display_name": "Minimal",
        })
        assert contract.role == "specialist"
        assert contract.security.pii_handling == "mask_reversible"
        assert contract.quality_gates.max_hops == 5
        assert contract.moe_routing.confidence_threshold == 0.15
        assert contract.audit.worm_enabled is True

    def test_cascading_validation_errors(self):
        """Contrato com múltiplos erros em sub-componentes."""
        contract = PersonaContract(
            persona_id="",
            display_name="",
            role="hacker",
            quality_gates=QualityGatesConfig(pre_mission=["fake_gate"], max_hops=0),
            security=SecurityPolicies(pii_handling="open"),
            moe_routing=MoERoutingConfig(embedding_tags=[], confidence_threshold=2.0),
            resilience=ResilienceConfig(circuit_breaker_threshold=0),
        )
        errors = contract.validate()
        # Deve ter erros de: persona_id, display_name, role, gates, max_hops, pii, tags, threshold, cb
        assert len(errors) >= 8


# ─────────────────────────────────────────────
# Built-in Contracts
# ─────────────────────────────────────────────

class TestBuiltinContracts:
    def test_all_builtins_are_valid(self):
        """Todos os contratos pré-definidos devem passar validação."""
        for persona_id, raw in BUILTIN_CONTRACTS.items():
            contract = PersonaContract.from_dict(raw)
            errors = contract.validate()
            assert errors == [], f"{persona_id} tem erros: {errors}"

    def test_list_builtin_personas(self):
        personas = list_builtin_personas()
        assert "maia-orchestrator" in personas
        assert "eva-supervisor" in personas
        assert "persona-devops" in personas
        assert "persona-finops" in personas

    def test_get_builtin_contract(self):
        contract = get_builtin_contract("maia-orchestrator")
        assert contract is not None
        assert contract.persona_id == "maia-orchestrator"
        assert contract.role == "orchestrator"
        assert "dlp_input" in contract.quality_gates.pre_mission

    def test_get_unknown_returns_none(self):
        assert get_builtin_contract("unknown-persona") is None

    def test_maia_has_full_gate_pipeline(self):
        maia = get_builtin_contract("maia-orchestrator")
        assert "dlp_input" in maia.quality_gates.pre_mission
        assert "rule_compliance" in maia.quality_gates.pre_mission
        assert "dag_validation" in maia.quality_gates.pre_mission
        assert "idempotency" in maia.quality_gates.pre_mission
        assert "grounding_sha256" in maia.quality_gates.post_mission
        assert maia.quality_gates.idempotency_required is True

    def test_devops_has_block_pii(self):
        devops = get_builtin_contract("persona-devops")
        assert devops.security.pii_handling == "block"

    def test_finops_has_auto_approve_limit(self):
        finops = get_builtin_contract("persona-finops")
        assert finops.security.auto_approve_up_to_brl == 500.0


# ─────────────────────────────────────────────
# AuditRecord
# ─────────────────────────────────────────────

class TestAuditRecord:
    def test_compute_hash_deterministic(self):
        r = AuditRecord(
            sequence=0,
            timestamp="2026-01-01T00:00:00Z",
            event_type="test.event",
            actor="system",
            trace_id="abc123",
            payload_hash="deadbeef" * 8,
            prev_hash=GENESIS_HASH,
        )
        h1 = r.compute_hash()
        h2 = r.compute_hash()
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_to_dict_from_dict_roundtrip(self):
        r = AuditRecord(
            sequence=5,
            timestamp="2026-10-15T12:00:00Z",
            event_type="gate.dlp_input",
            actor="maia-orchestrator",
            trace_id="trace123",
            payload_hash="a" * 64,
            prev_hash="b" * 64,
            record_hash="c" * 64,
            metadata={"verdict": "GREEN"},
        )
        d = r.to_dict()
        restored = AuditRecord.from_dict(d)
        assert restored.sequence == r.sequence
        assert restored.event_type == r.event_type
        assert restored.metadata == {"verdict": "GREEN"}

    def test_different_inputs_different_hashes(self):
        r1 = AuditRecord(0, "t", "a", "x", "id1", "p1", GENESIS_HASH)
        r2 = AuditRecord(0, "t", "b", "x", "id1", "p1", GENESIS_HASH)
        assert r1.compute_hash() != r2.compute_hash()


# ─────────────────────────────────────────────
# hash_payload
# ─────────────────────────────────────────────

class TestHashPayload:
    def test_none_payload(self):
        h = hash_payload(None)
        assert len(h) == 64

    def test_string_payload(self):
        h = hash_payload("hello")
        assert len(h) == 64

    def test_dict_payload_deterministic(self):
        h1 = hash_payload({"b": 2, "a": 1})
        h2 = hash_payload({"a": 1, "b": 2})
        assert h1 == h2  # sort_keys garante determinismo

    def test_different_payloads_different_hashes(self):
        assert hash_payload("a") != hash_payload("b")


# ─────────────────────────────────────────────
# WORMAuditLog
# ─────────────────────────────────────────────

class TestWORMAuditLog:
    def _tmp_path(self) -> Path:
        """Cria um arquivo temporário para o audit log."""
        return Path(tempfile.mkdtemp()) / "audit.jsonl"

    def test_empty_log(self):
        log = WORMAuditLog(self._tmp_path())
        assert log.length == 0
        assert log.last_hash == GENESIS_HASH

    def test_append_single_record(self):
        log = WORMAuditLog(self._tmp_path())
        record = log.append(
            event_type="test.event",
            actor="system",
            trace_id="trace-001",
            payload={"key": "value"},
            timestamp="2026-01-01T00:00:00Z",
        )
        assert record.sequence == 0
        assert record.prev_hash == GENESIS_HASH
        assert record.record_hash != ""
        assert log.length == 1
        assert log.last_hash == record.record_hash

    def test_append_chain(self):
        log = WORMAuditLog(self._tmp_path())
        r1 = log.append("evt.a", "actor1", "t1", timestamp="2026-01-01T00:00:00Z")
        r2 = log.append("evt.b", "actor2", "t2", timestamp="2026-01-01T00:01:00Z")
        r3 = log.append("evt.c", "actor3", "t3", timestamp="2026-01-01T00:02:00Z")

        assert r1.prev_hash == GENESIS_HASH
        assert r2.prev_hash == r1.record_hash
        assert r3.prev_hash == r2.record_hash
        assert log.length == 3

    def test_persistence_and_rebuild(self):
        path = self._tmp_path()
        log1 = WORMAuditLog(path)
        log1.append("evt.a", "actor1", "t1", timestamp="2026-01-01T00:00:00Z")
        log1.append("evt.b", "actor2", "t2", timestamp="2026-01-01T00:01:00Z")
        last_hash = log1.last_hash

        # Nova instância lê o arquivo existente
        log2 = WORMAuditLog(path)
        assert log2.length == 2
        assert log2.last_hash == last_hash

        # Append continua a cadeia
        r3 = log2.append("evt.c", "actor3", "t3", timestamp="2026-01-01T00:02:00Z")
        assert r3.prev_hash == last_hash
        assert r3.sequence == 2

    def test_read_all(self):
        log = WORMAuditLog(self._tmp_path())
        log.append("evt.a", "a1", "t1", timestamp="2026-01-01T00:00:00Z")
        log.append("evt.b", "a2", "t2", timestamp="2026-01-01T00:01:00Z")

        records = log.read_all()
        assert len(records) == 2
        assert records[0].sequence == 0
        assert records[1].sequence == 1

    def test_metadata_persisted(self):
        log = WORMAuditLog(self._tmp_path())
        r = log.append(
            "gate.result", "maia", "t1",
            metadata={"gate": "dlp_input", "verdict": "GREEN"},
            timestamp="2026-01-01T00:00:00Z",
        )
        records = log.read_all()
        assert records[0].metadata["gate"] == "dlp_input"

    def test_read_empty_file(self):
        path = self._tmp_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        log = WORMAuditLog(path)
        assert log.length == 0
        assert log.read_all() == []


# ─────────────────────────────────────────────
# verify_chain
# ─────────────────────────────────────────────

class TestVerifyChain:
    def test_empty_chain_is_valid(self):
        result = verify_chain([])
        assert result.valid is True
        assert result.total_records == 0

    def test_valid_chain(self):
        log = WORMAuditLog(Path(tempfile.mkdtemp()) / "audit.jsonl")
        for i in range(5):
            log.append(f"evt.{i}", "system", f"t{i}", timestamp=f"2026-01-01T00:0{i}:00Z")
        records = log.read_all()
        result = verify_chain(records)
        assert result.valid is True
        assert result.total_records == 5
        assert result.verified_records == 5

    def test_tampered_record_hash(self):
        log = WORMAuditLog(Path(tempfile.mkdtemp()) / "audit.jsonl")
        log.append("evt.a", "actor", "t1", timestamp="2026-01-01T00:00:00Z")
        log.append("evt.b", "actor", "t2", timestamp="2026-01-01T00:01:00Z")
        log.append("evt.c", "actor", "t3", timestamp="2026-01-01T00:02:00Z")

        records = log.read_all()
        # Adultera o hash do registro 1
        records[1].record_hash = "f" * 64

        result = verify_chain(records)
        assert result.valid is False
        assert result.first_broken_at == 1
        assert "adulterado" in result.error

    def test_tampered_prev_hash(self):
        log = WORMAuditLog(Path(tempfile.mkdtemp()) / "audit.jsonl")
        log.append("evt.a", "actor", "t1", timestamp="2026-01-01T00:00:00Z")
        log.append("evt.b", "actor", "t2", timestamp="2026-01-01T00:01:00Z")

        records = log.read_all()
        # Adultera o prev_hash do registro 1
        records[1].prev_hash = "0" * 64

        result = verify_chain(records)
        assert result.valid is False
        assert result.first_broken_at == 1
        assert "prev_hash" in result.error

    def test_broken_sequence(self):
        log = WORMAuditLog(Path(tempfile.mkdtemp()) / "audit.jsonl")
        log.append("evt.a", "actor", "t1", timestamp="2026-01-01T00:00:00Z")
        log.append("evt.b", "actor", "t2", timestamp="2026-01-01T00:01:00Z")

        records = log.read_all()
        # Pula a sequência
        records[1].sequence = 5

        result = verify_chain(records)
        assert result.valid is False
        assert "sequência" in result.error

    def test_deleted_record_detected(self):
        """Deletar um registro do meio quebra a cadeia."""
        log = WORMAuditLog(Path(tempfile.mkdtemp()) / "audit.jsonl")
        log.append("evt.a", "actor", "t1", timestamp="2026-01-01T00:00:00Z")
        log.append("evt.b", "actor", "t2", timestamp="2026-01-01T00:01:00Z")
        log.append("evt.c", "actor", "t3", timestamp="2026-01-01T00:02:00Z")

        records = log.read_all()
        # Remove o registro do meio
        del records[1]

        result = verify_chain(records)
        assert result.valid is False

    def test_verification_result_to_dict(self):
        result = VerificationResult(
            valid=True, total_records=10, verified_records=10,
        )
        d = result.to_dict()
        assert d["valid"] is True
        assert d["total_records"] == 10
        assert d["first_broken_at"] is None


# ─────────────────────────────────────────────
# Integration: Schema + Audit
# ─────────────────────────────────────────────

class TestSchemaAuditIntegration:
    def test_contract_audit_flags_control_worm(self):
        """PersonaContract.audit flags determinam se WORM deve ser usado."""
        contract = get_builtin_contract("maia-orchestrator")
        assert contract.audit.worm_enabled is True
        assert contract.audit.evidence_hash_chain is True

    def test_gate_results_auditable(self):
        """Resultados de gates podem ser registrados no audit trail."""
        log = WORMAuditLog(Path(tempfile.mkdtemp()) / "audit.jsonl")
        contract = get_builtin_contract("maia-orchestrator")

        # Simula resultado de cada gate pre_mission
        for gate_name in contract.quality_gates.pre_mission:
            log.append(
                event_type=f"gate.{gate_name}",
                actor=contract.persona_id,
                trace_id="mission-trace-001",
                payload={"verdict": "GREEN", "gate": gate_name},
                metadata={"persona": contract.persona_id},
                timestamp="2026-01-01T00:00:00Z",
            )

        records = log.read_all()
        assert len(records) == len(contract.quality_gates.pre_mission)
        result = verify_chain(records)
        assert result.valid is True
