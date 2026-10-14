---
type: adr
scope: second-brain
status: Aceito
date: 2026-10-14
related: [ADR-012, ADR-017, ADR-020, ADR-021]
---
# ADR-022: Política única e corretor de ferramentas

> Esta ADR trata do próprio repositório `second-brain`, não do Hub Logístico.

## Contexto
A plataforma multiagente (ADR-021) chegou à Fase 5 com quatro problemas na camada de ferramentas:
- **Duas listas de comandos permitidos.** O gateway SSH (`mcp_servers/srv_api_gateway_mcp.py`) e o executor do backend (`backend/tool_executor.py`) mantinham cada um a sua allowlist de comandos de inspeção, e elas divergiam.
- **Executor sem rastro e com chave SSH não fixada.** O executor abria a própria conexão SSH, sem registrar a chamada no `trace-log` e sem a chave do servidor memorizada que o gateway já usava.
- **Portões (gates) aplicados em lugar nenhum.** A ADR-020 definiu o domínio de workflow e os portões, mas a missão começava sem passar por eles, e o `ws_server` não validava o envelope de `NEW_TASK`.
- **Registro de ferramentas diferente da realidade.** `TOOL_REGISTRY` listava `run_tests`, `validate_plan` e `write_doc`, que nenhum código implementava, e não listava ferramentas que o executor de fato oferecia.

## Alternativas Consideradas
- **Manter duas listas, sincronizadas à mão:** descartada. É a causa da divergência; cada correção precisaria ser feita em dois lugares, sem nada que acuse o esquecimento.
- **Política só no gateway SSH:** descartada. Cobre apenas a ferramenta que fala com produção; as demais (leitura do vault, regras, evidência) continuariam sem veredito nem rastro, e o agente não teria identidade na decisão.

## Decisão
1. **Política única em `core/policy/`.** Identidade, classes de ferramenta, listas de comandos e a função `decide(identity, tool, args)` vivem ali e só ali. O gateway importa as regras de comando de `core.policy.commands`; um teste (`tests/test_no_local_allowlist.py`) falha se outra allowlist local reaparecer.
2. **Vereditos `APPROVE`, `ESCALATE` e `DENY`, com falha fechada.** Identidade inválida, ferramenta desconhecida, papel sem permissão, argumentos malformados ou qualquer exceção na própria política resultam em `DENY`. A política nunca levanta. Cada ferramenta tem uma classe: leitura e escrita local viram `APPROVE`; leitura em produção vira `ESCALATE`; mutação em produção é sempre `DENY`.
3. **Corretor `core/broker.py` como único caminho.** Toda chamada de ferramenta passa por `broker.call(identity, tool, args, task_id, approved=...)`: decide, executa as implementações de `core/tools.py` e grava o rastro com `caller` `agent:<papel>` e o rótulo `M<missionId>`. `backend/tool_executor.py` virou um adaptador fino sobre o corretor. Há uma só implementação de SSH, a do gateway, com a chave do servidor memorizada.
4. **Agentes são 5 papéis × 4 especialidades (ADR-012), em dois eixos.** O papel (`manager`, `researcher`, `coder`, `writer`, `reviewer`) decide o que a política permite (`TOOL_REGISTRY`); a especialidade (`DEV`, `DEVOPS`, `QA`, `PRODUTO`) é um segundo eixo, opcional na identidade (`agent:<papel>[/<ESPECIALIDADE>]`), validado por `core/policy/identity.py`, e não concede ferramenta: a permissão depende só do papel. As especialidades na tela ficam para a Fase 7.
5. **`run_safe_command` só para o papel `coder` e sempre `ESCALATE`.** Só é executada com aprovação explícita por chamada (`approved=True` no corretor), e nunca se o comando for recusado pelas regras de comando (bloqueio ou fora da inspeção somente leitura), caso em que o veredito é `DENY` antes de qualquer pedido de aprovação. A missão do orquestrador não passa `approved=True`, portanto não executa o comando sozinha.
6. **`run_tests`, `validate_plan` e `write_doc` saíram do registro.** Ninguém as fornecia, o runner de testes fica fora deste repositório e relatórios nunca escrevem no vault. `get_rule_evidence`, que o papel `reviewer` já listava, passou a ter implementação. O registro agora é igual ao que o corretor executa.
7. **Os portões rodam antes de cada missão** (`core/mission_guard.py`): vermelho bloqueia a missão e amarelo pede aprovação humana antes de começar. Um plano com ferramenta desconhecida é vermelho.
8. **O `ws_server` valida o envelope de `NEW_TASK`** com `validate_mission_envelope` (ADR-020) antes de cancelar qualquer missão em curso; o `missionId` devolvido ao cliente tem tamanho limitado.

## Consequências
- Um comando SSH pedido por um agente exige aprovação humana a cada chamada; na missão atual isso significa que ele é recusado com a mensagem de aprovação exigida, e não executado.
- O servidor MCP `srv_api_run_safe_command` continua com o opt-in `SRV_API_ALLOW_ARBITRARY` para comandos fora da inspeção; a política dos agentes é mais estreita e não depende dele.
- `core/tools.py` importa o gateway de forma tardia para executar SSH. É dívida a quitar com um `core/ssh.py` que ambos usem e que tire a dependência de `core/` sobre `mcp_servers/`.
- O rastro do corretor é gravado com E/S de arquivo síncrona (`tracing.write_record`), que bloqueia o laço de eventos por instantes; falha de escrita nunca derruba a chamada.
- A evidência continua auto-reportada: o corretor prova que a chamada ocorreu e quem a fez, não que o resultado é verdadeiro.
- Problema anterior e conhecido: um `APPROVE` antecipado ou duplicado pode satisfazer previamente uma espera de aprovação posterior, porque `Orchestrator.approve` apenas sinaliza um evento. Uma guarda em `Orchestrator.approve` fica como follow-up.
- O rótulo `validate_plan` em `dashboard/agent-arena.js` é só texto de interface, sem efeito de política; sai junto com a Fase 7.
