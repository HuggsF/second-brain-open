# SDD-004 — Nexus Frontend ↔ Python Domain Contract

**Status:** active  
**Versão:** 1.0  
**Revisado em:** 2026-10-13  
**Implementação:** `scripts/generate_nexus_entities.py`  
**Arquivo gerado:** `nexus/src/generated/nexus-entities.json`  
**Teste de contrato:** `nexus/tests/contract-entities.test.mjs`

---

## 1. Propósito

Definir e manter o contrato entre as constantes do frontend Nexus (JavaScript) e as entidades de domínio do backend Python, garantindo que nunca divirjam silenciosamente.

---

## 2. Arquitetura de Sincronização

```
core/domain/nexus/entities.py       (fonte de verdade Python)
          ↓ scripts/generate_nexus_entities.py
nexus/src/generated/nexus-entities.json   (bridge file, versionado)
          ↓ importado por
nexus/src/scene/constants3d.js      (constantes visuais 3D)
nexus/src/simulation.mjs            (simulação offline)
          ↓ verificado por
nexus/tests/contract-entities.test.mjs   (teste de contrato)
```

---

## 3. Campos Canônicos vs. Aliases JS

Para compatibilidade retroativa sem breaking changes:

### Agentes (`AGENT_ROLES`)

| Campo Python (`entities.py`) | Campo JS (`constants3d.js`) | Valor exemplo |
|---|---|---|
| `name` | `label` | `"Maia"` |
| `label` | `role` | `"Orquestradora"` |
| `room` | `roomId` | `"orchestrator"` |
| `color` | `color` | `"#ff007f"` |

### Salas (`ROOMS`)

| Campo Python (`entities.py`) | Campo JS (`constants3d.js`) | Notas |
|---|---|---|
| `size: [w, h, d]` | `size: [w, d]` | JS usa XZ (floor plane); h ignorado |
| `position: [x, y, z]` | `position: [x, y, z]` | Idêntico |
| `colorKey` | `colorKey` | Idêntico |

---

## 4. Processo de Atualização

Quando `core/domain/nexus/entities.py` for modificado:

```bash
# 1. Atualizar entities.py
# 2. Regenerar o JSON
python scripts/generate_nexus_entities.py

# 3. Verificar o contrato
node --test nexus/tests/contract-entities.test.mjs

# 4. Se constantes3d.js divergir, atualizar o JS ou o entities.py
# 5. Commitar entities.py + nexus-entities.json juntos
```

---

## 5. Invariantes de Contrato

| Invariante | Verificado em |
|---|---|
| Todos os roles em `entities.py` existem em `AGENT_CONFIGS` | `contract-entities.test.mjs` |
| `AGENT_CONFIGS` não tem roles extras | `contract-entities.test.mjs` |
| Cores dos agentes idênticas | `contract-entities.test.mjs` |
| `roomId` == `room` | `contract-entities.test.mjs` |
| Nomes dos agentes (`label`/`name`) idênticos | `contract-entities.test.mjs` |
| Todas as salas em `entities.py` existem em `ROOM_CONFIGS` | `contract-entities.test.mjs` |
| Posições e tamanhos XZ idênticos | `contract-entities.test.mjs` |
| `STATUS_EMISSIVE` cobre todos os `AGENT_STATUSES` | `contract-entities.test.mjs` |
| Todas as cores de status são hex `#RRGGBB` | `contract-entities.test.mjs` |

---

## 6. Arquivos Versionados

| Arquivo | Editar manualmente? | Regenerar quando? |
|---|---|---|
| `core/domain/nexus/entities.py` | ✅ Sim | — |
| `nexus/src/generated/nexus-entities.json` | ❌ Nunca | Após qualquer mudança em `entities.py` |
| `nexus/src/scene/constants3d.js` | ✅ Sim (visual 3D) | Divergência detectada pelo teste de contrato |
| `nexus/tests/contract-entities.test.mjs` | ✅ Sim | Novos campos no contrato |
