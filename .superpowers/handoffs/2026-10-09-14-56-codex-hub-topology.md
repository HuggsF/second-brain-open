# Handoff Codex — mapa operacional do Hub

## Estado para retomar

Implementação local concluída e revisada. Publicação da PR depende de ordem específica do Hugo. Escopo aprovado: somente Hub production/hml no dashboard do Second Brain; nenhuma alteração no Hub, backend/coletores, vault ou graph-data.js.

- Base: main 0b25f50.
- Branch de implementação: codex/feat/hub-topology.
- Worktree: C:/KIOSK/second-brain-worktrees/hub-topology.
- Código final: fed888b; documentos de entrega entram em commit posterior (consultar git log).
- Checkout original C:/KIOSK/second-brain permanece em codex/docs/handoff-second-brain-2026-10-09/0b25f50 com handoffs locais preservados. Continue o código no worktree acima.
- Clone de prova: C:/KIOSK/second-brain-worktrees/verification-hub-topology-2026-10-09; git clone --no-local de fonte local, origin removido, sem rede.
- Spec/plano/ledger: .superpowers/specs/2026-10-09-14-29-hub-topology-design.md, .superpowers/plans/2026-10-09-14-29-hub-topology.md, .superpowers/ledger/2026-10-09-14-29-hub-topology.md.
- PR preparada em .superpowers/prs/2026-10-09-14-56-hub-topology.md; ainda não publicada.

## O que mudou

Mapas em Observabilidade, produção/homologação lado a lado no desktop e empilhados no celular. Quatro aspectos do mesmo Hub: processo PM2, HTTP interno, HTTP público e SQLite/fila. Dependências dirigidas; motivo, checks, data/idade, última tentativa e fontes; teclado e lista equivalente.

Modelo puro hub-topology.js sem IO. Estados usam as duas amostras e indicadores atribuíveis, nunca report.ok sozinho. Hml espera worker/emissão desligados; SHA esperado vem do relatório. Vencimento em >180 s. Falha de coleta ou resposta inválida conserva a evidência anterior como histórico amarelo, mantendo checks e motivos, inclusive falha anterior.

Consultas de ambientes, estado atual e histórico são independentes: pendência de hml/history não bloqueia nova consulta production. Envelhecimento continua durante requisição pendente. Navegação/dispose descarta retornos tardios. Foco, seleção e detalhes abertos são preservados. Histórico usa a avaliação das verificações e avisos da coleta.

Teste Qdrant agora usa dois clientes reais em memória, com create/get/upsert e prova de isolamento (counts 1/0). Nenhum comportamento de produto Python mudou; não há execução de testes pela UI do Second Brain.

Latência não implementada: o contrato não fornece latência HTTP do Hub. Não apresentar duration_ms do MCP como latência do Hub.

## Commits locais

- 18b8df5 — docs: define o mapa operacional do Hub e o plano de execução
- 04ca4dd — feat(dashboard): projeta estados e dependências internas do Hub
- 92639e9 — test: isola verificação do Qdrant em memória
- fed888b — feat(dashboard): exibe mapa operacional e preserva observações do Hub

Sem push, merge, criação de repositório remoto ou PR publicada.

## Método e revisão

Hugo aprovou todas as etapas locais e pediu ciclos multiagentes. Classificação bounded; spec/plano antes do código; três implementadores com arquivos exclusivos. Coordenador integrou e verificou. Revisores independentes de semântica, UI, segurança e entrega geral; a última revisão usou contexto limpo e diff 0b25f50..fed888b, incluindo Qdrant por revisor que não o implementou.

TDD: modelo RED por módulo ausente, GREEN 40/40 após metadata; UI RED inicial 10 falhas, regressão de foco e duas de pendências. Revisão encontrou Important de cache substituído por dados inválidos e variante observation:null com metadata inválida; regressões vistas RED (12 e 6 falhas), corrigidas e revistas. Minor do histórico e fonte SQLite:61 corrigidos. GREEN focal final 35/35; Node completo 105/105. Recheck repetiu os três repros. Revisor final reportou nenhum Critical/Important/Minor remanescente e verificou 75 testes focalizados.

## Evidências

Worktree e clone limpo passaram os mesmos gates em processos filhos sem variáveis de configuração do projeto. Somente variáveis básicas Windows necessárias à execução foram preservadas; .env ausente nos dois. Python externo já disponível em C:/KIOSK/second-brain/.venv/Scripts/python.exe, sem ativação/cópia de venv.

Saída confirmada:

```text
Python: Ran 143 tests ... OK; exit_code=0
Node: tests 105; pass 105; fail 0; exit_code=0
Builder: Ran 4 tests ... OK; exit_code=0
Evidence lint: sem problemas; exit_code=0
```

Comandos: 12 módulos unittest do CLAUDE.md; node --test --test-isolation=none dashboard/tests/*.test.cjs (arquivos explicitamente expandidos pelo runner); Python dashboard/tests/test_build_graph.py; cli.py evidence --lint via CliRunner com SQLite temporário. Sem --test-isolation=none, Node encontrou EPERM no spawn antes dos testes neste host; o modo sem subprocessos evita isso.

Runner/saídas em C:/Users/HugoMelo/AppData/Local/Temp/kiosk-hub-topology-2026-10-09/: verify.py, worktree-verification.log, clean-clone-verification.log (scratch não versionado). Runner cria ambiente somente com SYSTEMROOT, WINDIR, COMSPEC, PATH, PATHEXT, TEMP, TMP, USERPROFILE, APPDATA, LOCALAPPDATA, PROGRAMFILES, PROGRAMFILES(X86), PROGRAMDATA. Cwd de cada gate é o checkout em prova com seu próprio vault; valida ausência de .env. Cli evidence lint usa SQLite temporário. Não rodou cli.py sync porque vault intacto.

Clone limpo após gates; .env, .runtime, .brain_hashes.json e .test_manifest.json ausentes. Diff de vault/graph-data.js contra 0b25f50 vazio. Diagnósticos Ollama/trace/boom são cenários simulados dos testes, não serviços iniciados nem falhas da suíte.

QA real no navegador com apenas servidor estático loopback porta 8859: ambos os mapas offline, seleção por Enter de SQLite e dependência inversa. Celular 390: clientWidth/scrollWidth 375/375, sem rolagem horizontal. Viewport restaurado, tab fechada e servidor estático encerrado. BFF/Qdrant/Ollama/Docker não iniciados; saúde real de produção/hml não consultada.

Prévia salva em C:/Users/HugoMelo/.codex/visualizations/2026/10/09/01a120e2-e494-75f1-88a1-84f8fbdf3da8/hub-topology-offline.jpg.

## Próximo passo e limites

Finishing-a-development-branch: branch/worktree preservados conforme regra de não publicar sem ordem específica. PR local preparada com causa raiz/correção/evidências. Se Hugo ordenar a publicação nessa ocasião, publicar codex/feat/hub-topology e abrir PR contra main; anexar URL ao chat. Não inferir merge/deploy.

Pendências anteriores do handoff 2026-10-09-14-13-codex-handoff.md seguem fora deste passo: esta entrega não rotaciona credenciais nem faz auditoria fiscal. Nunca reproduzir valores; não commitar .env/.runtime/.brain_hashes.json, iniciar serviços ou escrever em produção/hml.
