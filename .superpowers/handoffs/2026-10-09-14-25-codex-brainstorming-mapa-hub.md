# Handoff: brainstorming do mapa de topologia do Hub

Data: 2026-10-09, 14:25 (America/Sao_Paulo). Dono: Hugo.

## Novas instruções e aprovações

Hugo autorizou ciclos multiagentes e pediu amplo uso dos recursos disponíveis. Em seguida esclareceu o escopo: "Apenas o Hub inclusive". Interpretação refletida ao usuário: somente Hub em produção e homologação, sem nós de sistemas externos nem ampliação para toda a holding.

O desenho detalhado, a spec escrita e o plano ainda não foram aprovados. A autorização dos ciclos multiagentes e a definição de escopo não foram tratadas como autorização para pular os gates que Hugo estabeleceu.

## Ciclo multiagentes realizado

Três agentes, somente de leitura, em paralelo:

- hub_contrato: sinais existentes, BFF, MCP e preservação de observações.
- hub_interface: alternativas da tela, mapa/lista acessível e isolamento por ambiente.
- hub_semantica: revisão independente do significado das cores, evidências e testes futuros.

A coordenação também conferiu os contratos e leu trechos do checkout local do Hub, somente leitura. Nenhum agente escreveu código ou executou testes, serviços, coleta remota ou comandos mutantes no Hub.

## Achados para o desenho

- O BFF dispõe de observações separadas para production/hml e guarda última observação válida e última tentativa. Aguarda 60 s depois de um ciclo sequencial, e considera vencida a observação quando age_seconds > 180.
- O normalizador admite status PM2, endpoints HTTP interno/público e leitura SQLite/contadores de jobs. Esses campos podem estar ausentes; presença de report.ok não comprova a saúde de cada aspecto.
- Worker desligado em homologação é política esperada. Não representar a flag como monitoramento de um serviço worker independente.
- PM2, API, endpoints e SQLite são aspectos/partes do mesmo Hub. O mapa precisa de relações internas verificadas, não inferidas de checkout/hospeda/utiliza do catálogo geral.
- health.js usa SELECT 1 no banco: a leitura do banco é dependência comprovada do health/API no checkout local consultado.
- report.ok falso pode representar revisão, política ou pendência operacional, com HTTP e banco funcionando. A lista normalizada de causas é incompleta; mostrar avaliação com atenção quando não há causa suficiente, sem inventar falha específica.
- Falha de coleta, sessão expirada e ausência de observação não comprovam queda. Preservar observação anterior com horário, sem apresentar como saúde atual. Falha de um ambiente não deve apagar o outro.
- Sem observação ou sinal suficiente: cinza/sem evidência. Verde: verificação recente normal. Amarelo: observação vencida ou alerta identificado. Vermelho: verificação diretamente falhou em evidência recente, com motivo e data; evitar chamar toda falha de queda.
- Não existe latência HTTP do Hub no contrato. duration_ms do trace mede toda a chamada MCP, incluindo transporte/coleta, e não é latência do Hub.

## Proposta a apresentar, ainda não aprovada

Classificação permanece architectural; manter o processo completo pedido pelo Hugo.

Abordagens:

1. Mapa Hub dentro de Observabilidade (recomendada): duas faixas, produção e homologação, topologia explícita dos aspectos internos; mantém o grafo documental separado.
2. Perspectiva Operação Hub no Grafo: reaproveita mais controles, mas mistura mais facilmente estado observado e documentação.
3. Página Mapa Hub separada: navegação própria, com manutenção adicional.

Desenho inicial recomendado: topologia estática visível sem BFF; dados dinâmicos apenas dos contratos existentes; selecionar aspecto mostra motivo/data/ambiente, depende de e quem depende; lista e teclado equivalentes ao mapa; últimas observações preservadas em memória na perda da conexão, marcadas como históricas. Latência fica explicitamente fora deste primeiro ciclo por falta de medida confiável, sujeita à aprovação de Hugo. Sem novos coletores, Neo4j, acionamento de testes pela tela ou escrita externa.

## Verificação futura: dependência descoberta

Ainda NÃO foram rodados testes. O resultado 143 Python/30 Node continua atribuído ao handoff anterior.

O teste tests/test_components.py:31 chama QdrantStore.ensure_collection. core/qdrant_store.py:20 pode criar uma coleção real. Portanto clone sem .env não comprova independência dos serviços nem impede esse efeito. Antes de rodar os gates, prever isolamento explícito dessa dependência ou reportar a limitação, sem iniciar Qdrant nem alterar índice/runtime em uso. Tests de HTTP usam servidor efêmero e armazenamento temporário; isso deve ser distinguido do BFF operacional proibido de iniciar.

Testes significativos previstos: limites 180/>180 s; nenhuma observação; campos/idade inválidos; observação anterior seguida de erro/recusa; falha antiga não mostrada como atual; aspecto falho com outros normais; report.ok falso por revisão/política; report.ok verdadeiro com avisos; homologação independente de produção; clique/teclado/lista; navegação descartando retorno assíncrono antigo.

## Estado do Git e alterações da sessão

HEAD permanece 0b25f50. Branch local codex/docs/handoff-second-brain-2026-10-09. Única alteração deste ciclo: esta nota de handoff, nova, CRLF, sem commit. Preservados os dois handoffs existentes. Nenhum código, vault, ADR, spec ou plano foi alterado; nenhum push, merge, remoto ou PR foi feito.

## Próxima etapa

Apresentar o desenho inicial com alternativas e pedir UMA confirmação de desenho ao Hugo. Sua aprovação permite escrever a spec; depois Hugo revisa a spec, writing-plans produz plano, Hugo revisa e escolhe o método de execução. Executing-plans com TDD, revisão independente final, correções Critical/Important com teste, verificação com saída e clone limpo sem variáveis de ambiente do projeto, finishing-a-development-branch e PR seguem sujeitos às autorizações originais. Atualizar handoff no fim da sessão.
