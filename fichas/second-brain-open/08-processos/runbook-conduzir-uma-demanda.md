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
3. Gerar o rascunho da triagem: `cli.py gerar-artefatos <id>`. Isso chama um modelo. Sem modelo, gravar a
   triagem à mão com `cli.py demanda triar <id> --arquivo triagem.json`; o arquivo é um objeto JSON com
   `produto`, `t1` a `t4` (verdadeiro ou falso), `atividade`, `faixa`, `criterios_de_aceite` (lista) e
   `mais_de_uma_sprint`.
4. Ler o rascunho com `cli.py demanda mostrar <id>` e aprovar escolhendo a trilha:
   `cli.py demanda triar <id> --aprovar-por gestor-demandas --trilha completa`. O guia das quatro
   perguntas e das trilhas está em `profiles/<perfil>/guia_triagem.md`.
5. Avançar: `cli.py demanda avancar <id> --ator gestor-demandas`. Se o portão recusar, o comando lista o
   que falta.
6. Em cada fase, gerar os rascunhos com `cli.py gerar-artefatos <id>`. Eles ficam em
   `fichas/<projeto>/demandas/<id>/`, com `status: proposta`.
7. Revisar cada página, corrigir o texto e trocar o `status` para `validada`. Para a visão, registrar
   também quem aprovou: `cli.py demanda aprovar-visao <id> --por gestor-demandas`.
8. Página de regra (em `fichas/<projeto>/regras/`) pede mais do que as outras. O portão só a aceita com
   tudo isto no cabeçalho e no corpo:
   - `status: aprovada`, e `id`, `title`, `dono` e `versao` preenchidos;
   - `areas_aval` com as áreas que precisam dar aval, e em `avais` um registro por área, com `area`,
     `pessoa` (o papel de quem deu o aval), `data`, `email` e a mesma `versao` da página;
   - pelo menos dois exemplos na tabela da seção "Exemplos";
   - nenhuma pergunta na seção "Perguntas em aberto". A página gerada sempre nasce com perguntas ali:
     responder e apagar faz parte da revisão.
9. Gravar os artefatos que não são gerados (evidência, teste de reprodução, aceite da área). O valor vai
   em um arquivo JSON, para não depender das aspas do terminal: salvar, por exemplo, `"link ou texto"`
   em `evidencia.json` e rodar `cli.py demanda artefato <id> evidence --arquivo evidencia.json`.
10. Repetir os passos 5 a 9 até a fase `done`.

Trocar a trilha depois de aprovada: `cli.py demanda trilha <id> <nova> --motivo "..." --ator gestor-demandas`.

Regerar um rascunho ruim: `cli.py gerar-artefatos <id> --refazer`. Isso apaga as páginas ainda em
`proposta`, inclusive as editadas à mão; as validadas não são tocadas.

## Como saber que deu certo

- `cli.py demanda mostrar <id>` diz "Nada falta para sair de" na fase atual, e `avancar` muda a fase.
- A pasta `demandas/` não muda o resultado de `cli.py ficha validar`: uma ficha que era válida continua
  válida. Ficha recém-criada sai com 1 até ter as seções preenchidas, com ou sem demanda.

## Limites

- Na trilha completa, a entrega exige um arquivo de rastreio que este repositório não produz. Quem tiver
  um verificador próprio grava o caminho do arquivo com `cli.py demanda artefato <id> rastreio`.
- Não há comando para bloquear, cancelar ou devolver uma demanda para retrabalho.
- Se duas demandas gerarem uma regra com o mesmo nome, a segunda não sobrescreve a primeira e fica sem
  regra vinculada. Vincular à mão: `cli.py demanda artefato <id> regras --arquivo regras.json`, com a
  lista dos caminhos das páginas de regra.
- `--refazer` na fase `intake` também troca o rascunho de triagem ainda não aprovado.
