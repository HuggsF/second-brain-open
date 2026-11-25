---
tipo: runbook
dono: gestor-demandas
revisado_em: 2026-11-25
---
# Conduzir uma demanda, do pedido à entrega

## Quando usar

Sempre que chegar um pedido de mudança em um projeto que tem ficha. Os comandos abaixo são do `cli.py`;
`--ator`, `--por` e `--aprovar-por` recebem um papel, nunca o nome de uma pessoa.

## Passos

1. Conferir que o projeto está no catálogo (`profiles/<perfil>/produtos.yaml`) e tem ficha em
   `fichas/<projeto>/`. Sem ficha, criar com `cli.py ficha nova`.
2. Abrir a demanda: `cli.py demanda nova "Título" --descricao "Texto do pedido"`. O comando imprime o id.
3. Gerar o rascunho da triagem: `cli.py gerar-artefatos <id>`. Isso chama um modelo; sem modelo, gravar a
   triagem à mão com `cli.py demanda triar <id> --arquivo triagem.json`.
4. Ler o rascunho com `cli.py demanda mostrar <id>` e aprovar escolhendo a trilha:
   `cli.py demanda triar <id> --aprovar-por gestor-demandas --trilha completa`. O guia das quatro
   perguntas e das trilhas está em `profiles/<perfil>/guia_triagem.md`.
5. Avançar: `cli.py demanda avancar <id> --ator gestor-demandas`. Se o portão recusar, o comando lista o
   que falta.
6. Em cada fase, gerar os rascunhos com `cli.py gerar-artefatos <id>`. Eles ficam em
   `fichas/<projeto>/demandas/<id>/`, com `status: proposta`.
7. Revisar cada página, corrigir o texto e trocar o `status` para `validada`. Para a visão, registrar
   também quem aprovou: `cli.py demanda aprovar-visao <id> --por gestor-demandas`.
8. Gravar os artefatos que não são gerados (evidência, teste de reprodução, aceite da área):
   `cli.py demanda artefato <id> evidence --valor '"link ou texto"'`.
9. Repetir os passos 5 a 8 até a fase `done`.

Trocar a trilha depois de aprovada: `cli.py demanda trilha <id> <nova> --motivo "..." --ator gestor-demandas`.

Regerar um rascunho ruim: `cli.py gerar-artefatos <id> --refazer`. Isso apaga as páginas ainda em
`proposta`, inclusive as editadas à mão; as validadas não são tocadas.

## Como saber que deu certo

- `cli.py demanda mostrar <id>` diz "Nada falta para sair de" na fase atual, e `avancar` muda a fase.
- `cli.py ficha validar` continua saindo com 0 depois que a ficha ganha a pasta `demandas/`.

## Limites

- Na trilha completa, a entrega exige um arquivo de rastreio que este repositório não produz. Quem tiver
  um verificador próprio grava o caminho do arquivo com `cli.py demanda artefato <id> rastreio`.
- Não há comando para bloquear, cancelar ou devolver uma demanda para retrabalho.
