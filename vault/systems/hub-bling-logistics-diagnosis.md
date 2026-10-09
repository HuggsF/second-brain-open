# Investigação: UPDATE do Bling sem objeto logístico

Evidências coletadas em 08/10/2026, às 17:54–17:58 de Brasília. Apenas leitura de código, logs e SQLite de produção; nenhuma renovação OAuth, requisição de emissão, atualização no Bling, cancelamento ou reprocessamento foi executado na investigação.

## Causa confirmada

O adapter interrompe `updateTracking` quando não encontra `pedido.transporte.volumes[0].id`. A mensagem é gerada localmente antes do PUT no Bling, portanto estes registros não representam rejeição de um PUT pela API nem falha de rate limiting.

Nos 30 jobs com essa mensagem, o último payload universal persistido contém `package.qty = 0`. O mapeamento usa o comprimento de `transporte.volumes` quando o campo existe. Isso evidencia o cenário de volumes vazios na consulta inicial usada para processar esses jobs. A mensagem do UPDATE, isoladamente, também poderia significar primeiro volume sem ID; o payload complementa essa evidência.

Hashes SHA-256 do código de produção coincidiram com os arquivos locais:

- Adapter Bling: `67ec749417734c6fee627450a180637d7ce530d7bf28b587c3550350b73dc4ae`.
- Engine: `54222e6bd78cc55bbb69822a253e05dab8e83acce58b516467ddbbcea936447c`.

## Sequência que provoca a falha

1. `getOrder` consulta o pedido e produz o payload universal, incluindo quantidade de volumes zero.
2. O engine recupera um rastreio existente ou solicita uma nova etiqueta na J&T. A emissão pode ser confirmada e o rastreio salvo.
3. Só depois chama `updateTracking`, que consulta novamente o pedido e exige o ID do primeiro objeto de logística.
4. Sem esse ID, lança `Bling UPDATE falhou: ... não tem objeto de logística ...` antes de chamar PUT.
5. O catch trata a falta estrutural como erro comum: espera 30/60/90 segundos e repete; depois marca `failed`.
6. O envio ao WMS e a finalização como `success` não são alcançados nessa execução.

Reprocessar sem corrigir a condição no Bling não resolve a falha. As retentativas reaproveitam rastreios; isso não cria o objeto ausente nem comprova consistência fiscal ou estado atual na transportadora.

## Alcance observado

Às 17:54:28, janela móvel de 30 minutos:

| Indicador | Evidência |
|---|---:|
| Logs de falta de objeto logístico | 50 |
| Logs de rate limit | 1 |
| Outros logs de erro | 2 |
| Jobs contendo a falta de objeto | 30 |
| Pedidos ERP distintos nesses jobs | 20 |
| Jobs failed / pending | 28 / 2 |
| Jobs com rastreio registrado | 30 |

Conferência posterior: nove pedidos distintos desse conjunto têm emissão confirmada no ledger `jt_emissions`, criada em 08/10 entre 16:48:15 e 17:47:25 de Brasília. Os rastreios das linhas com ledger coincidem com o rastreio durável. Isso comprova o estado persistido pelo Hub; não houve nova consulta independente à J&T nesta investigação.

Um pedido possui dois rastreios diferentes entre dois jobs failed. Ambos os jobs são de 03/10/2026, anteriores ao deploy atual, e não têm registro durável associado. Deve ser conciliado separadamente; não é evidência de nova duplicidade causada pelo deploy atual. Os identificadores ficam no relatório privado `.deploy-state/bling-update.private.json`, fora do Git e do snapshot público de conhecimento.

Contagens de logs, jobs e pedidos não são equivalentes. O webhook exclui somente pending/processing/success ao verificar presença na fila: um pedido failed pode voltar a gerar uma linha em nova entrega de webhook. Isso é uma possibilidade permitida pelo código, não uma causa comprovada para cada linha duplicada observada.

## Correção proposta e critérios de aceite

- Validar quantidade de volumes e o ID de objeto logístico antes de qualquer nova emissão na J&T. Quando ausente, apresentar pendência de logística e bloquear emissão antecipadamente.
- Classificar essa falta como pendência de configuração/revisão, com código estável, sem gastar tentativas automáticas como se fosse indisponibilidade transitória.
- Para pedidos já etiquetados, preservar ledger e rastreio. Regularizar o objeto correto no Bling e atualizar o rastreio existente somente após confirmar vínculo pedido/volume/etiqueta.
- Não presumir criação automática de volume, divisão em múltiplos volumes ou cancelamento/reemissão. Essas regras continuam pendentes do contrato de integração e da decisão operacional.
- Evitar reentrada automática de uma pendência estrutural por webhook; manter um único estado de revisão por pedido até resolução explícita.
- Exibir na observabilidade "objeto logístico ausente" em vez de apenas quantidade genérica de regras acionadas. Separar falta estrutural, rate limit e falha de transporte; o contador atual de "demais erros" não prova que todos sejam terminais.

Testes exigidos para uma correção futura: zero volumes; primeiro volume sem ID; um volume válido; múltiplos volumes sem seleção definida; etiqueta já confirmada; divergência de rastreios; webhook repetido após pendência; preservação de rastreio após regularização. Critério central: nenhuma nova chamada de emissão quando faltar o objeto necessário para concluir a integração.

A documentação oficial do Bling descreve o objeto logístico como representação do volume e admite um ou mais volumes por venda: [serviço logístico no pedido ou nota](https://ajuda.bling.com.br/hc/pt-br/articles/360038663234-Como-selecionar-o-servi%C3%A7o-log%C3%ADstico-no-pedido-de-venda-ou-na-nota-fiscal). Isso não valida por si só um POST automático para regularizar os pedidos; o contrato específico ainda precisa ser verificado.

Rollback de código não cria objetos ausentes no ERP e não desfaz etiquetas existentes. Nenhuma correção de produção foi aplicada nesta investigação.
