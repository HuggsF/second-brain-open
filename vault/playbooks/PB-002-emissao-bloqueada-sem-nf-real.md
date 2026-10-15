---
id: PB-002
title: Emissão bloqueada sem NF real
status: active
validates: [RULE-001]
environment: hml
kind: test
targets: [Hub Logístico, Bling (consulta de NF), J&T (adapter)]
---

# PB-002: Emissão bloqueada sem NF real

## Cenário

- **Dado** um pedido cuja NF não tem número positivo, série, chave de 44 dígitos não zerada ou data válida, ou cuja consulta ao Bling falha.
- **Quando** o motor tenta emitir a etiqueta.
- **Então** a emissão é bloqueada antes de criar a intenção J&T, nenhum rastreio novo é gerado e um rastreio já existente continua reutilizável.

## Resultado esperado

Nenhuma chamada de criação à J&T para esse pedido; o job fica visível para revisão operacional. Uma resposta 429 do Bling volta à fila com cooldown, sem emitir.

## Registro

Ainda sem execuções registradas. Quem executar o cenário em homologação registra o resultado com `record_test_execution`, sem incluir dados do pedido.
