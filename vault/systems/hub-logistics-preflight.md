---
type: system
status: active
date: 2026-10-09
---
# Correção: validar logística antes da emissão

Implementação local de 08/10/2026, decorrente da investigação de UPDATE sem objeto logístico. Não regulariza objetos ou etiquetas existentes automaticamente.

## Comportamento

O adapter fornece `logistics.volumeCount` e `logistics.objectId` no pedido universal. O motor aceita automaticamente somente um volume com ID válido. Zero volumes ou ID ausente resultam em `REVIEW_REQUIRED: LOGISTICS_OBJECT_MISSING`; mais de um volume resulta em `REVIEW_REQUIRED: MULTIPLE_VOLUMES_UNDEFINED`. O bloqueio ocorre antes de emissão J&T e antes da atualização ERP.

Essas pendências permanecem como `failed` com código de revisão, compatível com a tela operacional existente. Não gastam retries automáticos nem geram novas intenções no ledger. Um webhook repetido reconhece tanto o código novo quanto a mensagem estrutural antiga e não cria outro job. Reenvio manual continua disponível; a validação será executada novamente, portanto reenvio sem regularização permanece bloqueado.

Uma etiqueta já registrada é preservada. Após regularizar um único objeto logístico, o operador pode reenviar o mesmo job; o motor reaproveita o rastreio, faz a atualização e confere a gravação no Bling. Divergências de rastreio e emissões incertas continuam exigindo revisão. O adapter revalida o objeto no segundo GET para detectar alterações entre preflight e UPDATE; se o objeto desaparecer depois de uma emissão, preserva o ledger e bloqueia novas emissões.

Não é presumido um contrato para criação automática de objetos, seleção de um dentre vários volumes, cancelamento ou reemissão de etiquetas.

## Observabilidade

O coletor acrescenta contagens de jobs failed sem objeto e com múltiplos volumes. Essas pendências mantêm o alerta mesmo depois que os erros saem da janela de cinco minutos. O BFF local aceita esses campos e apresenta razões de alerta por uma lista fixa, sem expor mensagens de pedidos ou payloads. Os novos contadores só ficam disponíveis quando o coletor atualizado for implantado no ambiente.

## Validação e ativação

Testes com SQLite em memória e adapters sem rede cobrem: zero volumes, ID ausente/inválido, múltiplos volumes, caminho válido, preservação e recuperação de etiqueta existente, divergência de rastreios, revalidação no UPDATE e reentrega de webhook com erro novo/legado. A suíte fiscal e os testes de idempotência permanecem aplicáveis.

Ativação deve usar o fluxo de release e rollback existente: homologação com worker desligado, revisão de SHA e health, depois produção. Atualizar a revisão esperada da observabilidade somente para a release efetivamente implantada. Nenhum job antigo deve ser reprocessado em lote ou ter seu ledger removido no deploy. Rollback restaura código, preserva banco e mantém worker pausado para revisão.
