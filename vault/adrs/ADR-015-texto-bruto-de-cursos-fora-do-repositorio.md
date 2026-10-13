---
type: adr
scope: second-brain
status: Aceito
date: 2026-10-13
related: [ADR-010]
---
# ADR-015: Texto bruto de cursos e livros fora do repositório

> Esta ADR trata do próprio repositório `second-brain`.

## Contexto
O commit `0e42568` (2026-10-13) versionou em `extracted_drive/` (28 arquivos, incluindo o Guia PMBOK 7ª edição) e `extracted_pm3/` (5 arquivos) o texto integral extraído de cursos e livros pagos. O texto serviu para gerar as notas de `vault/product/references/` e a inteligência de workflows; depois disso nada o lê em runtime. O pipeline de [[ADR-010-drivesyncengine-pipeline-ingestao-conhecimento-google-drive]] gravava o caminho do texto bruto em cada nota de referência.

## Alternativas Consideradas
- **Manter o texto no `main`:** deixa material protegido por direitos autorais num repositório com remoto no GitHub e aumenta o clone em ~50 mil linhas sem uso.
- **Reescrever o histórico para apagar o commit:** exige force push no `main` remoto; adiado e deixado para decisão humana.

## Decisão
1. `extracted_drive/` e `extracted_pm3/` saem do `main` e entram no `.gitignore`; o conteúdo fica na branch `archive/material-cursos-bruto` até o descarte.
2. As notas de `product/references/` guardam só metadados, um excerto curto e o SHA-256 da origem; a linha "Caminho Local do Texto Bruto" foi removida.
3. O `DriveSyncEngine` continua extraindo texto localmente, mas a nota gerada não aponta para ele, sai com frontmatter (ADR-014) e reaproveita a nota existente quando o SHA-256 já foi visto.
4. `extracted_full_cycle/` e `extracted_system_design/` continuam versionados: são manifestos e chunks lidos pelo dashboard e por `ingestion/generate_intelligence_chunks.py`.

## Consequências
- O texto bruto continua no histórico do git pelo commit `0e42568` até alguém decidir reescrever o histórico.
- Duas references duplicadas (mesmo SHA-256 das aulas 08 e 09) foram removidas e as 26 restantes renomeadas para kebab-case ASCII.
