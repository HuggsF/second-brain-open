# Benchmark documental — plataformas web de agentes e RAG

Data: 8 de outubro de 2026. Pesquisa somente leitura, com fontes primárias. Nenhum repositório externo foi executado ou modificado. Este arquivo acompanha `benchmark.json`.

O top 3 do recorte amplo é **OpenClaw, Hermes Agent e DeepSeek Harness**. O n8n fica abaixo deles por estrelas. A seleção foi ampliada até consultar **todos os 29 repositórios públicos, não arquivados e sem forks acima de 200 mil estrelas**; a API retornou `incomplete_results=false`.

Critério de inclusão fixado: aplicação com interface web oficial utilizável, agentes executáveis e recuperação de conhecimento documentada. São aceitas integrações oficiais documentadas com provedores externos de memória/RAG; uma capacidade genérica de conectar qualquer MCP, sem integração de recuperação comprovada, não basta.

| Rank | Solução | Estrelas exatas | Captura UTC | Revisão fixada |
|---|---|---:|---|---|
| 1 | [OpenClaw](https://github.com/openclaw/openclaw) | 391.627 | 2026-10-08 16:12:20 | `dc203b5e486d3b931face78556019797dbe3f376` |
| 2 | [Hermes Agent](https://github.com/NousResearch/hermes-agent) | 252.153 | 2026-10-08 16:12:20 | `38880bd2f1e90dbc9a1aeec03af62539ee64719a` |
| 3 | [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) | 245.783 | 2026-10-08 16:15:03 | `5badb15009ae1756c3afe0ae0cef1faafc290ccc` |

Fontes exatas de estrelas: [API OpenClaw](https://api.github.com/repos/openclaw/openclaw), [API Hermes](https://api.github.com/repos/NousResearch/hermes-agent), [API DeepSeek Harness](https://api.github.com/repos/deepseek-ai/deepseek-harness). A varredura completa ocorreu às `2026-10-08T16:14:04.272262+00:00`, consulta `stars:>200000 fork:false archived:false`, ordenação por estrelas, 100 resultados por página.

As qualificações estão comprovadas:

| Solução | Web oficial | Recuperação de conhecimento | Dependências relevantes |
|---|---|---|---|
| OpenClaw | [Control UI](https://docs.openclaw.ai/web/control-ui), catálogo e acompanhamento de agentes | [Busca híbrida e Memory Wiki](https://docs.openclaw.ai/concepts/memory), com claims, evidências, conflitos e atualização | Embeddings exigem provedor configurado; Memory Wiki é plugin integrado |
| Hermes | [Web Dashboard](https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard/), profiles, sessões, logs, analytics e chat | [Session Search / memória](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory/) e [provedores semânticos](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory-providers/) | Memória básica é local; recuperação semântica/ingestão de documentos depende de providers, por exemplo OpenViking; chat web usa TUI via PTY e exige POSIX |
| DeepSeek Harness | [README oficial](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/README.md), comando `dsh web` | [Integração de memória MCP](https://deepseek-harness.github.io/deepseek-harness/en/guide/mcp-memory), com validação de gravação, recuperação entre sessões e uso na resposta | Providers externos, desativados por padrão; reference-memory oferece grafo e busca textual, sem embeddings; [subagentes](https://deepseek-harness.github.io/deepseek-harness/en/reference/subsystems/subagent) têm contratos explícitos |

Não confundir essa qualificação com GraphRAG semântico completo implementado por todos. DeepSeek Harness documenta uma integração de recuperação de conhecimento, incluindo grafo externo; seu provedor reference-memory utiliza busca por substring.

Outros candidatos registrados: n8n `206.887`, AutoGPT `187.684`, Dify `158.094`, Langflow `155.577`, Open WebUI `154.214`, RAGFlow `91.839`, LobeHub `83.059`, AnythingLLM `66.824`, LibreChat `45.410`. Flowise tinha `55.493` e `archived=true`. OpenCode `212.340` tem UI web e agentes, mas recuperação específica de conhecimento não foi comprovada nas fontes consultadas. Superpowers, ECC e coleções de skills não são plataformas web completas nesse recorte.

Para os pesos solicitados, recomenda-se congelar **subcritérios observáveis antes de pontuar as waves**. Uma nota documental deve ser chamada de *cobertura de recursos para as tarefas do Second Brain*, enquanto UX empírica requer executar os mesmos cenários nos quatro produtos.

| Dimensão | Peso | Subcritérios propostos |
|---|---:|---|
| Navegação | 14 | 7: navegação organizada e contexto ativo; 7: destinos/deep links identificáveis |
| Grafo | 18 | 6: visualização navegável de conhecimento; 6: filtros explícitos de nós/relações; 6: exploração de vizinhança/caminhos |
| Provenance | 16 | 8: fonte/conteúdo identificável; 8: origem e atualização verificáveis na interface |
| Busca | 12 | 6: busca utilizável; 6: escopo e resultados que permitam verificar o achado |
| Acessibilidade | 14 | 7: percurso por teclado; 7: semântica, foco e contraste verificados |
| Mobile | 10 | 5: adaptação prevista; 5: tarefas concluídas em viewport móvel |
| Persistência | 8 | 4: contexto selecionado sobrevive a navegação/reload; 4: estado de trabalho relevante preservado |
| Estados | 8 | 4: vazio/carregamento/erro distinguíveis; 4: recuperação sem perda ou falsa confirmação |

`Não avaliado` deve permanecer como intervalo `[0, peso]`; teste documentado de acessibilidade não prova conformidade completa, e ausência de menção em README não significa recurso ausente.

A matriz documental conservadora é esta; **os limites relativos ao grafo dependem de manter os três subcritérios explícitos acima** e avaliar o produto padrão com seus provedores documentados, sem adicionar interfaces próprias aos concorrentes:

| Dimensão | OpenClaw | Hermes | DeepSeek Harness |
|---|---:|---:|---:|
| Navegação | 14–14 | 14–14 | 7–14 |
| Grafo de conhecimento | 0–0¹ | 6–6² | 0–0³ |
| Provenance | 8–16 | 8–16 | 8–16 |
| Busca | 6–12 | 12–12 | 0–12 |
| Acessibilidade | 0–14 | 0–14 | 0–14 |
| Mobile | 0–10 | 5–10 | 0–10 |
| Persistência | 4–8 | 4–8 | 0–8 |
| Estados | 4–8 | 4–8 | 4–8 |
| **Faixa de cobertura documental** | **36–82** | **53–88** | **19–82** |

Evidências e limites das células de grafo:

1. **OpenClaw:** o painel Memory Wiki revisado apresenta clusters, cartões, contagens, páginas e preview, com atualização e conflitos. A implementação delimitada é [memory/view.ts](https://github.com/openclaw/openclaw/blob/dc203b5e486d3b931face78556019797dbe3f376/ui/src/pages/agents/memory/view.ts#L1056). Isso fornece navegação/provenance, mas não um explorador de nós/relações com filtros e vizinhança. O zero vale para esse **explorador interativo específico**, não para a existência de memória estruturada ou capacidade de produzir diagramas.
2. **Hermes:** não zerar o grafo inteiro. O chat web incorpora o TUI, onde `/journey` mostra gráfico/timeline de aprendizagem, permite selecionar um nó e consultar seu conteúdo. Os controles delimitados em [journey.tsx](https://github.com/NousResearch/hermes-agent/blob/38880bd2f1e90dbc9a1aeec03af62539ee64719a/ui-tui/src/components/journey.tsx#L294) incluem seleção, leitura, edição e exclusão, mas não filtros de relações e exploração por hops. A implementação tem modo `timeline`/`item` e visão gráfica estática na [linha 448](https://github.com/NousResearch/hermes-agent/blob/38880bd2f1e90dbc9a1aeec03af62539ee64719a/ui-tui/src/components/journey.tsx#L448).
3. **DeepSeek Harness:** o grafo está no servidor MCP externo e é acessado por ferramentas; os tipos de painéis entregues são guide, arquivos/document preview, browser e subagent chat, conforme [catálogo delimitado](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/docs/subsystems/sidebar-right.md#L139). Não há explorador nativo do grafo do provider nessa composição documentada.

Há um conflito na documentação de persistência do DeepSeek Harness: [sidebar-right.md, linha 11](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/docs/subsystems/sidebar-right.md#L11) diz que reload restaura layouts, enquanto [a seção “Not built”, linha 150](https://github.com/deepseek-ai/deepseek-harness/blob/5badb15009ae1756c3afe0ae0cef1faafc290ccc/docs/subsystems/sidebar-right.md#L150) diz que o estado é apenas em memória. Manteve-se `0–8`, sem presumir falha.

Essas faixas permitem dizer, se a UI local atingir mais de 88 sob os mesmos subcritérios e tiver evidência suficiente, que **superou o limite documental de cobertura das tarefas escolhidas**. Não permitem dizer que tem UX empiricamente melhor ou que supera essas plataformas em execução, escalabilidade, qualidade de RAG ou arquitetura.

Para arquitetura, avaliar à parte: schema de entidades/relações, identidade e provenance, recuperação híbrida e travessia real do grafo, citações, isolamento de agentes, contratos de execução, cancelamento/retomada, permissões e métricas. Plano de arquitetura, painel com dados simulados e agentes locais determinísticos devem receber rótulos distintos de backend RAG e execução multiagente reais.

## Protocolo de evidência e revisão

- `documented_present`: capacidade explicitamente descrita em fonte oficial ou demonstrada em código delimitado da revisão fixada; não equivale a usabilidade medida.
- `documented_absent_in_scoped_ui`: subcritério não fornecido pela interface padrão delimitada e revisada; não equivale a impossibilidade de extensão, ausência de arquitetura de grafo ou ausência em qualquer produto/configuração futura.
- `not_evaluated`: evidência insuficiente; intervalo inclusivo `[0, peso]`.
- `conflicting_documentation`: fontes oficiais conflitantes; mantém-se intervalo inclusivo sem presumir a pior versão.
- UX empírica, contraste real, foco, tempos, responsividade e execução de tarefas dos concorrentes não foram testados nesta pesquisa.
- Nenhuma nota local ou condição de vitória está afirmada neste relatório. A UI local deve receber revisão independente, com cenário e evidência por subcritério.
- Os pesos somam 100. O limite documental máximo selecionado é 88. A condição estreita de comparação é `local_verified_task_coverage > 88`; sua conclusão nunca deve ser rotulada como superioridade geral de UX ou plataforma.

## Dados da varredura ampla

Captura UTC `2026-10-08T16:14:04.272262+00:00`, 29 resultados, `incomplete_results=false`:

| Repositório | Estrelas |
|---|---:|
| codecrafters-io/build-your-own-x | 552167 |
| sindresorhus/awesome | 516422 |
| public-apis/public-apis | 486901 |
| freeCodeCamp/freeCodeCamp | 456931 |
| EbookFoundation/free-programming-books | 398691 |
| openclaw/openclaw | 391627 |
| donnemartin/system-design-primer | 373609 |
| nilbuild/developer-roadmap | 369152 |
| jwasham/coding-interview-university | 362512 |
| vinta/awesome-python | 326031 |
| awesome-selfhosted/awesome-selfhosted | 324830 |
| obra/superpowers | 296649 |
| practical-tutorials/project-based-learning | 286258 |
| mattpocock/skills | 280851 |
| 996icu/996.ICU | 277269 |
| affaan-m/ECC | 275342 |
| NousResearch/hermes-agent | 252153 |
| torvalds/linux | 251450 |
| react/react | 250935 |
| trimstray/the-book-of-secret-knowledge | 248679 |
| deepseek-ai/deepseek-harness | 245783 |
| TheAlgorithms/Python | 225271 |
| multica-ai/andrej-karpathy-skills | 217568 |
| vuejs/vue | 212796 |
| anomalyco/opencode | 212340 |
| ossu/computer-science | 209975 |
| n8n-io/n8n | 206887 |
| DigitalPlatDev/FreeDomain | 203159 |
| tensorflow/tensorflow | 200736 |

As estrelas são um snapshot de popularidade, não um componente da pontuação de qualidade. Repositórios fora dos três selecionados foram excluídos por não satisfazerem a combinação exigida de plataforma web oficial, agentes e recuperação de conhecimento documentada, ou por terem menos estrelas do que os três elegíveis selecionados.
