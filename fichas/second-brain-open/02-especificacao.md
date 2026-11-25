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
12. Uma demanda nasce em `intake` e só muda de fase quando o portão da transição aceita: triagem
    aprovada por um papel, com trilha escolhida, e os artefatos que a trilha exige naquela fase. A
    recusa diz o que falta.
13. `gerar-artefatos` redige os rascunhos da fase pela cadeia de provedores e os grava em
    `fichas/<projeto>/demandas/<id>/` com `status: proposta`. Rascunho não abre portão. Sem
    `--refazer`, nenhuma página existente é alterada; com `--refazer`, só as que ainda estão em
    `proposta`.
14. O produto de uma demanda é um slug do catálogo do perfil, e esse slug é o de uma ficha. Produto
    fora do catálogo ou sem ficha é recusado, e nada é gravado fora da ficha. Perfil inexistente é
    recusado; perfil sem catálogo só confere a ficha, e os comandos avisam.

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
| 12 | `tests/test_demand_lifecycle_v2.py`, `tests/test_triagem.py`, `tests/test_triagem_portoes.py`, `tests/test_demanda_cli.py` |
| 13 | `tests/test_geracao_gerador.py`, `tests/test_geracao_ponta_a_ponta.py`, `tests/test_geracao_escrita.py`, `tests/test_demanda_cli.py`, `tests/test_ficha.py` |
| 14 | `tests/test_produtos.py`, `tests/test_docs_registry.py`, `tests/test_demanda_cli.py` |

Os arquivos desta tabela passam, assim como o resto da suíte. O resultado está na
[auditoria de construção mais recente](06-auditorias/2026-11-25-construcao.md).
