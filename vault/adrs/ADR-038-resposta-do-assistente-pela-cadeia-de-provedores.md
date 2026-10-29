---
type: adr
scope: second-brain
status: Proposto
date: 2026-10-28
related: [ADR-017, ADR-018, ADR-035, ADR-036, ADR-037]
---
# ADR-038: Resposta do assistente pela cadeia de provedores (nuvem primeiro, Ollama de reserva)

> Esta ADR trata do próprio repositório `second-brain`, não do Hub Logístico.

## Contexto
`BrainRetriever.answer()` (usado pelo `cli.py ask`, pelo BFF e pelo chat de teste) gera a resposta chamando o Ollama direto, com `llama3.2:3b` e timeout de 120 s. Nesta máquina (i5-1334U, sem GPU) o modelo roda na CPU e o prompt da resposta é grande: a pergunta mais até 4 trechos do vault. Medição de 2026-10-28, com o índice já reconstruído e o Ollama sem outro trabalho (evidência em `.superpowers/runs/2026-10-28-segundo-sinal/chat-evidence/transcript.txt`):
- **Chat:** das 5 perguntas, 4 chegaram ao modelo e as 4 estouraram os 120 s (`model_error`); a quinta foi recusada pelo gate sem chamar o modelo. O lote levou 9 min 10 s.
- **Chamada mínima direta ao Ollama** (prompt de poucas palavras, 5 tokens de saída): 37 s para ler o prompt e 59 s para gerar, cerca de 12 s por token.
- **Máquina no momento:** 0,4 GB de RAM livre de 15,7 GB e CPU em 100%, com outros aplicativos abertos. O modelo de 2,5 GB disputa memória com o resto da estação de trabalho.

A ADR-018 já registrava cerca de 16 s por tarefa curta no mesmo hardware. A resposta local depende de quanta memória e CPU sobram na estação de trabalho, e isso varia ao longo do dia.

As tarefas locais (ADR-017 e ADR-018) já resolveram esse problema: o perfil declara uma cadeia ordenada de provedores, a nuvem vem primeiro e o Ollama é a reserva. Todo provedor de nuvem leva `zdr: true` e `data_collection: deny`, e o orçamento da ADR-035 limita o gasto. A resposta do assistente ficou fora dessa cadeia.

Custo estimado com o provedor atual do perfil `kiosk` (`deepseek/deepseek-v4-flash-0731` via OpenRouter, US$ 0,016 por milhão de tokens de entrada e US$ 0,64 por milhão de saída): cerca de 3 mil tokens de entrada e 500 de saída custam por volta de US$ 0,0004 por resposta, ou cerca de US$ 0,40 por mil perguntas. A estimativa precisa ser conferida no orçamento depois das primeiras chamadas reais.

## Alternativas Consideradas
- **Manter só o Ollama:** descartada. Na medição, nenhuma resposta saiu dentro de 120 s, e um assistente que leva minutos por pergunta não é usado.
- **Modelo local menor (`llama3.2:1b`):** descartada como solução principal. Reduz a latência, mas piora a resposta, e continua lento com prompt grande na CPU. Pode entrar como reserva num perfil próprio.
- **Encolher o prompt (menos trechos, `num_predict` menor):** complementar, não substitui. Ajuda os dois caminhos e entra como ajuste separado, medido no `retrieval-eval` e no chat.
- **Só nuvem, sem reserva local:** descartada. Sem chave, sem rede ou com orçamento estourado o assistente pararia; a ADR-018 já fixou a reserva local como regra.
- **Um cliente de nuvem próprio dentro do retriever:** descartada. Duplicaria a cadeia, as garantias `zdr` e `data_collection` e o registro de custo que já existem em `core/local_tasks/`, e fugiria do orçamento.

## Decisão
1. **D1, mesma cadeia das tarefas.** A geração da resposta em `answer()` passa pela cadeia de provedores do perfil ativo (`FallbackClient` de `core/local_tasks/providers.py`), na ordem declarada: nuvem primeiro, Ollama de reserva. Só provedores do perfil, todos com `zdr: true` e `data_collection: deny` (CLAUDE.md §2).
2. **D2, recuperação continua local.** Embedding da pergunta, busca no Qdrant, piso e gate de termo (ADR-034 e ADR-037) não mudam e nunca saem da máquina. Só a pergunta e os trechos já selecionados vão ao provedor de geração. Sem citação (`no_evidence`), nenhum provedor é chamado.
3. **D3, contrato do cliente sem mudança.** A resposta usa o `chat(model, system, user, schema)` existente, com um schema mínimo `{"answer": string}`. Os clientes de nuvem e do Ollama não ganham método novo.
4. **D4, orçamento e custo.** Cada resposta grava o custo no `BudgetTracker` como as tarefas (ADR-035 e ADR-036). Com o estado `exceeded`, a resposta vai direto ao Ollama; o alerta de piora segue o mesmo caminho das tarefas.
5. **D5, retorno.** O resultado de `answer()` mantém as chaves atuais e o `status` (`ok`, `no_evidence`, `model_error`), e ganha `provider` (nome do provedor que respondeu) e `cost_usd`. `model_error` passa a significar que todos os provedores da cadeia falharam.
6. **D6, prazos.** Vale o `timeout_seconds` de cada provedor do perfil (hoje 20 s na nuvem e 120 s no Ollama), em vez do 120 s fixo no código.

## Consequências
- **Latência e custo medidos (2026-10-28, branch `feat/resposta-pela-cadeia`, evidência em `.superpowers/runs/2026-10-28-segundo-sinal/chat-evidence/adr038-prova-real.txt`):** duas respostas pelo OpenRouter em 4,4 s e 4,8 s, com custo real de US$ 0,000128 e US$ 0,000342 (abaixo da estimativa acima). Uma pergunta recusada pelo gate da ADR-037 voltou em 0,6 s, sem chamar provedor e com custo zero. Na mesma máquina, o Ollama sozinho estourava os 120 s.
- **Dados:** a pergunta e os trechos do vault citados saem da máquina, só para provedores da cadeia com retenção zero e sem uso para treino. Quem precisar de resposta 100 % local usa um perfil cuja cadeia só tem o Ollama.
- **Custo:** passa a existir gasto por pergunta, limitado pelo orçamento do perfil. O teto diário e mensal precisa caber no uso esperado do assistente além das tarefas.
- **Núcleo agnóstico:** o código novo em `core/` não cita a instância; o provedor e o modelo vêm do perfil (`tests/test_agnostic_core.py`).
- **Testes (TDD em `core/`):** cadeia com nuvem respondendo; nuvem falhando e Ollama respondendo; orçamento `exceeded` indo direto ao Ollama; `no_evidence` sem nenhuma chamada; todos falhando dando `model_error`; custo gravado no `BudgetTracker`. Nenhuma chamada de rede real nos testes.
- **Fora desta decisão:** mudar o número de trechos ou o tamanho da resposta, e streaming da resposta no BFF.
