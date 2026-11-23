---
etapa: construcao
data: 2026-11-23
veredito: verde
criterio: "A suíte passa, e sync seguido de buscar devolve a nota certa sem serviço nenhum."
evidencia: fichas/second-brain-open/06-auditorias/evidencias/2026-11-23c-pytest.txt
---
# Auditoria de construção, 2026-11-23, terceira do dia

## Critério

A suíte passa, e `sync` seguido de `buscar` devolve a nota certa sem serviço nenhum.

## O que foi feito

Depois da troca do banco vetorial pela busca de texto completo ([ADR-005](../04-decisoes/ADR-005-busca-textual.md)):

1. `python -m pytest -q`, com Python 3.14.3 e as dependências de `requirements.txt`. Saída em
   [evidencias/2026-11-23c-pytest.txt](evidencias/2026-11-23c-pytest.txt).
2. Em uma pasta temporária fora do repositório, com três notas fictícias e o Docker parado: `cli.py sync`,
   duas perguntas com `cli.py buscar` e `cli.py status`. Saída em
   [evidencias/2026-11-23c-sync-buscar.txt](evidencias/2026-11-23c-sync-buscar.txt).

Nos dois arquivos, o caminho local da máquina foi trocado por `.`, `~` ou `<pasta temporária>`; nada mais
foi alterado.

## Resultado

Verde: 1262 testes passam e nenhum falha. O `sync` indexou as três notas, e cada pergunta devolveu a nota
esperada.

Em relação à auditoria anterior, três testes mudaram: os dois que montavam o recuperador com um banco
vetorial falso foram reescritos sobre o índice de texto, e o que verificava a assinatura do módulo
removido saiu.

## O que esta auditoria não cobre

- `ask` com um modelo real: a geração da resposta só é exercitada com um gerador falso.
- Qualidade da busca: não há vault de exemplo nem perguntas de referência neste repositório, então acerto
  e piso de relevância não foram medidos.
- Outro sistema operacional: tudo foi rodado em uma máquina Windows.
