---
type: adr
scope: second-brain
status: Aceito
date: 2026-10-29
related: [ADR-017, ADR-018, ADR-035, ADR-038]
---
# ADR-040: Perfil kiosk sem Ollama na geração (nuvem só, Ollama só para embeddings)

> Esta ADR trata do próprio repositório `second-brain`, não do Hub Logístico.

## Contexto
A ADR-018 pôs o Ollama como reserva da cadeia de provedores das tarefas, e a ADR-038 levou a mesma cadeia para a resposta do assistente. Nesta estação (i5-1334U, sem GPU), o `llama3.2:3b` não serve como reserva: na medição de 2026-10-28 da ADR-038, as 4 respostas que chegaram ao modelo estouraram os 120 s, e uma chamada mínima levou cerca de 12 s por token. Quando a nuvem falha, a reserva só soma até 120 s de espera antes do mesmo `model_error`. O dono decidiu em 2026-10-29 tirar o Ollama da geração.

## Alternativas Consideradas
- **Manter o Ollama de reserva (ADR-018 e ADR-038 D1):** descartada. A reserva não entrega resposta dentro do prazo nesta máquina; só atrasa a falha.
- **Trocar a reserva por um modelo local menor (`llama3.2:1b`):** descartada. Continua lento com o prompt da resposta na CPU e piora a qualidade (ADR-038).
- **Segundo provedor de nuvem como reserva:** adiada. Exige outro endpoint com `zdr: true` e `data_collection: deny` e um `task-eval` próprio; entra em ADR nova quando for escolhido.
- **Tirar o Ollama também dos embeddings:** descartada. O `nomic-embed-text` (137M) é leve na CPU, a recuperação fica local (ADR-038 D2) e trocar o embedding exige `sync --rebuild` e novo `retrieval-eval` (ADR-037).

## Decisão
1. **D1, cadeia só de nuvem no perfil kiosk.** `profiles/kiosk/profile.yaml` declara só o provedor `openai_compatible` (OpenRouter, `zdr: true`, `data_collection: deny`). Substitui, para este perfil, o item 1 da ADR-018 ("Ollama de reserva") e a reserva local da ADR-038 D1. O núcleo não muda: a cadeia continua vindo do perfil, e um perfil pode voltar a declarar o Ollama.
2. **D2, orçamento estourado sem reserva.** Com o estado `exceeded` (ADR-035), as tarefas devolvem `status="budget_exceeded"` (exit 3 no CLI) e a resposta do assistente devolve `model_error` com motivo `budget_daily` ou `budget_monthly`, sem chamar nenhum modelo. É o caminho que a ADR-035 já previa para perfil sem provedor local.
3. **D3, Ollama só para embeddings.** O contêiner do Ollama continua necessário para `sync`, `query` e `retrieval-eval` (`nomic-embed-text`). O `llama3.2:3b` deixa de ser usado pelo perfil kiosk.
4. **D4, teste fixa a decisão.** `tests/test_local_tasks.py::test_real_kiosk_profile_has_no_local_generation` falha se o perfil kiosk voltar a ter provedor que não seja de nuvem, ou um de nuvem sem as duas garantias.

## Consequências
- **Sem chave, sem crédito, com HTTP 429 ou sem rede**, tarefas e respostas falham na hora (`escalate` ou `model_error`) em vez de esperar o Ollama. O `local_tasks_status` passa a refletir só o provedor de nuvem.
- **Dados:** nada muda nas garantias; o único destino da geração é o provedor da cadeia, com retenção zero e sem uso para treino.
- **Fica fora desta decisão:** o chat da página Workforce do dashboard (`dashboard/serve.py` com `backend/workforce_api.py`, este ainda não versionado) chama o Ollama direto, fora da cadeia de provedores. Precisa de decisão própria quando o arquivo entrar no repositório.
- **Perfil `example`:** continua com o Ollama, como exemplo genérico do núcleo.
