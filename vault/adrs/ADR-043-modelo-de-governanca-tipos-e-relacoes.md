---
type: adr
status: Proposto
date: 2026-10-29
related: [ADR-005, ADR-021, ADR-022, ADR-023, ADR-041, ADR-042]
---
# ADR-043: Modelo de governança de agentes — tipos, relações e precedência

## Contexto
A governança dos agentes da KIOSK tem as peças, mas não tem um modelo que diga o que cada peça é e
como se liga às outras. As peças existentes:

- Normas: regras de negócio do vault (`RULE-001` a `RULE-010`), as 74 regras operacionais do Hub
  ([[hub-regras-operacionais-codex]]), o registro de códigos emitidos ([[ADR-041-registro-obrigatorio-identificadores-codigo-estado]]),
  as regras-base do toolkit ([[ADR-042-toolkit-de-agentes-fonte-unica-com-adaptadores]]), os
  `CLAUDE.md`/`GEMINI.md` e a política executável de `core/policy/` ([[ADR-022-politica-unica-e-corretor-de-ferramentas]]).
- Procedimentos: playbooks `PB-001` a `PB-020`, skills do Claude Code e do Antigravity.
- Execução e evidência: missões do orquestrador, `trace_id` ([[ADR-004-trace-ids-e-log-unificado-nas-chamadas-mcp]]),
  árvore regra → playbook → execução ([[ADR-005-arvore-de-evidencias-regras-playbooks-execucoes]]),
  luzes e JEV ([[ADR-023-luzes-de-teste-e-dominio-de-observacao]]).
- Decisões e demandas: ADRs, `DEMANDA-NNN`, `ADMIN-KIOSKBRANDS/governance`.

### Problemas Enfrentados
- **Quatro fontes de norma sem precedência.** Vault, registro do repositório, regras-base e
  arquivos de instrução podem divergir, e nada diz qual vale.
- **O mesmo procedimento em três lugares.** O deploy e rollback do Hub existe como skill
  (`hub-deploy-rollback`), nota de sistema ([[hub-deploy-rollback]]) e procedimento em playbook.
- **Runbook sem tipo formal.** A ADR-023 separou `kind: test` de `kind: runbook` para a luz da
  regra, mas em 29/10/2026 só 9 dos 20 playbooks declaram `kind` (8 `test`, 1 `runbook`);
  PB-008 e PB-012, que são runbooks, não declaram e têm `validates`.
- **Dois planos de governança.** Agentes da plataforma passam pelo corretor (política em código,
  rastro, aprovação). Agentes de IDE (Claude Code, Antigravity, Codex), que fazem a maior parte
  do trabalho nos repositórios, seguem só instruções em texto.
- **Evidência autodeclarada e aprovação sem registro.** O corretor prova que a chamada ocorreu,
  não que o resultado é verdadeiro (ADR-022). Não há registro durável de quem aprovou o quê.
- **Sem lugar para padrões e anti-padrões.** Lições de incidentes (reemissão J&T após timeout,
  Singleton do `BlingGateway`) ficam em notas soltas, sem ligação com a regra que violam nem com
  o check que as detecta.
- **Sem CI.** O second-brain não tem CI e o do Hub está com a cobrança da conta `userTI10`
  bloqueada (ADR-041). Checks que o modelo pressupõe rodam à mão ou não rodam.

## Alternativas Consideradas

### Opção A: tipos e relações em arquivos com frontmatter, um arquivo por item (escolhida)
- **Prós:** mesmo formato de ADR-005 e ADR-041; revisão por PR; validável por lint local e CI;
  funciona offline; o grafo é projeção gerada, não fonte.
- **Contras:** vínculos mantidos à mão desatualizam se não forem derivados ou validados.

### Opção B: ferramenta externa de catálogo ou GRC (Backstage, Jira, planilha)
- **Prós:** interface pronta, relatórios.
- **Contras:** fora do vault e do controle de versão; não alcança o CI nem os agentes offline;
  duplica o sistema de registro.

### Opção C: grafo (Neo4j) como fonte da verdade
- **Contras:** descartada pelos motivos da ADR-041 (CI não alcança, perde revisão por PR).
  Fica como projeção futura.

### Opção D: não modelar; resolver peça por peça
- **Contras:** mantém a duplicação de procedimentos e a falta de precedência; cada nova peça
  (toolkit, registro de códigos, catálogo de anti-padrões) inventa as próprias relações.

## Decisão

### 1. Tipos
Cada item é um arquivo com frontmatter (`type`, `status`, `date`, `dono`) e identificador
estável, nunca apagado nem reaproveitado.

| Grupo | Tipo | Identificador | Onde vive |
|---|---|---|---|
| Norma | Regra de negócio | `RULE-NNN` | `vault/rules/` |
| Norma | Código emitido | `<MODULO>-NN` (legados mantêm o prefixo) | `docs/regras/ids/` de cada repositório |
| Norma | Regra-base de agentes | `rb-<area>` | `regras-base.md` do agent-toolkit |
| Norma | Política executável | classe de ferramenta | `core/policy/` e hooks instalados pelo toolkit |
| Procedimento | Playbook de teste | `PB-NNN`, `kind: test` | `vault/playbooks/` |
| Procedimento | Runbook | `PB-NNN`, `kind: runbook` | `vault/playbooks/` |
| Procedimento | Skill | nome kebab-case + versão | `skills/` do agent-toolkit |
| Conhecimento | Padrão | `PADRAO-NNN` | `vault/padroes/` |
| Conhecimento | Anti-padrão | `ANTIPADRAO-NNN` | `vault/padroes/` |
| Registro | Execução / evidência | id da execução | `.runtime/evidence.db` (nunca no vault) |
| Registro | Rastro | `trace_id` | `.runtime/trace-log.jsonl` |
| Decisão | ADR | `ADR-NNN` | `vault/adrs/` |
| Demanda | Demanda | `DEMANDA-NNN` | `ADMIN-KIOSKBRANDS/governance` |

O prefixo `PB-` e a pasta `vault/playbooks/` ficam para runbooks e testes: renumerar quebraria
execuções já registradas. O que distingue é `kind`, que passa a ser obrigatório.

### 2. Relações
A relação é declarada no arquivo de origem; o destino não repete o vínculo.

| Origem | Campo | Destino | Observação |
|---|---|---|---|
| Playbook `test` | `validates` | Regra de negócio | Só `kind: test` conta na luz (ADR-023) |
| Runbook | `validates` | Regra de negócio | Vínculo de consulta (regra → runbook no JEV); não conta na luz, que só usa `kind: test` |
| Runbook | `opera` | Sistemas | |
| Skill | `executa` | Runbook ou playbook | Aponta; não copia os passos |
| Código emitido | `fonte_vault` | Regra de negócio | Uma regra pode ter vários códigos |
| Código emitido | `testado_por` | Testes | Derivado dos testes cujo nome começa por `[CODIGO]` |
| Anti-padrão | `viola` | Regra ou código | |
| Anti-padrão | `corrigido_por` | Padrão | |
| Anti-padrão | `detectado_por` | Teste, check ou playbook | Sem detector é lacuna de prevenção |
| Anti-padrão | `ocorreu_em` | `arquivo:linha`, commit ou incidente | Obrigatório: só entra anti-padrão observado na KIOSK |
| Padrão / anti-padrão | `problema` | texto curto | Chave que liga o padrão aos anti-padrões do mesmo problema |
| Execução | `playbook_id`, `evidence_ref` | Playbook | Formato atual de `record_test_execution` |
| ADR | `related` | Qualquer item | |

### 3. Precedência de normas para agentes
1. Política executável (código de `core/policy/` e hooks) vence tudo, porque é a única aplicada.
2. Mutação em produção exige autorização explícita do humano no mesmo turno, em qualquer caso.
3. `CLAUDE.md`/`AGENTS.md` do repositório vence a regra-base global do toolkit.
4. Regra-base global vence a skill.
5. Pedido explícito do usuário ajusta o fluxo de uma skill, nunca os itens 1 e 2.

Regra de negócio (`RULE-NNN`) não é instrução de agente: é fato do domínio. Divergência entre a
regra e o código é defeito a corrigir, não conflito de precedência.

### 4. Os dois planos de governança
- Plataforma: continua no corretor (ADR-022).
- IDE: o agent-toolkit instala, além das instruções, mecanismos de aplicação: hook antes de
  executar ferramenta que barra ou pede confirmação para comando de produção, e `task_id`
  obrigatório nas chamadas MCP. Os dois planos gravam rastro no mesmo formato.

### 5. Aprovação humana
Toda aprovação (`ESCALATE` aprovado, autorização de produção) vira evento no rastro com quem,
quando, o quê e o `trace_id` da ação aprovada.

### 6. CI como pré-requisito
Os checks do modelo (frontmatter e `kind`, referências entre itens, `regras:check`, segredos)
rodam no CI de cada repositório. Enquanto não houver CI, rodam à mão e a execução registra isso.

### 7. Implementação em demandas separadas
1. Declarar `kind` nos 11 playbooks sem o campo. Runbooks mantêm `validates`: `core/evidence.py:142`
   exige o campo em todo playbook e o JEV usa o vínculo para listar runbooks da regra.
2. Estender `cli.py evidence --lint` para `kind` obrigatório, `dono` e os campos novos.
3. Criar `vault/padroes/`, os templates de padrão e anti-padrão e os primeiros casos com evidência.
4. Incluir os hooks e o `task_id` no escopo do agent-toolkit (PRD Fase 1 ou fase própria).
5. Destravar o CI do Hub e criar o do second-brain.
6. Registro durável de aprovação no rastro.

## Consequências

### Positivas
- Cada peça nova (toolkit, registro de códigos, catálogo de anti-padrões) encaixa num tipo e
  em relações já definidos.
- Incidente vira anti-padrão, que aponta a regra violada e o check que faltava: o ciclo de
  governança se fecha.
- A precedência explícita resolve divergência entre fontes sem depender de interpretação.
- O JEV ganha dados: luz de regra a partir de testes que provam a regra, runbooks fora da luz.

### Desafios / Riscos
- Esta ADR não altera ADR-005, ADR-022, ADR-023, ADR-041 nem ADR-042; quando uma demanda da
  seção 7 mudar o que elas decidem, abre ADR própria.
- Campos novos só valem com lint; até o item 2, são convenção.
- Sem CI, a aplicação depende de execução manual.
- Hooks variam por ferramenta (Claude Code, Antigravity, Codex); o adaptador de cada uma precisa
  provar o hook em sessão real.

## Times Impactados
- Mantenedores do second-brain — lint, templates e pasta de padrões.
- Desenvolvimento do Hub — registro de códigos, nomes de teste e CI.
- Mantenedor do agent-toolkit — hooks e `task_id` nos adaptadores.

## Referências
- [[ADR-005-arvore-de-evidencias-regras-playbooks-execucoes]]
- [[ADR-021-escopo-do-second-brain-conhecimento-observabilidade-multiagente]]
- [[ADR-022-politica-unica-e-corretor-de-ferramentas]]
- [[ADR-023-luzes-de-teste-e-dominio-de-observacao]]
- [[ADR-041-registro-obrigatorio-identificadores-codigo-estado]]
- [[ADR-042-toolkit-de-agentes-fonte-unica-com-adaptadores]]
- [[agent-toolkit-prd-fase1-aprovada]]
- [[hub-arquitetura-ddd-typescript]]
