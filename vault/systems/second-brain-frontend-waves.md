# Second Brain — evolução local do frontend
Data: 2026-10-08 · KIOSK Brands · escopo local.

## Resultado e interpretação do score
A implementação atende aos **17 subcritérios binários de cobertura de tarefas**, totalizando **100/100**. A revisão independente está em `dashboard/analysis/final-independent-review.md`; os testes e observações em `dashboard/analysis/qa-evidence.json`.

Este número mede presença e verificação dos recursos definidos antes da implementação. **Não mede qualidade perfeita nem comprova UX global superior**. A auditoria inicial de 37/100 era qualitativa e provisória, portanto não é uma diferença numérica diretamente comparável com esta nota binária.

| Referência no recorte aprovado | Estrelas no snapshot GitHub | Cobertura documental conservadora |
| --- | ---: | ---: |
| [OpenClaw](https://github.com/openclaw/openclaw) | 391.627 | 36–82 |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | 252.153 | 53–88 |
| [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) | 245.783 | 19–82 |
| Second Brain local | Não se aplica | 100, para os cenários verificados |

Referências capturadas em 08/10/2026, 16:12–16:15 UTC (13:12–13:15 de Brasília), com revisões fixadas. A pesquisa avaliou todos os 29 repositórios públicos não arquivados, sem forks, acima de 200 mil estrelas. Critério: UI web oficial, agentes executáveis e recuperação de conhecimento documentada, incluindo providers oficiais externos. O inventário, fontes primárias, dependências e incertezas estão em `dashboard/analysis/benchmark-2026-10-08.md` e `benchmark.json`.

Recursos não avaliados nos concorrentes permaneceram com intervalo [0,peso], sem penalização presumida. O limite documental máximo ficou em 88; a cobertura local auditada o ultrapassa. Os concorrentes **não foram submetidos ao mesmo ensaio empírico**. Popularidade não compõe o score; grafo recebeu peso alto por ser uma tarefa central deste Second Brain.

## Quatro waves executadas
### Wave 1 — orientação e leitura
Navegação Visão geral / Conhecimento / Grafo / Consultas / Planos; hierarquia de leitura, biblioteca de todo o vault, busca global, favoritos, fontes recentes e temas. Renderer Markdown sem HTML executável, com listas, tabelas, código, links HTTP(S) seguros e wikilinks. Origem, SHA-256 e data do arquivo são consultáveis. A data do arquivo não é apresentada como confirmação de fatos.

### Wave 2 — contexto do grafo
Três perspectivas com posições compactas e estáveis; filtros de entidade, domínio, evidência e relação; foco em um ou dois saltos; caminhos com direção opcional; fonte de cada aresta; lista equivalente e tabela de relações. Relações não adjacentes usam corredor inferior para evitar passar por dentro de outro card. Código e implantação têm campos separados; produção e HML apontam para documentos próprios. A implantação de 08/10 é um snapshot, não saúde ao vivo.

### Wave 3 — recuperação e preparação de agentes
Consulta textual determinística com expansão do catálogo, trechos exatos, linhas, hashes, entidades e lacunas. Não há resposta gerada por IA. Histórico e exportação de contexto são locais.
Editor funcional de planos versionados: papéis, dependências, ferramentas permitidas e budgets até 86.400 segundos por etapa. Ciclos, IDs duplicados, dependências desconhecidas e ferramentas externas são rejeitados na validação. Importação e exportação exigem contrato válido. Rascunhos inválidos podem persistir para correção, com erro explícito; nunca são executados.

### Wave 4 — revisão e correções
Revisão independente encontrou e orientou correções para: foco perdido na lista, filtros antigos na busca global, schemas malformados, propriedades herdadas em URLs, intervalos de citação impossíveis, atalhos de diálogo, skip link que substituía o hash, headings repetidos, sigla J&T não recuperada e limites de tamanho não informados. O leitor recebe foco em tela móvel; a lista é o padrão móvel do grafo. Os critérios foram mantidos e a nota foi fechada somente após QA.

Não foram inventadas notas intermediárias para as waves. Os marcos são mudanças e verificações de recursos; o score comparável é o da versão final.

## Verificação
- 29 testes Node: busca, ranking, trechos/linhas/hash do vault real, caminhos, desconexão, validade do DAG, orçamentos, XSS/URLs, renderer e schemas inválidos.
- 4 testes Python: catálogo completo, escapes de script, identidade estável, travessia de diretório, IDs, coordenadas e arestas.
- Navegador: Enter em SVG e lista mantém foco; Ctrl/⌘+K abre busca; Esc fecha e devolve foco; skip preserva o deep link; busca sob filtros mostra a entidade correta; favoritos, tema e rascunhos sobrevivem ao reload; Back restaura consulta; ciclo bloqueia exportação.
- 375×812: leitura com tabelas, consulta com fontes e edição de plano concluídas; texto do Markdown 14px; largura do documento 360px, sem overflow da página. Capturas em `dashboard/analysis/mobile-reader.jpg` e `mobile-plan.jpg`.
- Snapshot malformado e referência `__proto__` mostram erro recuperável. Console sem erros nos fluxos verificados.
- Texto normal e cores de evidência têm contraste acima de 4,5:1 nos temas verificados. Não houve auditoria completa WCAG, teste com leitor de tela ou pesquisa com usuários.
- Sem ensaio de desempenho com grandes catálogos. O catálogo atual tem 19 entidades e 16 relações; a biblioteca cresce com os Markdown do vault.

## Arquitetura e próximos passos
A UI usa um snapshot validado (`schema.js`), serviços puros de busca/grafo/planos (`core.js`), renderer seguro (`markdown.js`) e módulos de apresentação (`app.js`, `graph-ui.js`, `workbench.js`). Essa divisão permite substituir o adapter local sem acoplar documentos à interface.

O backend existente usa Qdrant/Ollama e MCP. Isso **não torna esta UI uma aplicação GraphRAG semântica ou multiagente executável**. A execução, observabilidade ao vivo, busca vetorial e geração de respostas não foram conectadas.

A sequência recomendada é:
1. BFF autenticado, espaços e autorização por documento; nunca enviar todo o vault ao navegador de um usuário sem verificar acesso.
2. Contratos versionados de catálogo, fontes e chunks com identidade/hash/linhas; ingestão consistente antes de trocar a versão visível.
3. Recuperação híbrida textual/vetorial/grafo, ranking e compilação de contexto com citações.
4. Gateway de modelos com limites, avaliação de respostas e tratamento de documentos como dados.
5. Orquestrador durável de DAG, eventos SSE, sequência para retomada, cancelamento e orçamento.
6. Ferramentas isoladas, allowlist e aprovação vinculada ao conteúdo de ações externas.
7. Observabilidade real, avaliações com usuários e ensaios comparáveis nas referências.

Detalhes: [[second-brain-graphrag-multiagent]], [[second-brain-frontend-360]].

## Uso e atualização local
```powershell
cd C:\KIOSK\second-brain
.\.venv\Scripts\python.exe dashboard\build_graph.py
.\.venv\Scripts\python.exe dashboard\serve.py --port 8847
```
Abrir http://127.0.0.1:8847/dashboard/. O servidor limita os arquivos ao dashboard, sem listar diretórios, e só escuta em loopback. Se a porta já estiver ocupada, use outra porta e seu URL correspondente.
Alterar o vault não atualiza automaticamente a página: gere o snapshot e recarregue. A biblioteca é uma cópia local verificável, não um monitor de produção. Nenhum segredo ou API externa foi incorporado à UI.

## Restauração
Antes da instalação local, os arquivos originais e documentos alterados são preservados em `.frontend-backups`, com manifesto de hashes. Restaure a lista de arquivos originais do manifesto e gere novamente o grafo se desejar refletir o vault atual. Mova arquivos introduzidos para uma pasta de recuperação, se quiser remover a nova UI; preserve os relatórios e os documentos de conhecimento. Restauração de frontend não reinicia serviços do hub nem modifica bancos.
A chave `kiosk.brain.v1` contém apenas preferências, favoritos, consultas e planos deste navegador. Exportar um plano válido antes de limpar a chave evita perder esse trabalho.

Todas as alterações desta tarefa são locais. Nenhuma PR, publicação ou implantação externa foi feita.
