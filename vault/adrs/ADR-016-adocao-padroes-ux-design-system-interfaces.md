---
type: adr
status: proposed
date: 2026-10-13
---
# ADR-016: Adoção de Padrões de UX e Design System para Interfaces KIOSK

## Contexto

A equipe KIOSK Brands opera no modelo **Full-Cycle Developer** com 2 pessoas e **sem designer dedicado**. As interfaces produzidas (Second Brain Dashboard, Análise 360, CRM HGGS) são funcionais mas carecem de padronização visual e raciocínio de UX formal.

Uma análise de discovery do produto **UX Engine** (designmotionhq.com) revelou que **4 de 8 capacidades de design** não são cobertas por nenhum time KIOSK, e as 4 restantes são cobertas apenas parcialmente:

| Capacidade | Status Atual |
|---|---|
| Intent Discovery | 🔴 Não coberto |
| Information Hierarchy | 🔴 Não coberto |
| State Completeness | 🟡 Parcial (hub-logístico) |
| Form UX | 🟡 Parcial (caso a caso) |
| Feedback & Affordance | 🟡 Parcial (issues UX-01/02) |
| UX Auditor | 🟡 Parcial (QA funcional, não visual) |
| Design System | 🔴 Não coberto |
| Visual Character | 🔴 Não coberto |

Issues abertas no frontend: UX-01 (navegação por relação), UX-02 (troca de vista com zero resultados), MOB-01, A11Y-01.

## Decisão

Adotar formalmente 8 princípios de UX como **skill de agente** e documentar o **design system** do Second Brain Dashboard:

1. **Criar skill `ux-engine-kiosk`** em `.agents/skills/` para ser carregado automaticamente por agentes Antigravity ao tocarem UI.

2. **Criar `DESIGN.md`** na raiz do dashboard com tokens extraídos do `style.css` existente, servindo como fonte de verdade para paleta, tipografia, espaçamento, componentes e breakpoints.

3. **Os 8 princípios** (Intent Discovery, Information Hierarchy, State Completeness, Form UX, Feedback & Affordance, UX Auditor, Design System, Visual Character) devem ser consultados antes de qualquer modificação de interface.

4. **Não comprar ferramentas externas** neste momento. Os conceitos são universais e foram internalizados como skills próprios, evitando dependência de vendor e incompatibilidade de plataforma (UX Engine é Claude Code, nós usamos Antigravity/Gemini).

## Consequências

### Positivas
- Agentes de IA passam a ter guia formal de UX ao gerar/alterar interfaces
- Design System documentado permite consistência entre telas e entre sessões
- Issues UX-01/02 ganham framework de resolução
- Custo zero (skill internalizado)
- Base para futuro time de produto/design

### Negativas
- Overhead inicial de leitura do DESIGN.md a cada sessão (mitigado por progressive disclosure do Antigravity)
- Skill precisa ser mantido atualizado quando tokens mudarem
- Não substitui designer real para decisões de produto complexas

### Riscos
- Agente pode ser excessivamente rígido ao aplicar regras (mitigação: skill usa linguagem flexível, não mandatória)
- DESIGN.md pode ficar desatualizado se tokens CSS mudarem sem atualizar o doc (mitigação: incluir no checklist de PR)

## Referências

- Discovery completo: `discovery_designmotionhq.md` (conversa 820b0851)
- [[second-brain-frontend-360]] — Auditoria 360 com issues UX-01/UX-02
- [[second-brain-frontend-waves]] — Nota de presença de features 73/100
- [[ADR-013-adocao-padroes-mba-full-cycle-ia]] — Padrão de skills para agentes
- Skill criado: `.agents/skills/ux-engine-kiosk/SKILL.md`
- Design System: `dashboard/DESIGN.md`
