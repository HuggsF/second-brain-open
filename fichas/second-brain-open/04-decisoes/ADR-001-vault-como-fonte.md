---
id: ADR-001
status: aceito
data: 2026-11-23
---
# O vault em Markdown é a fonte; o índice é derivado

## Contexto

O conhecimento de engenharia precisa ser lido por pessoas e por agentes, versionado e revisado como
código. Código que sustenta: `config.py` (caminhos do vault), `cli.py` (comando `sync`, que reconstrói
o índice a partir dos arquivos) e `core/chunker.py`.

## Opções consideradas

1. **Arquivos Markdown como fonte, índice derivado.** Legível sem ferramenta, versionado no git,
   reconstruível.
2. **Banco de dados como fonte.** Consulta mais rica, mas o conteúdo deixa de ser revisável em um diff.
3. **Ferramenta de documentação hospedada.** Boa edição, mas o conhecimento sai da máquina e do git.

## Decisão

Opção 1. O vault é o registro; o índice vetorial pode ser apagado e refeito a qualquer momento.

## Consequências

- Uma nota apagada some do índice no próximo `sync`.
- Consultas estruturadas entre notas dependem de campos no começo de cada arquivo.
- O repositório não traz vault: quem instala aponta `config.py` para o seu.
