---
type: adr
scope: second-brain
status: Proposto
date: 2026-10-13
related: [ADR-008, ADR-014, ADR-017]
---
# ADR-018: Provedores de nuvem com reserva local para as tarefas

> Esta ADR trata do próprio repositório `second-brain`. Substitui, em parte, o ADR-017: a decisão "o núcleo nunca chama a nuvem" deixa de valer; o resto do ADR-017 (envelope, `escalate`, perfis, eventos) continua.

## Status
Proposto. O critério de sucesso da spec (`.superpowers/specs/2026-10-13-12-43-provedores-nuvem-com-reserva-local-design.md`, §1) foi atingido no acerto, mas não na latência: no `task-eval` final do perfil kiosk a média por chamada de modelo foi 17,6 s, acima dos 16 s do modelo local. Vira `Aceito` quando uma nova medição do perfil kiosk der média bem abaixo de 16 s (ver "Pendências").

## Contexto
O ADR-017 criou o tier local (Ollama, `llama3.2:3b`) e decidiu que o núcleo nunca chama a nuvem: o que o modelo local não resolve volta ao chamador como `escalate`. Nesta máquina (i5-1334U, sem GPU dedicada) cada tarefa leva cerca de 16 s com o modelo carregado e 44–51 s a frio, o que inviabiliza o uso interativo pelos agentes. Modelos pequenos servidos na nuvem respondem em poucos segundos e custam frações de centavo por chamada, mas mandam o conteúdo da tarefa para fora da máquina.

## Decisão
1. **Nuvem primeiro, Ollama de reserva.** O perfil declara uma cadeia ordenada `providers`. O núcleo tenta cada provedor em ordem; falha de rede, HTTP ≥ 400, resposta sem conteúdo ou timeout passa ao próximo. Provedor cuja chave falta (ou está vazia) é pulado sem chamada. Sem `providers`, o comportamento é o do ADR-017.
2. **Só provedor sem retenção nem treino.** Todo provedor de nuvem do perfil leva no corpo da requisição `provider: {data_collection: deny, zdr: true}`: `zdr: true` restringe a endpoints sem retenção de dados (*zero data retention*) e `data_collection: deny` exclui endpoints que coletam ou treinam com o conteúdo. Essa garantia faz parte da decisão: um provedor de nuvem sem ela não entra no perfil. A mesma trava fica ligada na conta (openrouter.ai/settings/privacy).
3. **Cliente genérico compatível com OpenAI.** `OpenAICompatClient` fala `POST {base_url}/chat/completions` com `response_format` por `structured` (`json_schema`, `json_object` ou `none`) e mescla `extra` no corpo sem sobrescrever `model` nem `messages`. A chave é lida de `os.environ[api_key_env]` na hora da chamada; o perfil guarda só o nome da variável. O fornecedor (`openrouter`) e a URL aparecem só em `profiles/kiosk/profile.yaml`; o gate de agnosticismo recusa o nome no núcleo.
4. **Custo e origem no envelope.** `cost.tier` ganha `cloud`; `cost.provider` e `cost.actual_usd` (soma, resposta a resposta, de tokens × `price` do provedor que respondeu) são opcionais. `local_tasks_status` lista cada provedor com `configured` e `available`; `model_available` só é verdadeiro se algum provedor estiver configurado e disponível.
5. **Modelo do perfil kiosk:** `deepseek/deepseek-v4-flash-0731`, escolhido pela avaliação real de 2026-10-13 (abaixo), com o preço da lista pública (0,016 / 0,64 USD por 1M tokens de entrada / saída).

## Alternativas Consideradas
- **Local primeiro, nuvem de reserva:** descartada. A reserva só entraria depois de a chamada local falhar ou estourar o tempo, então o caso comum continuaria com 16 s ou mais; o objetivo é justamente tirar o caso comum do Ollama.
- **Um provedor só (nuvem sem reserva):** descartada. Sem chave, sem crédito, com limite de taxa (HTTP 429, visto na avaliação) ou sem rede, toda tarefa viraria `escalate`; o Ollama já está instalado e cobre esses casos.
- **Roteamento por sensibilidade do conteúdo:** descartada por ora. Classificar o que é sensível antes de enviar exige um classificador confiável, que não temos; a garantia `zdr`/`deny` vale para todo conteúdo e é verificável no corpo da requisição.
- **Cliente específico de fornecedor (SDK do OpenRouter ou de um modelo):** descartada. Prende o núcleo a uma instância e a um fornecedor; a API compatível com OpenAI é atendida por vários provedores e pelo próprio Ollama.
- **Biblioteca de terceiros (LiteLLM):** descartada. Traz dezenas de dependências e o próprio mapeamento de erros e custos para um uso que cabe em cerca de 120 linhas com `httpx`, que o projeto já usa; e o controle do que vai no corpo (a garantia `zdr`/`deny`) ficaria atrás de mais uma camada.

## Avaliação real (2026-10-13)
Candidatos: os 3 de menor preço de entrada em `GET https://openrouter.ai/api/v1/models` com `structured_outputs`, contexto ≥ 8k, sem `:free`, sem alias `~` nem variante `:batch`. Cada um rodou `cli.py task-eval` (12 casos; os 3 de `validate` são determinísticos e não chamam modelo) com `zdr: true`, `data_collection: deny` e o Ollama de reserva. Latência = média de `cost.ms` das 9 chamadas de modelo, incluindo o tempo das tentativas que falharam.

| Candidato | Acerto | Latência média | Tiers (9 chamadas) | Custo por chamada |
|---|---|---|---|---|
| `deepseek/deepseek-v4-flash-0731` | 100% | 6,2 s | cloud 9 | US$ 0,000195 |
| `openai/gpt-oss-20b` | 100% | 7,8 s (10,6 s numa 1ª rodada) | cloud 9 | US$ 0,000029 |
| `inclusionai/ling-3.0-flash-vl` | 92% | 12,7 s | cloud 5, local 4 | US$ 0,000007 |

`ling-3.0-flash-vl` caiu no Ollama em 4 chamadas: os dois endpoints ZDR desse modelo responderam HTTP 429 (limite de taxa). Vencedor pelo critério (acerto, depois latência, depois custo): `deepseek/deepseek-v4-flash-0731`.

`task-eval --profile kiosk` final com o vencedor: acerto 100% (12 de 12), 9 chamadas em `cloud`, latência média 17,6 s (mediana 7,2 s; máxima 87,5 s, uma chamada de `extract` com 1.805 tokens de saída), custo médio US$ 0,000294 por chamada.

## Consequências
- **Acerto:** 100% no perfil kiosk pela nuvem, contra 92% do `llama3.2:3b` local no mesmo dataset de 12 casos.
- **Latência:** mediana de 7,2 s por chamada, mas com cauda longa. A média do kiosk foi 17,6 s por causa de uma resposta de 87,5 s. O `timeout_seconds: 20` do provedor é o timeout de leitura do `httpx`, não um prazo total por chamada: uma resposta longa que continua chegando não é cortada. O prazo total do `run_task` (`max(timeouts) × (1 + retries) × 2` = 480 s no kiosk) continua valendo.
- **Custo:** US$ 0,0002–0,0003 por chamada com o vencedor; a avaliação inteira (5 rodadas, 45 chamadas de modelo) custou US$ 0,005. `paid_equivalent_usd` mantém o significado do ADR-017.
- **O que sai da máquina:** o texto da tarefa e o prompt vão ao OpenRouter e a um endpoint com ZDR. A chave e o conteúdo nunca vão para envelope, `events.jsonl`, trace MCP ou mensagem de erro (coberto por teste com chave sentinela).
- **Reserva:** sem chave, sem crédito, com 429 ou com a nuvem fora, a tarefa é atendida pelo Ollama (visto na avaliação com `ling-3.0-flash-vl`), com a latência local somada ao tempo perdido na nuvem.

## Pendências
- Prazo total por chamada no `OpenAICompatClient` (ou limitar o raciocínio do modelo via `extra`) e nova medição do perfil kiosk. Com a média bem abaixo de 16 s, este ADR passa a `Aceito`.
