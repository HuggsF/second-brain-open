"""Workflow domain constants — canonical mission patterns and agent mappings.

These constants define the shared vocabulary for mission planning between:
- core.graph.nodes (Node Loop Graph plan_node)
- backend.orchestrator (legacy Orchestrator._match_pattern)

Do NOT import any I/O, HTTP, or WebSocket libraries here.
This module has zero dependencies outside the standard library.
"""

__all__ = [
    "AGENT_PERSONA_MAP",
    "DEFAULT_STEPS",
    "MISSION_PATTERNS",
]

# Sprint 7: Mapeamento de agentes Nexus → PersonaContract IDs
# Ativa o pipeline de integração MoE/Zero-Trust por persona
AGENT_PERSONA_MAP = {
    "manager": "maia-orchestrator",
    "reviewer": "eva-supervisor",
    "researcher": "persona-researcher",   # GAP-10: novo builtin (task-14)
    "coder": "persona-devops",            # reuse de persona existente
    "writer": "persona-writer",           # GAP-10: novo builtin (task-14)
}

# Padrões de missão → steps (regras fixas, sem LLM)
MISSION_PATTERNS = [
    {
        "keywords": ["diagnosticar", "failed", "fila", "sistema", "pedido", "erro"],
        "steps": [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": ""}, "bubble": "Buscando documentação relevante..."},
            {"agent": "coder", "tool": "get_system_architecture", "input": {"system_name": "example-system"}, "bubble": "Lendo estados e regras do sistema..."},
            {"agent": "reviewer", "tool": "list_rules", "input": {}, "bubble": "Verificando regras de negócio..."},
        ],
    },
    {
        "keywords": ["playbook", "pb-", "procedimento", "protocolo"],
        "steps": [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": ""}, "bubble": "Localizando playbooks..."},
            {"agent": "reviewer", "tool": "list_rules", "input": {}, "bubble": "Cruzando com regras de negócio..."},
        ],
    },
    {
        "keywords": ["adr", "decisão", "arquitetura", "trade-off"],
        "steps": [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": ""}, "bubble": "Buscando ADRs relevantes..."},
        ],
    },
    {
        "keywords": ["oauth", "token", "provedor", "autenticação"],
        "steps": [
            {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": "oauth provedor token"}, "bubble": "Buscando doc de OAuth..."},
            {"agent": "coder", "tool": "get_system_architecture", "input": {"system_name": "example-system"}, "bubble": "Lendo schema do sistema..."},
        ],
    },
    {
        "keywords": ["status", "saúde", "health", "qdrant", "brain"],
        "steps": [
            {"agent": "coder", "tool": "get_brain_status", "input": {}, "bubble": "Verificando status do Qdrant..."},
        ],
    },
]

# Fallback: busca genérica
DEFAULT_STEPS = [
    {"agent": "researcher", "tool": "search_knowledge_base", "input": {"query": ""}, "bubble": "Pesquisando no vault..."},
]
