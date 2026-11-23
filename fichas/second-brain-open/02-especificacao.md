---
secao: 2
origem: Passo de especificação do spec-driven development
aplica: sim
---
# Especificação

## Requisitos

1. A política decide cada chamada de ferramenta a partir da identidade do agente, da classe da ferramenta
   e dos argumentos, e nunca levanta exceção: em caso de erro, nega.
2. Ferramenta de leitura é aprovada; escrita local é aprovada e rastreada; leitura em produção é escalada
   para um humano; alteração em produção nunca é aprovada automaticamente.
3. A lista de comandos de inspeção permitidos existe em um único lugar.
4. Os portões de qualidade rodam conforme o conteúdo da missão e produzem um semáforo global.
5. Uma ferramenta que falha repetidamente é desligada por um disjuntor e religada depois de um teste.
6. Uma regra de negócio lista os roteiros de teste que a validam; a luz da regra vem das execuções
   registradas.
7. Cada chamada ao servidor MCP gera um registro de rastreio com os campos sensíveis mascarados.
8. O núcleo novo não cita o nome da organização que o usa.

## Critérios de aceite

Cada critério é um comportamento que um arquivo de teste do repositório exercita.

| Requisito | Teste |
|---|---|
| 1 e 2 | `tests/test_policy.py`, `tests/test_policy_registry.py` |
| 3 | `tests/test_no_local_allowlist.py` |
| 4 | `tests/test_gates.py`, `tests/test_gate_isolation.py` |
| 5 | `tests/test_resilience.py`, `tests/test_cb_half_open.py` |
| 6 | `tests/test_evidence.py`, `tests/test_evidence_store.py` |
| 7 | `tests/test_tracing.py`, `tests/test_trace_middleware.py` |
| 8 | `tests/test_agnostic_core.py` |

Os doze arquivos desta tabela passam hoje. As 92 falhas da suíte estão em outros seis arquivos, que cobrem
o grafo de missão, o servidor WebSocket e o tempo limite de ferramenta: esses comportamentos ficam fora da
tabela até que os testes rodem. O detalhe está na
[auditoria de construção](06-auditorias/2026-11-23-construcao.md).
