---
etapa: construcao
data: 2026-11-25
veredito: verde
criterio: "A suíte passa, e uma demanda vai do pedido até a visão em rascunho, com o portão recusando o rascunho."
evidencia: fichas/second-brain-open/06-auditorias/evidencias/2026-11-25-pytest.txt
---
# Auditoria de construção, 2026-11-25

## Critério

A suíte passa, e uma demanda vai do pedido até a visão em rascunho dentro da ficha, com o portão recusando
o avanço enquanto a página está em rascunho.

## O que foi feito

Depois de o motor ganhar demanda, triagem, portões e geração de rascunhos
([ADR-007](../04-decisoes/ADR-007-demanda-na-ficha.md)):

1. `python -m pytest -q`, com Python 3.14.3 e as dependências de `requirements.txt`. Saída em
   [evidencias/2026-11-25-pytest.txt](evidencias/2026-11-25-pytest.txt).
2. Em uma pasta temporária, com uma ficha `portal` criada por `ficha nova`, um catálogo com esse produto e
   um cliente de IA falso que devolve respostas fixas: criar a demanda, gerar o rascunho da triagem,
   aprovar com a trilha completa, avançar para `spike`, gerar a visão e tentar avançar de novo. Saída em
   [evidencias/2026-11-25-demanda.txt](evidencias/2026-11-25-demanda.txt).

Nos dois arquivos, o caminho local da máquina foi trocado por `.`, `~`, `<python>` ou `<pasta temporária>`;
nada mais foi alterado.

## Resultado

Verde: 1744 testes passam e nenhum falha. Na sessão, a visão foi gravada em
`fichas/portal/demandas/dem-001/visao.mdx` com `status: proposta`, e o segundo avanço foi recusado dizendo
que a página ainda está em proposta e que falta registrar quem a aprovou.

Em relação à auditoria anterior, entraram os testes de triagem, ciclo de vida, portões, geração, catálogo de
produtos e linha de comando das demandas. Da instalação privada de origem não vieram os testes que
dependiam de uma API HTTP, de um validador externo de páginas de regra e do catálogo com repositório de
código por produto.

## O que esta auditoria não cobre

- Geração com modelo real: os rascunhos só foram produzidos por um cliente falso. A qualidade de um
  rascunho de verdade nunca foi medida aqui.
- A demanda até `done`: a sessão para em `spike`. O caminho inteiro é exercitado só em teste, com um
  verificador de rastreio falso; o verificador real não faz parte deste repositório.
- Uso pelas fichas reais do repositório: nenhuma demanda foi aberta para `second-brain-open` ou `rag-dojo`.
- Uso concorrente do banco de demandas.
- Outro sistema operacional: tudo foi rodado em uma máquina Windows.
