---
type: adr
scope: second-brain
status: Aceito
date: 2026-10-13
related: [ADR-005, ADR-013]
---
# ADR-014: Frontmatter YAML como padrão de metadados das notas do vault

> Esta ADR trata do próprio repositório `second-brain`.

## Contexto
Até 2026-10-12 o vault tinha três formas de registrar status e data de uma nota:
- seções `## Status` e `## Data` (ADR-001 a ADR-012, com seis redações diferentes de status);
- um blockquote sob o título com `> **Status:** \`#status/active\`` e emoji no H1 (notas de architecture, product e references criadas em 2026-10-12);
- frontmatter YAML (só `rules/` e `playbooks/`, lido por `core/evidence.py`).

Nenhum código lia as duas primeiras: o chunker indexava os metadados como texto da seção "Introdução" e o leitor do dashboard mostrava o frontmatter como uma linha horizontal seguida de texto solto.

## Alternativas Consideradas
- **Só seções Markdown (`## Status`, `## Data`):** muda menos arquivos, mas continua sem parser e mistura metadados com o conteúdo indexado.
- **Blockquote com tags `#status/...`:** legível no Obsidian, mas não é parseável sem regex específica e não serve a `core/evidence.py`.

## Decisão
1. Toda nota do vault começa com frontmatter YAML. Campos comuns: `type` (`adr`, `system`, `architecture`, `product`, `reference`, `team`, `domain`, `daily`, `radar`), `status` e `date` (`AAAA-MM-DD`).
2. ADRs usam o vocabulário do template: `Proposto`, `Aceito`, `Depreciado`, `Substituído por ADR-NNN`. Uma ADR sobre este repositório declara `scope: second-brain`.
3. Campos opcionais com nome fixo: `author`, `source`, `audience`, `related`, `supersedes`, `version`, `updated`, `target_release`, `tags`; references acrescentam `drive_file_id`, `source_sha256` e `original_file`. Descrições livres (objetivo, aplicação, agentes beneficiados) ficam no corpo, em blockquote.
4. Títulos sem emoji. ADRs na ordem Contexto → Alternativas Consideradas → Decisão → Consequências.
5. `core/chunker.py` retira o frontmatter do texto indexado e grava `status` e `doc_type` nos metadados do chunk; `dashboard/markdown.js` mostra o frontmatter como bloco de metadados.
6. Os templates de `vault/_templates/` seguem o mesmo formato.

## Consequências
- 105 notas reescritas em 2026-10-13 (`docs/padronizacao`); o conteúdo das seções não mudou, só cabeçalhos e ordem.
- Os status "Executado com sucesso", "Aprovado e implementado" e "Aprovado e vigente" passaram a `Aceito`; o detalhe ficou no histórico do git.
- Notas sem status declarado receberam `active`; a data de notas sem data é a do primeiro commit do arquivo.
- Uma nota nova sem frontmatter continua sendo indexada, mas sem `status` e `doc_type`.
