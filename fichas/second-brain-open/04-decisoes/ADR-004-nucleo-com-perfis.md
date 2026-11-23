---
id: ADR-004
status: aceito
data: 2026-11-23
---
# Núcleo que não nomeia a organização; vocabulário em perfis

## Contexto

O motor nasceu para um uso concreto, e nomes desse uso tendem a vazar para o código. Um núcleo que
cita a organização não serve a outra. Código que sustenta: `profiles/example/profile.yaml`,
`core/protocol/`, `core/local_tasks/` e o teste `tests/test_agnostic_core.py`.

## Opções consideradas

1. **Núcleo genérico mais um perfil por instância, com teste que barra nomes.** A fronteira é verificada.
2. **Um ramo do repositório por organização.** Sem custo inicial, mas as correções não voltam.
3. **Configuração por variável de ambiente espalhada.** Tira os nomes do código, mas não dá um lugar
   único para o vocabulário.

## Decisão

Opção 1. O vocabulário da instância vive em `profiles/<nome>/`; o teste lê os termos proibidos de uma
variável de ambiente, porque a lista em si não pode ir para um repositório público.

## Consequências

- Sem a variável definida, o teste não barra nada: a conferência depende de quem roda.
- Só os módulos listados no teste estão cobertos; os mais antigos ficam de fora até serem incluídos.
- O perfil de exemplo tem só `profile.yaml`; um perfil completo ainda não existe aqui.
