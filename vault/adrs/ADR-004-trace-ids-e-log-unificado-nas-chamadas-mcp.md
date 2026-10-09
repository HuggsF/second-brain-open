# ADR-004: Trace IDs e log unificado nas chamadas das ferramentas MCP do Second Brain

> Esta ADR trata do próprio repositório `second-brain`, não do Hub Logístico.

## Status
Aprovado e implementado (2026-10-09)

## Data
2026-10-09

## Contexto
A análise 360 do Second Brain (perfil Piloto, 2026-10-09) concluiu "Não apto". Entre as causas transversais está a impossibilidade de reconstituir qual ação de agente levou a qual efeito: os quatro servidores MCP não registavam nada, o gateway SSH tinha só um log próprio sem identificador de tarefa e o `request_id` do BFF era descartado (findings D09 e D07; risco transversal XR-04).

## Decisão
1. Todas as chamadas das 15 ferramentas MCP passam por um middleware FastMCP (`core/trace_middleware.py`) que grava um registo em `.runtime/trace-log.jsonl`.
2. Identificadores no formato W3C Trace Context: `trace_id` (32 hex) agrupa uma tarefa; `span_id` (16 hex) identifica a chamada.
3. Cada ferramenta aceita um parâmetro opcional `task_id`. Sem ele, cada chamada recebe um `trace_id` novo; com ele, o texto é transformado de forma estável num `trace_id` (hash) e guardado como `task_label`.
4. Argumentos são resumidos e segredos mascarados antes de gravar; falhas de registo nunca derrubam a chamada.
5. O gateway SSH emite eventos filhos (`ssh.exec`, `ssh.refused`) com o mesmo `trace_id`; o antigo `gateway-audit.jsonl` deixa de existir.
6. O campo `caller` usa o nome do cliente MCP do handshake (`client_info.name`), sem tentar identificar pessoas ou agentes.
7. Consulta: `cli.py trace <trace_id>` e `cli.py trace --recent N`.

## Alternativas descartadas
- **Decorador por ferramenta:** repete o código 15 vezes e uma ferramenta nova sem o decorador fica sem rasto.
- **Ferramentas `iniciar_tarefa` e `encerrar_tarefa`:** guardam estado escondido no processo e atribuem mal as chamadas quando duas tarefas se misturam.

## Consequências
- O log é local e não é à prova de adulteração: serve de evidência para o responsável, não para terceiros.
- A rotação (5 MB, 3 ficheiros) é um limite técnico, não uma política de retenção; a retenção continua por decidir.
- `caller` é informativo. Separar utilizadores e agentes (identidade real) fica para o trabalho de governança.
- Um agente que não passa `task_id` produz um rasto por chamada.
- O log é a base dos passos seguintes: árvore de evidências, mapa de topologia e vista dos agentes.
