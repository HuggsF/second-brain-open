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
9. `sync` indexa o vault em um arquivo SQLite e `buscar` devolve os trechos relevantes sem serviço
   nenhum. Com o índice já construído, nota ilegível falha sozinha e as outras são atualizadas. Na
   primeira indexação e na reconstrução, uma nota ilegível aborta tudo: o `sync` lista as notas e não
   grava índice parcial.
10. `ask` gera a resposta pela cadeia de provedores do perfil e diz quem respondeu e quanto custou.
    Quando nenhum provedor responde, o perfil não carrega ou o orçamento está esgotado, `ask` mostra as
    fontes, diz o motivo e sai com 1.
11. Cada chamada de modelo registra o custo. Com o orçamento do dia ou do mês esgotado, nenhuma
    chamada vai a provedor de nuvem: a cadeia usa só provedores locais ou devolve `budget_exceeded`
    (saída 3 em `cli.py task`). `cli.py budget` mostra gasto, limite e estado.

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
| 9 | `tests/test_indice_texto.py`, `tests/test_sync_consistency.py`, `tests/test_busca_cli.py`, `tests/test_sem_motor_vetorial.py` |
| 10 | `tests/test_retrieval_contract.py`, `tests/test_answer_generation.py`, `tests/test_busca_cli.py` |
| 11 | `tests/test_cost.py`, `tests/test_budget.py`, `tests/test_budget_wiring.py`, `tests/test_local_tasks.py`, `tests/test_local_tasks_cli.py` |

Os arquivos desta tabela passam, assim como o resto da suíte. O resultado está na
[auditoria de construção mais recente](06-auditorias/2026-11-24-construcao.md).
