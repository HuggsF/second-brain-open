# Spec — MCP Ontology Upgrade + ETL Preditivo + Visualizações

**Demanda:** MCP Ontology Upgrade  
**Data:** 2026-10-21  
**Fase:** 2 (Spec)  
**Fonte:** `handoff-discovery.md`, ADRs 005, 014, notas de ontologia

---

## 0. Decisões Assumidas (§10-11 do Handoff)

| # | Questão | Decisão (recomendação aceita) |
|---|---|---|
| 1 | `resolve_ontology_term` matching | **Fuzzy** — substring case-insensitive + score de similaridade |
| 2 | `list_bounded_contexts` fonte | **Estático** — parseia `hub-mapa-entidades-dominios.md` |
| 3 | RULE-003..005 escopo | **Confirmado** — conferência NF-e, race condition, objeto Bling |
| 4 | `search_knowledge_base` include_content | **Default false** — backward compat; opt-in com `include_content=true` |
| 5 | Re-indexação | **`cli.py sync --force`** após alterar chunker |
| 6 | GAP-5 (lint de código) | **Fora do escopo v1** |
| 7 | Pipeline ETL extração | **SSH** (reutiliza infraestrutura do `observe_hub`) |
| 8 | Séries temporais | **SQLite local** (`second-brain/data/analytics.db`) |
| 9 | Tools preditivos | **Cálculo estatístico simples** (sem ML/Ollama no v1) |
| 10 | Visualizações | **Tab nova** no dashboard existente |
| 11 | 74 invariantes | **Documento consolidado** (`vault/systems/hub-regras-operacionais-codex.md`) |
| 12 | 10 docs faltantes | **Ingestão na fase de Execução** (tickets verticais) |

---

## 1. Escopo e Fronteiras

### 1.1 Está no escopo (v1)

1. **Eixo 1 — Ontologia:** 3 tools novos + 2 melhorados + 3 regras + chunks enriquecidos
2. **Eixo 2 — Regras Operacionais:** 2 tools novos + documento consolidado + ingestão de 10 docs
3. **Eixo 3 — ETL + Análise Estatística:** pipeline de extração + SQLite analytics + 5 tools + tab dashboard

### 1.2 Fora do escopo

- GAP-5: lint de aderência de código à ontologia
- Modelos ML / Ollama para predição
- Reconciliação automática de emissões `uncertain` (DEM-15)
- Resolução de DEM-09, 10, 12, 13, 16 (pendências do Hub, não do MCP)
- Alterações no código de produção do Hub

---

## 2. Contratos dos Novos Tools MCP

### 2.1 `resolve_ontology_term(term, task_id?)`

```python
@mcp.tool()
def resolve_ontology_term(term: str, task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Dado um nome de classe, entidade ou campo (atual ou proposto),
    retorna o mapeamento ontológico completo.
    Busca fuzzy (substring case-insensitive) no registro de ontologia.
    Fonte: vault/systems/hub-ontologia-ddd-proposta.md
    """
```

**Input:** `term` — qualquer string (ex: `"Order"`, `"DispatchJob"`, `"ErpPort"`, `"UniversalPayload"`)  
**Output:**
```json
{
  "matches": [
    {
      "current_name": "Order",
      "proposed_name": "DispatchJob",
      "nature": "Modelo operacional: reserva, estado e tentativas. Não é a venda.",
      "bounded_context": "Expedição e Remessas",
      "category": "entity",
      "source": "hub-ontologia-ddd-proposta.md",
      "status": "proposta"
    }
  ],
  "total": 1,
  "ontology_status": "proposta para revisão"
}
```

**Invariantes:**
- Retorna lista vazia se nenhum match (nunca erro)
- Busca em `current_name`, `proposed_name` e aliases
- Case-insensitive, substring match
- Máximo 10 resultados

### 2.2 `list_bounded_contexts(task_id?)`

```python
@mcp.tool()
def list_bounded_contexts(task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lista os 5 bounded contexts do Hub Logístico com entidades,
    use cases e portas de cada um.
    Fonte: vault/systems/hub-mapa-entidades-dominios.md
    """
```

**Output:**
```json
[
  {
    "id": "bc-pedidos",
    "name": "Pedidos e Qualificação Comercial",
    "description": "Identificar a venda, canal, loja, itens e situação.",
    "entities": ["SalesOrderSnapshot", "RecipientSnapshot"],
    "use_cases": ["HandleBlingWebhookUseCase", "ManualEnqueueUseCase"],
    "ports": ["SalesOrderReaderPort"],
    "implementations_js": ["shippingPolicy.js", "findOrderForInvoice"],
    "implementations_ts": ["ShippingPolicy", "UniversalPayload"]
  }
]
```

**Invariantes:**
- Sempre retorna exatamente 5 BCs (hardcoded pela ontologia)
- Parseia markdown no boot, cacheia em memória

### 2.3 `list_domain_entities(bounded_context?, task_id?)`

```python
@mcp.tool()
def list_domain_entities(bounded_context: Optional[str] = None, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lista entidades do domínio, opcionalmente filtradas por bounded context.
    Mostra nome atual, proposto, identidade e relações.
    """
```

**Output:** Lista de entidades com campos: `current_name`, `proposed_name`, `identity`,
`bounded_context`, `nature`, `related_ports`, `related_use_cases`

### 2.4 `list_operational_rules(category?, task_id?)`

```python
@mcp.tool()
def list_operational_rules(category: Optional[str] = None, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Lista as invariantes operacionais do Hub documentadas pelo Codex.
    Categorias: 'emission', 'preflight', 'nfe', 'recovery', 'weight',
    'monitor', 'logging', 'deploy'. Sem filtro lista todas.
    Fonte: vault/systems/hub-regras-operacionais-codex.md
    """
```

**Output:** Lista com `id`, `description`, `category`, `source_doc`, `source_branch`, `dem_ref` (se aplicável)

### 2.5 `get_rule_details(rule_id, task_id?)`

```python
@mcp.tool()
def get_rule_details(rule_id: str, task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Retorna detalhes completos de uma invariante operacional pelo ID.
    IDs: INV-01..19, PREFLIGHT-01..07, NFE-01..13, RECOVERY-01..07,
    WEIGHT-01..09, QMON-01..06, LOG-01..05, DEPLOY-01..08.
    """
```

**Output:** `id`, `description`, `full_text`, `category`, `source_doc`, `source_branch`,
`related_code`, `dem_ref`, `evidence_methodology`

### 2.6 `search_knowledge_base` v2 (backward-compatible)

```python
@mcp.tool()
def search_knowledge_base(
    query: str,
    category: Optional[str] = None,
    bounded_context: Optional[str] = None,
    include_content: bool = False,
    task_id: Optional[str] = None
) -> List[Dict[str, Any]]:
```

**Mudanças:**
- `bounded_context`: filtro opcional no Qdrant (novo payload field)
- `include_content`: se True, inclui `content` no resultado (default False = backward compat)
- Resultado enriquecido: `doc_type`, `status`, `related`, `bounded_context` nos metadados

### 2.7 `get_system_architecture` v2

Apenas atualizar docstring:
```python
"""
Recupera a documentação técnica de um sistema ou nota do vault/systems/.
Existem 46+ notas. Use get_brain_status para ver a contagem total.
"""
```

### 2.8 Tools de Análise Estatística (ETL)

> **Nota de revisão (Phase 5 Review):** Os tools originalmente especificados como
> `predict_failure_risk`, `throughput_forecast`, `api_health_score` e `store_performance`
> foram refinados durante a execução com base nas decisões de design aprovadas pelo usuário:
> - Decisão #9: "Cálculo estatístico simples (sem ML/Ollama no v1)"
> - A abordagem per-order/per-store risk scoring foi descoped em favor de análise agregada por período
> - Os nomes e assinaturas foram ajustados para refletir o que o ETL realmente entrega

#### `etl_run(days?, environment?)`
```python
@mcp.tool()
def etl_run(
    days: int = 7,
    environment: str = "production",
    task_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executa o pipeline ETL: extrai dados agregados do Hub Logístico via SSH
    e armazena localmente. Não armazena PII (NEG-03). Não altera o Hub (NEG-02).
    days: janela de extração (1-90). environment: 'production' ou 'hml'.
    """
```

**Output:** `extracted_at`, `environment`, `tables` (contagem de rows por tabela)

#### `predict_emission_trends(days?)`
```python
@mcp.tool()
def predict_emission_trends(
    days: int = 30,
    task_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analisa tendências de emissão dos últimos N dias e projeta volume do dia seguinte.
    Retorna médias, taxa de sucesso/falha, tendência (increasing/stable/decreasing)
    e dados diários. Requer ETL prévio (etl_run).
    """
```

**Output:**
```json
{
  "period": {"start": "2026-09-21", "end": "2026-10-21", "days": 30},
  "summary": {
    "avg_daily_orders": 45.2,
    "avg_success_rate": 87.3,
    "avg_failure_rate": 8.1,
    "total_reviews": 12
  },
  "trend": {
    "direction": "stable",
    "daily_change": 0.15,
    "projected_next_day": 46
  },
  "daily_data": [{"date": "2026-10-20", "total": 48, "success": 42, "failed": 4, "review": 2}]
}
```

#### `analyze_error_patterns(days?)`
```python
@mcp.tool()
def analyze_error_patterns(
    days: int = 14,
    task_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analisa padrões de erro (RATE_LIMIT, TIMEOUT, REVIEW_REQUIRED, UNCERTAIN_STATE,
    CANCELLATION) dos últimos N dias. Identifica o problema mais frequente.
    Requer ETL prévio.
    """
```

**Output:** `period_days`, `by_type` (lista com type/total/last_seen), `daily_trend`, `top_issue`

#### `analyze_throughput(days?)`
```python
@mcp.tool()
def analyze_throughput(
    days: int = 7,
    task_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analisa throughput por hora do dia, identifica pico e vale de operação,
    sugere janela de manutenção. Requer ETL prévio.
    """
```

**Output:** `period_days`, `hourly_avg`, `peak` (hour + avg_emissions), `low`, `recommended_maintenance_window`

#### `analyze_logistics_health(days?)`
```python
@mcp.tool()
def analyze_logistics_health(
    days: int = 14,
    task_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analisa saúde do objeto logístico: cobertura, LOGISTICS_OBJECT_MISSING
    e MULTIPLE_VOLUMES. Requer ETL prévio.
    """
```

**Output:** `period_days`, `summary` (logistics_coverage_pct, total_missing_reviews, total_multi_volume_reviews), `daily`

---

## 3. Módulos de Infraestrutura

### 3.1 Ontology Parser (`core/ontology.py`)

Novo módulo que parseia as notas de ontologia do vault:
- Lê `hub-ontologia-ddd-proposta.md` → extrai tabelas Markdown → registra entidades, campos, ports, use cases
- Lê `hub-mapa-entidades-dominios.md` → extrai bounded contexts com entidades
- Cacheia em memória (dict), re-parseia se file mtime mudar
- Sem dependência do Qdrant (leitura estática)

### 3.2 Operational Rules Parser (`core/operational_rules.py`)

Novo módulo que parseia o documento consolidado de regras:
- Lê `hub-regras-operacionais-codex.md` → extrai tabelas → registra 74 invariantes
- Cacheia em memória, re-parseia se mtime mudar
- Sem dependência do Qdrant

### 3.3 Analytics ETL (`core/analytics_etl.py`)

Novo módulo para extração e transformação de dados do Hub:
- **Extração:** via SSH (reutiliza `_ssh_exec` de `hub_observability_mcp.py`)
- **Comando remoto:** `sqlite3 /path/to/hub.db "SELECT ... " -json`
- **Queries de extração:**
  - `orders_queue`: status distribution, retry counts, error patterns, timestamps
  - `system_logs`: sucesso count, erro clustering, integration traces
  - `jt_emissions`: uncertain/confirmed ratio
  - `order_bling_status`: revenue by store, lifecycle velocity
- **Transformação:** cálculos estatísticos em Python (numpy-free, stdlib only):
  - Moving averages, percentiles, z-scores
  - Retry velocity = retries / age_hours
  - Error clustering = GROUP BY error pattern
  - Throughput = success count / time window
- **Armazenamento:** SQLite local (`second-brain/data/analytics.db`)
  - Tabelas: `etl_snapshots`, `etl_metrics`, `etl_predictions`
  - Retenção: 30 dias de snapshots

### 3.4 Chunker Enrichment (`core/chunker.py` — alteração)

Adicionar campos ao metadata dos chunks:
```python
extra = {
    "status": front.get("status"),
    "doc_type": front.get("type"),
    "related": front.get("related", []),       # NOVO
    "bounded_context": front.get("bounded_context"),  # NOVO (se presente no frontmatter)
    "entities": front.get("entities", []),      # NOVO (se presente no frontmatter)
}
```

Após alteração, executar `cli.py sync --force` para re-indexar todos os 1398+ vetores.

---

## 4. Documentos do Vault (a criar)

### 4.1 `vault/systems/hub-regras-operacionais-codex.md`
Documento consolidado com as 74 invariantes, organizadas por categoria, com:
- Frontmatter: `type: system, status: active, date: 2026-10-21`
- Tabela por grupo (INV, PREFLIGHT, NFE, etc.)
- Referência ao documento-fonte e branch
- DEM-NN linkados
- Non-assumptions do Codex

### 4.2 10 Docs Faltantes (ingestão durante Execução)
Cada doc fonte do hub-logistico será sintetizado numa nota vault/systems/ seguindo ADR-014.

### 4.3 RULE-003, RULE-004, RULE-005 + Playbooks
```yaml
# RULE-003
id: RULE-003
title: Conferência NF-e obrigatória antes de despacho automático
status: active
source: vault/systems/hub-gatilho-nfe-e-politicas-de-emissao.md
domain: logistica

# RULE-004
id: RULE-004
title: Emissão protegida contra race condition (mutex/lock atômico)
status: active
source: vault/systems/protecoes-processamento-emissao-hub.md
domain: logistica

# RULE-005
id: RULE-005
title: Objeto logístico Bling deve existir antes de emissão
status: active
source: vault/systems/hub-regras-operacionais-codex.md (PREFLIGHT-01)
domain: logistica
```

Playbooks correspondentes: PB-014, PB-015, PB-016.

---

## 5. Invariantes Negativos (o que a solução NUNCA pode fazer)

| # | Invariante | Verificável por |
|---|---|---|
| NEG-01 | Tools de ontologia NUNCA alteram arquivos do vault (read-only) | Teste: mock filesystem, assert no writes |
| NEG-02 | Tools preditivos NUNCA executam comandos no Hub que alterem estado | Teste: assert all SSH commands are SELECT |
| NEG-03 | Pipeline ETL NUNCA armazena dados de PII (nome, CPF, email, telefone) | Teste: regex scan no analytics.db |
| NEG-04 | `search_knowledge_base` com `include_content=false` NUNCA retorna `content` | Teste: assert key absent |
| NEG-05 | Novos parâmetros NUNCA quebram chamadas existentes (backward compat) | Teste: chamar sem novos params |
| NEG-06 | Re-indexação NUNCA apaga vetores sem re-inserir | Teste: count antes/depois de sync |
| NEG-07 | Tools preditivos NUNCA inventam dados quando SSH falha | Teste: mock SSH failure → erro explícito |
| NEG-08 | Documento de regras operacionais NUNCA presume invariantes não documentadas pelo Codex | Review: comparar 1:1 com fontes |
| NEG-09 | ETL NUNCA faz mais de 1 SSH connection por ciclo de coleta | Teste: count connections |
| NEG-10 | Dashboard NUNCA faz requests ao Hub diretamente (só via BFF/analytics.db) | Teste: network audit |

---

## 6. Bordas e Edge Cases

### 6.1 Concorrência
- ETL scheduler e MCP tool podem acessar `analytics.db` simultaneamente → usar WAL mode
- Múltiplos agentes chamando tools de ontologia → sem problema (read-only, cached)

### 6.2 Timeouts
- SSH para extração ETL: timeout 30s (mesmo que observe_hub)
- Se SSH falha, tools preditivos retornam `{"error": "DATA_UNAVAILABLE", "last_valid": "..."}` com último dado válido

### 6.3 Nulos
- `bounded_context` filter nulo → sem filtro (retorna tudo)
- `resolve_ontology_term("")` → retorna lista vazia
- Store sem dados → `store_performance` retorna `{"error": "NO_DATA"}`

### 6.4 Reprocessamento
- `sync --force` é idempotente (delete + re-insert por file_path)
- ETL snapshots são append-only com timestamp; re-run não duplica

---

## 7. Plano de Arquivos

### Novos
| Arquivo | Tipo | Escopo |
|---|---|---|
| `core/ontology.py` | Módulo | Parser de ontologia |
| `core/operational_rules.py` | Módulo | Parser de regras operacionais |
| `core/analytics_etl.py` | Módulo | Pipeline ETL + armazenamento |
| `vault/systems/hub-regras-operacionais-codex.md` | Nota | 74 invariantes consolidadas |
| `vault/rules/RULE-003*.md` | Regra | Conferência NF-e |
| `vault/rules/RULE-004*.md` | Regra | Race condition emissão |
| `vault/rules/RULE-005*.md` | Regra | Objeto logístico Bling |
| `vault/playbooks/PB-014*.md` | Playbook | Validação RULE-003 |
| `vault/playbooks/PB-015*.md` | Playbook | Validação RULE-004 |
| `vault/playbooks/PB-016*.md` | Playbook | Validação RULE-005 |
| `dashboard/analytics-panel.js` | UI | Painel ETL/Analytics |
| `dashboard/rules-panel.js` | UI | Semáforo de regras operacionais |
| `data/analytics.db` | DB | Séries temporais (gitignored) |
| 10× `vault/systems/hub-*.md` | Notas | Docs faltantes ingeridos |

### Alterados
| Arquivo | Alteração |
|---|---|
| `mcp_servers/brain_mcp.py` | +7 tools, docstring atualizada |
| `core/chunker.py` | +3 campos metadata (related, bounded_context, entities) |
| `core/qdrant_store.py` | +filtro `bounded_context` no search |
| `core/retriever.py` | +param `bounded_context`, `include_content` |
| `cli.py` | +comando `etl` |
| `dashboard/index.html` | +tab Analytics, +tab Rules |
| `dashboard/app.js` | +routing para novos painéis |
| `.gitignore` | +`data/analytics.db` |

### Não-tocados (No-Touch)
| Arquivo | Razão |
|---|---|
| `core/evidence.py` | Não é afetado — regras operacionais são separadas do evidence tree |
| `core/evidence_store.py` | Não é afetado |
| `backend/*` | BFF do dashboard — não alterado nesta iteração |
| `mcp_servers/hub_observability_mcp.py` | Reutiliza `_ssh_exec` mas não é alterado |
| `mcp_servers/github_gateway_mcp.py` | Sem relação |
| `mcp_servers/srv_api_gateway_mcp.py` | Sem relação |
| Código do hub-logistico | Saldo +0/-0 em produção |

---

## 8. Critérios de Aceite por Eixo

### Eixo 1 (Ontologia)
- `resolve_ontology_term("Order")` retorna `DispatchJob` com BC e natureza
- `list_bounded_contexts()` retorna 5 itens com entidades
- `search_knowledge_base("emissão", bounded_context="fiscal")` filtra corretamente
- Chunks re-indexados com metadata enriquecida (+related, +bounded_context)

### Eixo 2 (Regras Operacionais)
- `list_operational_rules()` retorna 74 itens
- `list_operational_rules("preflight")` retorna 7 itens
- `get_rule_details("INV-01")` retorna texto completo com fonte
- Documento consolidado no vault com frontmatter ADR-014
- RULE-003..005 e PB-014..016 criados e lint-free

### Eixo 3 (ETL + Análise Estatística)
- `etl_run(7)` extrai dados do Hub via SSH (1 conexão por ciclo — NEG-09)
- `predict_emission_trends(30)` retorna tendência e projeção do próximo dia
- `analyze_error_patterns(14)` identifica tipo de erro mais frequente
- `analyze_throughput(7)` identifica peak/low hours e sugere janela de manutenção
- `analyze_logistics_health(14)` retorna cobertura logística e reviews pendentes
- Dashboard tab Analytics renderiza série temporal
- Dashboard tab Rules renderiza semáforo das 74 invariantes
- `data/analytics.db` populado via ETL com retenção 30 dias
- NEG-02 e NEG-03 verificados (sem PII, sem writes no Hub)
- NEG-09 verificado (1 SSH connection por ciclo ETL)
