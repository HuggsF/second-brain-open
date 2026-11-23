---
id: ADR-003
status: aceito
data: 2026-11-23
---
# Uma política central decide cada chamada de ferramenta

## Contexto

Agentes chamam ferramentas, e algumas executam comandos em servidores. Listas de comandos permitidos
espalhadas pelo código divergem com o tempo. Código que sustenta: `core/policy/decide.py` (`decide`),
`core/policy/classes.py` (classe de cada ferramenta) e `core/policy/commands.py`; o teste
`tests/test_no_local_allowlist.py` falha se a lista aparecer em outro lugar.

## Opções consideradas

1. **Uma função de decisão única, por classe de ferramenta.** Aprovar, escalar ou negar em um só lugar.
2. **Cada servidor de ferramentas valida os próprios comandos.** Simples de começar, diverge depois.
3. **Confiar nas permissões do sistema operacional.** Não distingue leitura de alteração no nível que
   interessa, nem deixa registro da decisão.

## Decisão

Opção 1. Leitura é aprovada; escrita local é aprovada e rastreada; leitura em produção é escalada para
um humano; alteração em produção nunca é aprovada automaticamente. A política nunca levanta: erro vira
negação.

## Consequências

- Ferramenta nova precisa ser classificada antes de poder ser chamada; sem classe, é negada.
- A lista de comandos de leitura é conservadora: um comando legítimo e fora dela é recusado.
- Há um único ponto para auditar o que um agente pode fazer.
