---
type: system
status: active
date: 2026-10-09
---
# Second Brain — BFF e observabilidade local

Implementação da wave 1 em 08/10/2026. Piloto local, um espaço autorizado (`kiosk`), perfil de leitura. Não é autenticação multiusuário pronta para internet.

## Fluxo implementado

Dashboard → adapter HTTP de mesma origem → BFF autenticado → histórico SQLite local.
Daemon de coleta → cliente FastMCP → ferramenta `observe_hub(environment)` → SSH com host fixado → coletor existente do Hub → PM2, health HTTP e SQLite em modo de leitura → histórico.

O navegador nunca recebe chave SSH, comandos genéricos, token GitHub ou payloads de pedidos. A ferramenta permite apenas `production` e `hml`; diretórios, comando, revisão esperada e política de worker são definidos no código. O gateway genérico existente não é publicado na API.

## Inicialização e sessão

Na raiz do Second Brain, com o Python da `.venv`:

1. `python -m observability.enroll_host` uma única vez. A identidade pública é obtida pela conexão autenticada existente (TOFU, sem verificação independente); conferir fora de banda antes de uso ampliado. O coletor usa RejectPolicy e não substitui automaticamente o pin em `.runtime/known_hosts`.
2. `python -m backend.server` inicia o BFF em `127.0.0.1:8848` e o daemon interno.
3. Abrir o link de `.runtime/connect.url`. Expira em 30 minutos, uso único. Cookie HttpOnly, SameSite Strict, sessão de oito horas. O banco guarda hashes dos segredos. Não compartilhar esse arquivo.
4. `python -m backend.server --issue-link` renova apenas o acesso local, sem iniciar outro daemon.

Uma instância por porta: a exclusividade de coleta vale dentro do processo; uma segunda instância na mesma porta não inicia o daemon. Não executar instâncias em outras portas compartilhando o banco. Reinício manual após reboot nesta wave. O serviço antigo em 8847 continua como visualização offline.

## Contrato HTTP v1

- GET `/v1/capabilities`: recursos habilitados; `semantic_retrieval` agora é true (recuperação vetorial com citações, ADR-034); execução de agentes continua false e GraphRAG (grafo) não está conectado.
- GET `/v1/observability?space=kiosk&environment=production`: última observação válida, última tentativa, idade, stale e collection_failed.
- GET `/v1/observability/history?space=kiosk&environment=hml&limit=30`: tentativas recentes, máximo 100 por resposta.

- POST `/v1/retrievals?space=kiosk` (onda B, ADR-034): recuperação vetorial com citações.
  - Guarda: sessão e verificação de mesma origem (Host, `Sec-Fetch-Site` e `Origin` explícito, como nas demais escritas); `Content-Type: application/json`.
  - Corpo JSON: `query` (texto, 1 a 500 caracteres), `limit` (inteiro de 1 a 10, padrão 5) e `category` (texto ou `null`). Espaço diferente de `kiosk` na query string recebe 403.
  - Resposta 200: `schema_version`, `space_id`, `request_id`, `mode: "vector"`, `query`, `index_version`, `citations`, `gaps` e `timings_ms.retrieval`. Cada citação traz `document`, `section`, `line_start`, `line_end`, `sha256`, `score`, `stale` e `excerpt` (trecho com até 400 caracteres). `citations` vazio com `gaps` preenchido significa sem evidência.
  - Erros tipados: 400 (`INVALID_JSON`, `INVALID_QUERY`, `INVALID_LIMIT`, `INVALID_LENGTH`), 401 (`AUTH_REQUIRED`), 403 (`ORIGIN_DENIED`, `SPACE_DENIED`), 413 (`BODY_TOO_LARGE`), 415 (`JSON_REQUIRED`) e 503 (`RETRIEVAL_UNAVAILABLE`, quando Qdrant ou Ollama falham). O texto da exceção nunca vai na resposta; vai só ao log local.
  - O retriever é criado sob demanda: o BFF sobe sem Qdrant, e a rota devolve 503 enquanto o serviço estiver fora. O índice anterior à onda B não devolve nada até `cli.py sync --rebuild --yes` (ADR-034).

Rotas de dados e arquivos do dashboard exigem sessão. Espaço diferente recebe 403; ambiente inválido 400; ausência de sessão 401. Fora `POST /v1/retrievals`, as rotas de dados são somente GET, sem ferramentas corretivas. Host e Origin validados; não há CORS. Diretórios fora do dashboard não são servidos.

## Daemon e interpretação

Coleta serial dos dois ambientes; nova rodada 60 segundos após terminar a anterior; lock evita sobreposição. Duas amostras por ambiente separadas por um segundo. Não há chamadas ao Bling ou J&T. O SHA esperado é `3cf7250afe30931a54621093638e1b0f76f64169`; worker esperado ligado em produção e desligado em homologação. Alterar a expectativa somente após deploy validado.

Histórico persistido em `.runtime/brain.db`, limitado a sete dias e aproximadamente 10 mil tentativas. Mais de 180 segundos sem observação válida é dado desatualizado. Falha de transporte preserva o resultado anterior e apresenta alerta; observação recente com diagnóstico ruim permanece como requer atenção.

Os campos `*SinceDeploy` do coletor são contagens da janela móvel de cinco minutos nesta integração, e a UI informa essa janela. Reinícios e jobs falhos são acumulados; jobs antigos não comprovam nova regressão. Diagnóstico de saúde operacional não comprova erp_id/rastreio/chave fiscal; reconciliação fiscal continua em auditoria separada.

## Continuidade

Wave 2: recuperar texto e vetores com citações e escopo autorizado (a leitura de paths nos MCPs foi corrigida na onda A, ADR-033; a recuperação vetorial com citações, piso e espaço entrou na onda B, ADR-034; resta a recuperação de texto e grafo). Wave 3: orquestrador durável, estados de runs, budgets, cancelamento e SSE. Wave 4: ferramentas isoladas e aprovações vinculadas à ação. Conectar watcher de ingestão exige heartbeat e estratégia para falha de embeddings; ele não é ativado por esta wave.

Antes de abrir acesso em rede: TLS, identidade multiusuário, permissões reais por espaço, limites de conexões, supervisão do daemon, auditoria de acesso sem segredos e verificação independente do host SSH.

## Rollback local

Parar somente o processo do BFF iniciado nesta wave. Restaurar os arquivos alterados a partir de `.frontend-backups/bff-wave1-*`; remover apenas os novos arquivos relacionados na lista `manifest.json`. Regenerar o snapshot com `python dashboard/build_graph.py` após restaurar o diário. Preservar `.runtime/brain.db` para evidência, fora de publicação. O Hub de produção não recebe mudanças de código, banco ou configuração por esta wave.

## Validação da wave

Seis testes Python do BFF e 30 testes Node do dashboard aprovados. Integração FastMCP executada realmente nos dois ambientes com host pinado. Validada em navegador a sessão, as coletas reais, os alertas e o histórico. Observação recente de produção indicou erros em UPDATE do Bling, que exigem investigação independente; nenhum reparo automático é executado.

## Log de rastreio das chamadas MCP

Todas as ferramentas dos quatro servidores MCP gravam um registo em `.runtime/trace-log.jsonl` (ver ADR-004): `trace_id` e `span_id` no formato W3C, ferramenta, duração, estado e argumentos resumidos sem segredos. O parâmetro opcional `task_id` agrupa as chamadas de uma tarefa. O BFF ainda não lê este log; os próximos passos (árvore de evidências, mapa e vista dos agentes) vão consumi-lo. Consulta: `cli.py trace <trace_id>` ou `cli.py trace --recent N`.

## Árvore de evidências

Regras de negócio (`vault/rules/`) e playbooks (`vault/playbooks/`) são notas versionadas; as execuções dos testes ficam no registro local `.runtime/evidence.db`, cada uma ligada ao `trace_id` da chamada que a registrou (ver ADR-005). O BFF ainda não lê este registro. Consulta: `cli.py evidence [RULE_ID]`, `cli.py evidence --lint` e as ferramentas MCP `list_rules`, `get_rule_evidence` e `record_test_execution`.
