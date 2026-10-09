# ADR-001: Migração dos Sistemas de Atendimento e Processos (SULTS e Holmes) para Salesforce

## Status
Proposto (Em análise pelo time de engenharia)

## Data
2026-10-07

## Contexto
A holding **KIOSK Brands** opera com centenas de franquias no formato de quiosques e lojas em shoppings e terminais (marcas Touti, Amavia e Yes! Cosméticos). Atualmente, a operação de suporte e processos está fragmentada em duas ferramentas legadas:

1. **SULTS:** Utilizado como extranet, checklists operacionais e SAF (Serviço de Atendimento ao Franqueado).
2. **Holmes:** Utilizado para workflows de aprovação de documentos e padronização de rotinas entre matriz e quiosques.

### Problemas Enfrentados
- **Silos de Dados:** Um chamado de um franqueado no SULTS não conversa com uma aprovação de documento no Holmes nem com o financeiro no SAP.
- **Dificuldade de Integração:** APIs fragmentadas e limites de automação para inteligência artificial e agentes autônomos.
- **Falta de Visibilidade 360° do Franqueado:** O time de expansão e suporte não tem visão unificada do histórico do franqueado.

## Decisão
Decidiu-se unificar a gestão de chamados, relacionamento com franqueados e fluxos de processos na plataforma **Salesforce** (Sales Cloud + Service Cloud):

1. **Centralização de Atendimento:** O Service Cloud substituirá os chamados do SULTS e os fluxos de aprovação do Holmes.
2. **Camada de Integração:** Utilização de MCP (Model Context Protocol) e webhooks para conectar o Salesforce ao SAP (ERP) de forma segura.
3. **Agentes de Atendimento:** Implementação futura de agentes de IA para triagem e acompanhamento de chamados frequentes de reposição de mercadoria.

## Consequências
### Positivas
- Visão única de cada quiosque/franqueado em uma única plataforma enterprise.
- APIs padronizadas e ricas para desenvolvimento de integrações e agentes autônomos.
- Redução de custos de manutenção de múltiplas ferramentas de nicho.

### Desafios / Riscos
- **Curva de Migração:** Necessidade de mapear os chamados legados do SULTS e as regras de aprovação do Holmes.
- **Transição de Usuários:** Treinamento de franqueados e consultores de campo acostumados com o aplicativo móvel do SULTS.
