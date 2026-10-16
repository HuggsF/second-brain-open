# Especificação — UI/UX Roadmap Second Brain (Fase 1: Higienização)

> **Fase:** 2 — Spec Gate  
> **Data:** 16/10/2026  
> **Escopo:** Fase 1 do Roadmap UI/UX (Higienização & Alinhamento Visual)  
> **Evidence:** [2026-10-16-uiux-roadmap-evidence.md](file:///c:/KIOSK/second-brain/docs/superpowers/evidence/2026-10-16-uiux-roadmap-evidence.md)  
> **PD-OVRs vigentes:** PD-OVR-001 a PD-OVR-006

---

## 1. Objetivo

Executar a Fase 1 do Roadmap UI/UX: **eliminar código morto, unificar personas de IA entre frontends e consolidar features duplicadas**. Preparar a base para integrações cross-app da Fase 2.

---

## 2. Invariantes Negativos (Proibições Explícitas)

1. **INV-01**: É proibido alterar a lógica de negócio dos agentes (simulação, reducer, protocolo WS). Este escopo é puramente de UI/UX e limpeza.
2. **INV-02**: É proibido remover testes existentes. Testes podem ser adicionados ou atualizados, nunca deletados.
3. **INV-03**: É proibido alterar o DESIGN.md do Dashboard. Ele é fonte-de-verdade. O Nexus deve oferecer tema compatível como **opção**, não como substituição do tema cyberpunk.
4. **INV-04**: É proibido alterar APIs do backend Python. Escopo é exclusivamente frontend.
5. **INV-05**: É proibido quebrar os testes que atualmente passam (82 Nexus, 178 Dashboard, 118 JEV).

---

## 3. Itens de Escopo

### 3.1 Limpeza de Código Morto (CLEAN)

| ID | Descrição | Arquivos Alvo | Critério de Aceite |
|----|-----------|--------------|-------------------|
| CLEAN-01 | Remover `phaser` do `package.json` do Nexus | `nexus/package.json` | `npm ls phaser` → not found |
| CLEAN-02 | Remover `zustand` do `package.json` do Nexus | `nexus/package.json` | `npm ls zustand` → not found. `grep -r "zustand" nexus/src/` → 0 |
| CLEAN-03 | Mover `nexus/src/game/` para `nexus/src/_archived_game/` | `nexus/src/game/*` | Pasta `game/` não existe mais em `src/`. Pasta `_archived_game/` existe. Testes passam (82/84) |
| CLEAN-04 | Limpar referências mortas no `agent-arena.js`: renomear personas genéricas para as 5 canônicas | `dashboard/agent-arena.js` | `grep -c "Maia\|Noah\|Theo\|Lia\|Eva" dashboard/agent-arena.js` ≥ 5. Personas genéricas removidas |

### 3.2 Unificação Visual (VISUAL)

| ID | Descrição | Arquivos Alvo | Critério de Aceite |
|----|-----------|--------------|-------------------|
| VISUAL-01 | Criar arquivo de tema orgânico `nexus/src/theme-organic.css` com tokens do DESIGN.md (`#101513`, `#b8f37b`, system-ui) | `nexus/src/theme-organic.css` (novo) | Arquivo existe com as variáveis CSS mapeadas do DESIGN.md |
| VISUAL-02 | Adicionar alternador de tema no Header do Nexus (cyberpunk ↔ orgânico) com persistência em `localStorage` | `nexus/src/components/Header.jsx`, `nexus/src/App.jsx` ou `context.jsx` | Botão visível no Header. Clique alterna `data-theme` no `<html>`. Reload preserva escolha |
| VISUAL-03 | Unificar personas da Agent Arena com as 5 canônicas do Nexus | `dashboard/agent-arena.js` | Mesmos nomes, roles e cores que `nexus/src/simulation.mjs` |

### 3.3 Consolidação de Duplicatas (DEDUP)

| ID | Descrição | Arquivos Alvo | Critério de Aceite |
|----|-----------|--------------|-------------------|
| DEDUP-01 | Aba Playbooks do Dashboard redireciona para JEV (embed ou link) ao invés de UI própria | `dashboard/app.js`, `dashboard/playbooks-ui.js` | Clicar em "Playbooks" no nav do Dashboard mostra a experiência do JEV, não o `playbooks-ui.js` |
| DEDUP-02 | Reorganizar nav do Dashboard: agrupar 12 itens em categorias (Conhecimento, Operação, Agentes) | `dashboard/app.js` | Nav tem ≤ 6 itens de primeiro nível com sub-menus expansíveis |

---

## 4. Casos de Borda e Riscos

| Caso | Mitigação |
|------|-----------|
| Remoção de Phaser/Zustand pode quebrar `npm install` se há peer deps | Rodar `npm install && npm test` após remoção |
| Arquivo `_archived_game/` pode ser commitado com binários grandes | Verificar que não há assets > 1MB na pasta |
| Tema orgânico pode conflitar com estilos inline do cyberpunk | Usar CSS custom properties com fallback no `:root` |
| Agent Arena usa indices numéricos para personas, não nomes | Mapear cada índice para persona canônica, manter backward compat |
| Nav do Dashboard com sub-menus pode quebrar keyboard nav | Testar com Tab/Enter/Escape. Dashboard já tem a11y excelente |

---

## 5. Fora de Escopo (Fase 2+ do Roadmap)

- Barramento unificado de eventos (BUS-01 → Fase 2)
- Substituição de iframes por postMessage (BUS-02 → Fase 2)
- Tool Call Visualizer, streaming de raciocínio (MON-01/02 → Fase 2)
- Execução real de playbooks no JEV (EXEC-01 → Fase 2)
- HITL com feedback granular (HITL-01 → Fase 3)
- Fluxo Spec→Evidence integrado (FLOW-01 → Fase 3)

---

*Spec gerada a partir de evidências materiais 3D. Aguarda aprovação humana antes do plano.*
