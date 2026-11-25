---
id: ADR-007
status: aceito
data: 2026-11-25
---
# Demanda com trilha e portões, e rascunhos gravados dentro da ficha

## Contexto

O motor tinha fichas de projeto, busca e uma cadeia de provedores, mas não tinha o conceito de demanda:
um pedido de mudança que nasce, é triado, passa por fases e deixa documentos pelo caminho. Sem isso, a
ficha descrevia o projeto parado e nada ligava um pedido aos artefatos que ele produz. Código que sustenta
a decisão: `core/demand_lifecycle.py`, `core/triagem.py`, `core/docs_registry.py`, `core/geracao/`,
`core/produtos.py` e o grupo `demanda` do `cli.py`.

O ciclo de vida, a triagem e a geração já existiam e estavam testados em uma instalação privada do mesmo
autor; entram aqui sem o vocabulário dela. Lá, os rascunhos vão para um repositório de documentação à parte.

## Opções consideradas

1. **Rascunhos dentro da ficha do projeto.** A pasta de documentos passa a ser, por padrão, `fichas/`, e
   o produto de uma demanda é o slug de uma ficha. Os rascunhos caem em
   `fichas/<projeto>/demandas/<id>/` e as regras em `fichas/<projeto>/regras/`.
2. **Pasta de documentos separada, como na origem.** Cópia mais fiel, mas ficha e demanda ficariam sem
   ligação.
3. **Redistribuir cada artefato nas seções numeradas da ficha.** Exigiria reescrever o plano de geração e
   os portões, e misturaria rascunho de demanda com o documento vigente do projeto.

## Decisão

Opção 1. Uma demanda nasce em `intake` e segue por `spike`, `spec`, `dev`, `review` e `done`. A triagem
responde quatro perguntas e escolhe uma de quatro trilhas (`operacional`, `correcao_direta`, `leve`,
`completa`); a trilha define o que cada fase precisa produzir, e o portão de cada transição recusa o
avanço dizendo o que falta. `gerar-artefatos` redige os rascunhos da fase pela cadeia de provedores, com o
custo e o orçamento do [ADR-006](ADR-006-resposta-pela-cadeia.md). A variável `DOCS_REPO_PATH` ainda
aponta outra pasta de documentos, para quem preferir a opção 2.

## Consequências

- As páginas geradas são Markdown com extensão `.mdx` e nascem com `status: proposta`. O portão só aceita
  a página depois que uma pessoa a revisa e troca o status. A visão precisa também do registro de quem a
  aprovou.
- Sem `--refazer`, `gerar-artefatos` nunca altera uma página existente. Com `--refazer`, apaga e regera as
  páginas ainda em `proposta`, inclusive as editadas à mão. Página fora de `proposta` nunca é tocada.
- O validador de fichas ignora as pastas `demandas/` e `regras/`: elas não são seção da ficha.
- O rascunho da triagem nasce sem trilha, só com uma sugestão. Quem aprova informa a trilha; trocar a
  trilha depois exige motivo e autor registrados.
- Quem aprova é sempre um papel, não uma pessoa. O motor não confere isso: ele grava o texto que recebe.
- A trilha completa não chega a `done` sozinha: o portão de entrega exige um arquivo de rastreio entre
  exemplos de regra e testes, e o verificador que o produz não faz parte deste repositório. Pelo mesmo
  motivo, na fase `review` da trilha completa o `gerar-artefatos` sempre sai com 1.
- Não há API nem quadro: o acesso é só pela linha de comando. Bloquear, desbloquear, cancelar e devolver
  para retrabalho existem no serviço e ainda não têm comando.
- A geração dos rascunhos não tem teste com modelo real: os testes usam um cliente falso.
- O catálogo de atividades e as faixas de esforço do guia de triagem de exemplo são fictícios.
