---
type: system
status: active
date: 2026-10-09
---
# Second Brain: evolução de recuperação e agentes

Data da auditoria: 08/10/2026. Escopo: leitura dos arquivos locais do Second Brain e implementação de um núcleo de experiência local no staging. Nenhuma chamada ao Qdrant, Ollama, gateways, produção ou indexação foi feita para esta auditoria.

## Atualização posterior — wave 1

O piloto local agora tem adapter HTTP, BFF autenticado e daemon de observação de produção/homologação por MCP, com histórico e estado de coleta. O baseline abaixo registra a auditoria inicial, anterior à conexão real. GraphRAG semântico e execução multiagente continuam não conectados. Consulte `vault/systems/second-brain-observability-bff.md` (na raiz do projeto) para operação, contrato e rollback.

## Estado comprovado na auditoria inicial

| Área | Implementação existente | Limite atual |
|---|---|---|
| Conhecimento | Vault com 30 arquivos Markdown na leitura inicial | O catálogo do dashboard cobre apenas parte do vault |
| Recuperação | `core/retriever.py` gera embedding pelo Ollama e busca no Qdrant | Busca top-k filtrada por categoria; não consulta o grafo |
| Geração | `BrainRetriever.answer()` chama Ollama, sem streaming | Falha do modelo vira texto no campo de resposta, sem estado de erro tipado |
| Ferramentas | `mcp_servers/brain_mcp.py` expõe pesquisa, ADR, arquitetura e estatísticas via FastMCP | Não equivale a uma API web com autenticação e autorização por espaço |
| Grafo | Catálogo curado de 19 nós, 16 relações, 3 vistas e 8 fontes no build inicial | Não há extração automática, comunidades nem armazenamento de grafo utilizado pelo retriever |
| Frontend inicial | HTML/CSS/JS estático, carregando `graph-data.js` | Sem HTTP API, stream de eventos, execução de agentes ou persistência de runs |
| Agentes | Gateway MCP pode ser utilizado por clientes externos | Não há orquestrador de múltiplos agentes, scheduler, runs ou aprovações persistidas no projeto |

O armazenamento vetorial encontrado é **Qdrant**. Não foi encontrada implementação Chroma nesses arquivos. Disponibilidade atual dos serviços não foi testada, portanto o frontend não deve apresentar “online” a partir da existência desses módulos.

## O que o núcleo local faz

`core.js` contém funções síncronas, sem rede, eval, credenciais, geração de resposta ou execução de ferramentas. O mesmo módulo é exportado para o browser como `window.BrainCore` e para os testes Node como CommonJS.

- `normalize(text)`: remove acentos, normaliza caixa e espaços; conteúdo continua sendo dado.
- `search(graph, query, {limit=12, category='all', kind='all'})`: busca lexical em entidades e em **todos** os documentos presentes no bundle, incluindo documentos sem nó associado. `category` é o primeiro segmento do caminho documental; `kind` aceita `all`, `entity` ou `document`.
- `neighborhood(graph, id, hops=1)`: retorna objetos de nós/arestas existentes. Considera ambas as direções para explorar vizinhança, limitada a dois saltos, 80 nós e 240 relações.
- `shortestPath(graph, source, target, {directed=false, view=null})`: retorna IDs de nós/arestas de um caminho existente; respeita direção quando solicitada e a vista quando informada. Uma busca sem caminho retorna `found:false` e listas vazias.
- `retrieve(graph, query, {limit=6, hops=1})`: busca trechos e relaciona entidades do catálogo. Retorna `mode:'local-text-graph'`, seeds, nós/arestas por ID, citações com hash fornecido e linhas originais 1-based, e lacunas explícitas. Não usa embeddings ou LLM.
- `validatePlan(plan)`: valida a especificação de um plano local. **Não executa** o plano e não valida credenciais ou permissões remotas.

Palavras comuns isoladas não retornam todos os documentos. Headers encontrados dentro de cercas de código não criam novas seções. Textos contendo HTML, scripts ou instruções são devolvidos como dados; o renderer deve continuar usando mecanismos seguros de texto/DOM.

Expansão de vizinhança e caminho têm significados diferentes. Um caminho não direcionado permite navegar uma relação em sentido reverso, mas a interface deve preservar a seta e o verbo originais. Nenhuma aresta entre vistas é criada para preencher lacunas.

Uma citação identifica um trecho recuperado; ela não prova sozinha uma conclusão. Cobertura lexical é uma heurística de busca, sem interpretação de probabilidade ou confiança factual. O score lexical serve para ordenação local e não é comparável a um score vetorial ou de avaliação de produto.

## Proveniência e estados de conhecimento

O catálogo inicial mistura evidência e implantação: `local` é exibido como “sem deploy”, mesmo quando notas recentes descrevem uma versão já implantada. São dimensões distintas e precisam campos separados.

```json
{
  "id": "entity:hub",
  "label": "Hub Logístico",
  "type": "system",
  "aliases": ["hub"],
  "evidence": "implemented",
  "deployment": {
    "environment": "production",
    "status": "verified",
    "revision": "SHA completo",
    "verified_at": "ISO-8601"
  },
  "provenance": [{
    "document_id": "doc:hub-production",
    "document_sha256": "SHA256",
    "section": "Processamento",
    "line_start": 10,
    "line_end": 20
  }]
}
```

Uma relação precisa também de tipo/verbo, origem, destino, documento/trecho de suporte, método de obtenção (`curated` ou `extracted`), estado de revisão, validade e snapshot. Uma relação extraída por modelo é uma proposta até revisão; não deve receber automaticamente o mesmo status de uma observação operacional.

Registrar separadamente `built_at`, `source_revision`, `index_version`, `graph_version`, `verified_at` e `observed_at`. Build recente, documento recente, índice recente e produção verificada não são equivalentes.

## Arquitetura evolutiva proposta

```text
Frontend
  → adapter offline atual / cliente HTTP versionado futuro
  → BFF autenticado com autorização por espaço
  → recuperação textual + Qdrant + grafo
  → compilação de contexto e citações
  → gateway de modelos
  → orquestrador com runs/eventos persistidos
  → ferramentas específicas, isoladas e autorizadas
```

Começar pelo catálogo curado permite provar caminhos de recuperação antes de extrair relações automaticamente. O serviço de grafo pode iniciar com uma implementação simples que preserve IDs e proveniência; escolher um novo banco não é necessário para esta melhoria local. Extração, resolução de entidades, revisão, busca híbrida e eventual sumarização de comunidades vêm depois, com um conjunto de perguntas de avaliação.

## Contratos de API para implementação futura

Nenhum endpoint abaixo é disponibilizado por esta wave. São contratos propostos para a próxima fase de backend.

| Endpoint | Entrada/resultado mínimo |
|---|---|
| `GET /v1/capabilities` | Modo, schema/API version, recursos realmente habilitados e permissões do usuário |
| `GET /v1/catalog` | Snapshot autorizado de entidades/relações com IDs, aliases, tipos e proveniência |
| `GET /v1/documents/:id` | Conteúdo autorizado, SHA256, revisão, seção/linhas e classificação |
| `POST /v1/retrievals` | Query, estratégia e filtros; candidatos/chunks, scores com método identificado, caminhos, exclusões, timings e snapshot |
| `POST /v1/answers` | Resposta, citações por claim/chunk, hashes de fontes e indicação de claims sem suporte |
| `POST /v1/runs` | Plano versionado, agentes, dependências, ferramentas permitidas, orçamento e chave de idempotência |
| `GET /v1/runs/:id` | Estado, passos, artefatos, consumo, responsável e causa de falha/bloqueio |
| `GET /v1/runs/:id/events` | SSE com event ID/sequence persistida e retomada de leitura |
| `POST /v1/approvals/:id/decision` | Decisão vinculada à ação exata e à versão/hash válida |
| `POST /v1/runs/:id/cancel` | Cancelamento auditado; explicação sobre ferramentas já iniciadas |

Todos os contratos precisam `request_id`, `schema_version`, `space_id` e estados de erro tipados. Resultados de recuperação também precisam `snapshot_id`, `index_version` e `graph_version`. IDs documentais devem ser estáveis e não permitir leitura arbitrária de caminhos do disco.

```json
{
  "request_id": "request-uuid",
  "schema_version": 1,
  "space_id": "space-id",
  "snapshot_id": "snapshot-id",
  "mode": "hybrid-text-vector-graph",
  "query": "Como a emissão é protegida?",
  "candidates": [{
    "chunk_id": "chunk-id",
    "document_id": "doc-id",
    "document_sha256": "SHA256",
    "score": {"value": 0.8, "method": "nome-do-metodo"},
    "section": "Emissão",
    "line_start": 10,
    "line_end": 18,
    "text": "Trecho autorizado"
  }],
  "paths": [{"node_ids": ["a", "b"], "relation_ids": ["relation-id"]}],
  "gaps": [],
  "timings_ms": {"retrieval": 20}
}
```

Isso é um exemplo futuro. O modo atual permanece `local-text-graph`, com o formato mínimo do `BrainCore` e sem model calls. Não usar os números deste exemplo como medição real.

## Plano local, DAG e execução futura

Schema **exato** do validador local: propriedade `version:1`; nome de etapa em `name`, não `title`.

```json
{
  "version": 1,
  "steps": [{
    "id": "research",
    "name": "Pesquisar fontes",
    "role": "researcher",
    "dependsOn": [],
    "tools": ["search", "read_graph", "read_sources"],
    "budgetSeconds": 30
  }, {
    "id": "review",
    "name": "Revisar evidências",
    "role": "reviewer",
    "dependsOn": ["research"],
    "tools": ["read_sources"],
    "budgetSeconds": 20
  }]
}
```

Papéis aceitos: `researcher`, `reviewer`, `writer`. Ferramentas aceitas: `search`, `read_graph`, `read_sources`. O validador rejeita dependências desconhecidas, ciclos, autorreferência, IDs repetidos, orçamento inválido e ferramentas externas. Limita o plano a 100 etapas. Exportar um plano válido não autoriza nem executa operações.

Para execução futura, o servidor deve impor limites de tempo, tokens/custo, chamadas, concorrência e número de tentativas. Ferramentas recebem permissões efetivas por agente/run; o nome do papel não concede acesso. O plano validado precisa versão/hash persistido, para impedir alteração entre aprovação e execução.

Estados de run sugeridos: `draft`, `queued`, `running`, `awaiting_approval`, `succeeded`, `failed`, `cancelled`, `budget_exceeded`. Estados de etapa: `pending`, `running`, `blocked`, `succeeded`, `failed`, `skipped`.

Eventos tipados: `run.created`, `run.started`, `step.started`, `retrieval.completed`, `artifact.created`, `approval.requested`, `approval.decided`, `step.completed`, `step.failed`, `run.completed`, `run.failed`, `run.cancelled`, `budget.exceeded`. Cada evento precisa sequência monotônica por run, timestamp do servidor, IDs run/step/request, responsável e payload sanitizado. O stream deve ser retomável sem duplicar ferramentas após reconexão. Exibir resumos de decisão e artefatos, não supostas cadeias internas de raciocínio.

Aprovação futura: persistir ação/argumentos redigidos, hash da ação, snapshot/plano, usuário autorizado, validade e estado. Rejeitar aprovação expirada, já consumida ou de outra versão. A API deve revalidar autorização ao executar; o frontend não é fronteira de segurança.

## Espaços, RBAC e ferramentas

- Autorizar documentos, chunks, entidades e relações **antes** da recuperação, da expansão e da geração. Um resultado oculto não pode vazar por citação, caminho, contagem ou artefato.
- Aplicar `space_id`/tenant e classification/ACL consistentemente no vault lógico, payload Qdrant, grafo, runs e caches. Não basta adicionar um filtro no frontend.
- Manter credenciais, tokens e chaves no backend. Browser e planos exportados recebem IDs de conexões, nunca valores secretos.
- Não expor `srv_api_run_safe_command` ao sistema web. Uma blocklist de strings de shell não limita adequadamente um agente com comando arbitrário. Preferir ferramentas operacionais específicas com parâmetros tipados, isolamento, allowlist e aprovação apropriada.
- Revisar `AutoAddPolicy` do SSH e usar identidade de host confiável antes de ampliar a superfície operacional.
- Validar leitura documental com resolução de caminho e contenção no diretório permitido. `get_system_architecture()` atualmente compõe um caminho sem a checagem de contenção usada pelo builder.
- Conteúdo de fontes é dado não confiável. Documentos não podem conceder ferramentas, alterar política de aprovação ou instruir agentes a divulgar credenciais.
- O bundle estático contém documentos integrais. Hospedá-lo publicamente entrega esse conteúdo; para a versão web, entregar somente dados autorizados por usuário/espaço.

## Ingestão consistente e observabilidade

A sincronização atual apaga vetores antigos antes de gerar novos embeddings. A exclusão no store suprime exceções. O manifest é um arquivo JSON sem lock/transação compartilhada; não oferece coordenação para múltiplos processos. Esses comportamentos precisam ser corrigidos antes de aumentar concorrência ou usuários.

Fluxo proposto: validar fonte → calcular hash/revisão → gerar chunks e embeddings em staging → validar dimensões/contagem → publicar nova versão do índice → tornar a versão ativa → retirar a antiga. Documentos removidos precisam estado auditável e falha de exclusão visível. Não anunciar ingestão concluída quando apenas se detectou uma mudança.

Expor jobs com estados `queued`, `running`, `succeeded`, `partially_failed`, `failed`; contagens separadas de arquivos detectados, publicados, removidos e falhos. Registrar duração, modelo/versão de embedding, retries, erro tipado e versão do índice. Comparar hash de citação com hash do documento servido para indicar fonte desatualizada.

## Critérios de aceitação da evolução

1. Consulta com termos desconhecidos produz fontes vazias e lacuna explícita.
2. Citação reproduz exatamente as linhas da revisão indicada; um hash divergente é sinalizado.
3. Caminhos usam somente relações existentes e exibem direção, tipo e fonte.
4. Usuário sem acesso não encontra documento, chunk, entidade derivada ou artefato restrito.
5. A interface distingue recuperação textual local, resultado vetorial, resposta do modelo e execução real.
6. Plano inválido não executa; aprovação vincula-se à mesma versão/ação executada.
7. Reconexão ao stream não duplica uma operação e permite recuperar a sequência perdida.
8. Orçamento e cancelamento são aplicados pelo servidor e auditados.
9. Falha de ingestão não substitui silenciosamente um índice válido por estado incompleto.
10. Benchmark de UX mede tarefas verificáveis. Um score local de interface não comprova superioridade funcional sobre plataformas completas com backend.

Testes locais do núcleo cobrem normalização, ranking/globalidade, offsets/hashes, cercas de código, strings XSS como dados, consultas sem resultado, limites de vizinhança, caminhos/direção/vistas e validação do DAG. Nenhum teste chama serviços externos.
