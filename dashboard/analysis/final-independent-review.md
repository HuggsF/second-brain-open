# Revisão independente das waves locais

Data: **08/10/2026**, America/Sao_Paulo. Escopo: implementação em staging do dashboard local. Esta revisão inspeciona código e testes; **não controla o navegador**. Observações de QA do navegador executadas pelo responsável pela implementação devem ser anexadas separadamente, com tarefas e resultado.

O revisor participou da implementação do renderer Markdown, mas não implementou `app.js`, `graph-ui.js`, `core.js`, `workbench.js`, CSS, catálogo ou build. A revisão de integração e contratos é independente dessas implementações; testes do renderer não equivalem a auditoria externa de toda sua segurança.

## 1. Correções identificadas antes da pontuação

| Item | Achado na primeira revisão | Evidência | Estado no segundo passe |
|---|---|---|---|
| R-01 | Seleção da lista com vizinhança ativa recriava a lista e tentava restaurar foco no SVG oculto. | `graph-ui.js:84–117` | Corrigido: restaura em SVG ou lista conforme o modo. Exige confirmação de tarefa por teclado. |
| R-02 | Busca global de entidade preservava filtros de domínio/vizinhança do grafo, que podiam esconder e apagar a seleção. | `app.js`, função `globalSearch` | Corrigido: navegação limpa `domain` e `focus`. |
| R-03 | Valores de URL `constructor`/`__proto__` passavam em lookups de objetos; `mode` inválido podia ocultar os dois modos do mapa. | `app.js`, função `readRoute` | Corrigido com `Object.hasOwn` e whitelist de modo; IDs de nó/aresta/domínio são reconciliados. |
| R-04 | Snapshot malformado com `documents` ausente não tinha recuperação; null em `views`, `issues` como string ou edge sem ID podia causar falha. | `schema.js:8–30`; guard de `app.js:6` | Corrigido por schema dedicado: shape, limites, hashes, IDs únicos, listas, vistas não vazias, referências próprias e edges compatíveis. Regressões Node passam sem exceção. |
| R-05 | Busca “J&T” não tinha tokens elegíveis porque descartava J e T isolados. | `core.js:14–19` | Corrigido: sigla com ampersand é normalizada como `jt`; reprodução Node encontrou resultados. |
| R-06 | Importação de plano aceitava orçamento de `1e308`, apesar do input de UI limitar a 86400. | `core.js:242`, `workbench.js:93–109` | Corrigido: validator rejeita orçamento acima de 86400; reprodução Node rejeitou o plano. |
| R-07 | Documento acima de 500.000 caracteres era truncado sem aviso, enquanto o build aceita até 1MB. | `markdown.js:93`, `build_graph.py`, reader em `app.js` | Corrigido: renderer retorna `truncated`, reader avisa e exportação preserva o original completo. As 30 fontes atuais têm no máximo 26.013 caracteres. |
| R-08 | Skip link `#main` substitui a URL da rota; a tela permanece, mas reload perde o destino original. | `index.html:19`; handler da classe `.skip` em `app.js` | Corrigido: preventDefault, foco e scroll em `main` preservam hash. |
| R-09 | TOC armazena texto do heading, embora IDs únicos existam. Reload de seção homônima resolve o primeiro heading. | `app.js`, `renderReader` | Corrigido: TOC persiste ID e restauração prioriza ID exato. |
| R-10 | Range de citação vindo da URL pode produzir `start > lines` ou `end < start`, com badge impossível e trecho vazio. | `app.js`, bloco `if(options.lineStart)` | Corrigido: clamp para range válido, com aviso explícito de ajuste. |
| R-11 | Referências URL `doc=__proto__` ou `constructor` acessavam propriedade herdada de documents e podiam interromper o reader. | `app.js`, funções `openDoc` e `renderReader` | Corrigido com `Object.hasOwn`: fonte desconhecida apresenta estado específico. |
| R-12 | A relação horizontal Hub → Corpem podia atravessar o card intermediário J&T e ocultar a ligação real. | `graph-ui.js:94–105` | Corrigido: relação longa na mesma linha usa portas inferiores e curva abaixo dos cards; labels têm posição própria. |

Um plano inválido persistido **não é, por si só, bug**. Preservar um rascunho com ciclo enquanto o usuário o corrige é uma decisão legítima. O loader valida shape suficiente para editar, o workbench mostra os erros, importação/exportação exige `validatePlan.ok` e nenhum plano é executado. O aceite deve testar que um rascunho inválido reabre como inválido, sem confirmação de sucesso ou exportação autorizada.

## 2. Melhorias comprovadas por código

- Arquitetura de informação com visão geral, biblioteca, grafo, consulta de evidências e preparação de planos. O frontend distingue preparação local de execução indisponível.
- Busca global por entidade e texto completo, normalização de acentos, resultados explícitos, snippets e navegação até linhas da fonte. Não chama modelo ou serviço externo.
- Mapa e lista, controles explícitos de zoom, pan por pointer, filtros de vista/evidência/domínio, vizinhança de 1–2 saltos e caminho mínimo por relações existentes.
- Reader com SHA256, snapshot, data de arquivo identificada corretamente, trechos com offsets 1-based, TOC, wikilinks e backlinks.
- Persistência versionada de tema, favoritos, fontes recentes, consultas e rascunho de plano; hash da URL representa página, fonte, seleção e filtros relevantes.
- Vazio, fonte ausente, carregamento inicial, erro de snapshot e persistência indisponível possuem mensagens distintas.
- Markdown não usa `innerHTML`, não cria imagens remotas, não admite URLs javascript/data/file e usa `noopener noreferrer` em links externos. Código/documentos recuperados continuam texto.
- Build contém fontes dentro do vault e testa existência de nós/vistas/arestas e coordenadas finitas. O catálogo separa nível de evidência e implantação documentada.
- Plano admite apenas papéis e ferramentas locais definidos; valida ciclos, IDs, dependências e orçamento. A UI não inventa tempos, custos ou agentes em execução.

## 3. Evidência de testes e limites

Na execução independente final da suíte, **29 testes Node e 4 testes Python passaram**: 14 de core, 8 de Markdown, 7 de integração e 4 do build. Eles cobrem normalização, busca, ranking, offsets/hashes de citações, conteúdo não confiável, ausência de evidência, não mutação, saltos/caminhos, DAG/allowlist, URLs, wikilinks, tabelas/listas/código, limites, snapshot malformado, sigla J&T, hashes reais do vault, orçamento máximo e contenção de caminhos no build. Os quatro testes Python inicialmente foram bloqueados pelo sandbox na criação de fixtures; rerodados fora dessa restrição, passaram. Isso foi limitação de ambiente, não falha do código.

Reprodução adicional após ajustes: consulta “J&T” retorna resultados; plano com orçamento `1e308` é rejeitado; snapshot contém 30 fontes com máximo de 26.013 caracteres. Testes de DOM/navegação adicionais escritos pelo implementador ainda devem ter seus resultados anexados, sem confundir fake DOM com comportamento real de focus, layout ou leitor de tela.

Contraste calculado independentemente a partir dos tokens CSS sobre o painel: tema escuro texto **14,78:1**, secundário **8,13:1**, accent **12,80:1**; tema claro texto **15,19:1**, secundário **6,62:1**, accent **6,70:1**. Good/warn/blue/violet/danger também têm pelo menos 6,5:1 nesses pares. Isso é verificação matemática de cores, não avaliação de foco visível real ou legibilidade de cada combinação possível.

Não foi executado pelo revisor: navegador, leitor de tela, gestos em dispositivo touch, Lighthouse, teste de concorrentes, retrieval semântico, backend HTTP/MCP, execução de agentes ou teste de escala. Esses itens não recebem crédito por aparência ou intenção.

QA de navegador informado pelo implementador e aceito como evidência complementar em 08/10: Enter no nó Hub mantém foco no SVG; lista em viewport 375px com vizinhança ativa preserva foco após recriar o nó Bling; Ctrl K abre/foca busca e Esc devolve foco; skip link por Enter foca main sem alterar hash; consulta por Enter retorna seis fontes com F1, hash e linhas 19–24 verificáveis; favoritos persistem após reload; voltar restaura consulta; ciclo do plano reaparece como inválido e bloqueia exportação; nome de rascunho persiste. No roteiro móvel, lista padrão → Bling → fonte apresenta duas tabelas e fonte de 14px, sem overflow horizontal da página. Consulta sem evidência e consulta rollback, edição de plano e reload também passaram em viewport 375×812.

O registro consolidado é [qa-evidence.json](qa-evidence.json), gravado às 17:05:52 UTC de 08/10/2026. Teste real de snapshot malformado mostrou recuperação sem erros de console; busca ficou indisponível de forma explícita. Referência `doc=__proto__` mostrou fonte não encontrada. O registro inclui console sem erros ao concluir os fluxos. O revisor inspecionou as capturas [mobile-reader.jpg](mobile-reader.jpg) e [mobile-plan.jpg](mobile-plan.jpg): layout estreito, textos/campos legíveis e indicação explícita de preparação sem execução. Interações e medidas do navegador foram executadas pelo implementador, não por este revisor.

## 4. Pontuação comparável: cobertura de tarefas

A pontuação final precisa seguir os **17 subcritérios** de `benchmark.json`, com pesos 14/18/16/12/14/10/8/8. Isso evita substituir o método por notas parciais arbitrárias para superar um alvo. O baseline 37/100 de `360-audit.md` é uma avaliação qualitativa provisória, **não diretamente comparável** a esse método binário/intervalar consolidado.

Estados: presente quando demonstrado; não verificado representa intervalo `[0,peso]`; ausência comprovada no escopo representa zero. Resultado de código e resultado empírico ficam identificados separadamente.

| Dimensão / subcritério | Peso | Avaliação final e evidência |
|---|---:|---|
| Navegação: contexto ativo | 7 | Presente por código: áreas, heading, breadcrumb e aria-current. |
| Navegação: destinos/deep links | 7 | Presente: rotas identificáveis, TOC por ID; skip link preserva hash e voltar/reload testados. |
| Grafo: visualização navegável | 6 | Presente por código: seleção, pan, zoom e lista equivalente. |
| Grafo: filtros explícitos | 6 | Presente por código: vista/evidência/domínio e seleção reconciliada. |
| Grafo: vizinhança/caminhos | 6 | Presente por código e testes: 1–2 saltos, caminho mínimo e direção. |
| Provenance: fonte/conteúdo | 8 | Presente por código e testes: reader e trechos reais. |
| Provenance: origem/atualização | 8 | Presente: hash/linhas reais conferidos em integração, data de arquivo e snapshot distintos; ranges e truncamento têm aviso. |
| Busca: utilizável | 6 | Presente por código e testes: texto completo, acentos e resultados explícitos. |
| Busca: escopo/achado verificável | 6 | Presente por código e testes: categorias, entidades/fontes, snippets, fonte e linhas. |
| A11y: percurso por teclado | 7 | Presente: QA Enter no SVG/lista com vizinhança, Ctrl K/Esc, skip link, consulta por Enter. |
| A11y: semântica/foco/contraste | 7 | Presente no escopo: labels/dialogs/buttons/tabelas semânticos, foco testado e contrastes calculados nos dois temas. Não é auditoria WCAG completa. |
| Mobile: adaptação prevista | 5 | Presente por código: media queries e lista padrão abaixo de 650px. |
| Mobile: tarefa em viewport móvel | 5 | Presente: QA 375×812 com lista → seleção → fonte, consulta e plano; largura de página 360px e capturas inspecionadas. |
| Persistência: contexto em navegação/reload | 4 | Presente: rotas/filtros/seleções, hash preservado, favorito/reload e voltar/consulta testados. Câmera/scroll não fazem parte desse item estreito. |
| Persistência: trabalho preservado | 4 | Presente: favoritos/histórico/rascunhos; nome e ciclo sobrevivem ao reload, com erro de validação preservado. Falha de storage mantém sessão por código. |
| Estados: vazio/carregamento/erro | 4 | Presente: vazio do grafo, consulta sem evidência, fonte ausente e snapshot malformado testados; carregamento inicial distinto. |
| Estados: recuperação sem perda/falsa confirmação | 4 | Presente: inválido não é exportado, restauração do modelo funciona, snapshot inválido oferece recovery, fontes ausentes e storage têm feedback; nenhuma execução inventada. |

**Pontuação final: 100/100 de cobertura das tarefas delimitadas**, com os mesmos 17 subcritérios e pesos do benchmark. Os 12 pontos antes não verificados foram fechados com o roteiro móvel e a evidência de semântica/foco/contraste acima; não foram preenchidos com estimativa. Esse score binário informa que os affordances pedidos estão presentes e verificáveis no escopo local; **não representa qualidade perfeita, ausência de bugs ou UX universalmente superior**.

Conforme [benchmark.json](benchmark.json), os intervalos documentais das referências são OpenClaw `[36,82]`, Hermes Agent `[53,88]` e DeepSeek Harness `[19,82]`. A cobertura local 100 supera o limite superior documental máximo 88 **nesse recorte**. As referências não receberam o mesmo ensaio empírico; por isso, a conclusão não é vitória em usabilidade, qualidade de RAG, execução de agentes ou maturidade da plataforma. Estrelas não compõem esse score.

## 5. Gaps residuais e riscos

- O mapa é curado e pequeno; não há comunidades/cluster automático, dados ao vivo ou benchmark de escala. Não afirmar que já suporta catálogo empresarial grande.
- A legenda não cobre explicitamente E-commerce, embora o domínio use cor distinta; manter esse gap de clareza visual na avaliação qualitativa.
- Câmera, scroll e aba do inspector não são restaurados. O critério de contexto selecionado é mais estreito do que restauração completa da sessão.
- Busca é lexical e expandida por relações curadas. Não recebe pontos de embeddings, GraphRAG semântico ou resposta gerada.
- Planos são preparação contratual. Não recebe pontos de execução multiagente, autenticação, SSE, cancelamento operacional ou retomada durável.
- Toda a base Markdown selecionada está no bundle local. A futura publicação precisa separar dados por autorização; servidor local não é controle multiusuário.
- Revisão de fontes por hash não prova que o fato é atual. A UI corretamente rotula modificação de arquivo e snapshot; continuará precisando de revisão semântica de claims.

## 6. Roteiro de QA e limites do encerramento

Roteiros principais fechados em `qa-evidence.json`; os itens abaixo também orientam manutenção e testes adicionais, sem ampliar a alegação de cobertura:

1. Teclado: Ctrl/⌘ K → resultado → grafo → lista → seleção com vizinhança → Tab continua; diálogo Esc devolve contexto.
2. Deep link: selecionar nó/fonte, ativar skip link, recarregar e preservar destino; heading homônimo reabre a seção correta.
3. Mobile: viewport 375px ou equivalente; pesquisar, abrir fonte, seguir relação e voltar sem texto miniaturizado ou página com overflow horizontal.
4. Falhas: snapshot ausente/malformado, hash inválido, fonte removida, range impossível e localStorage negado.
5. Plano: criar ciclo, sair/reabrir, confirmar estado inválido; exportação recusada; importar inválido mantém trabalho existente.
6. Segurança: Markdown com HTML/URL perigosa permanece dado; nenhuma chamada de ferramenta/backend é disparada por documento.

Conclusão permitida: cobertura maior das tarefas delimitadas do benchmark documental. Conclusão proibida: UX empiricamente superior aos concorrentes, plataforma superior em RAG/agentes, ou prontidão de produção multiusuário. Ainda não houve pesquisa com usuários, auditoria completa com leitor de tela, teste de escala ou avaliação do backend futuro.
