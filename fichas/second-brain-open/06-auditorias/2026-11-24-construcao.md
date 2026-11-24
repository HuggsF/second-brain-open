---
etapa: construcao
data: 2026-11-24
veredito: verde
criterio: "A suíte passa, e o comando budget mostra gasto e limite do perfil de exemplo sem serviço nenhum."
evidencia: fichas/second-brain-open/06-auditorias/evidencias/2026-11-24-pytest.txt
---
# Auditoria de construção, 2026-11-24

## Critério

A suíte passa, e o comando `budget` mostra gasto e limite do perfil de exemplo sem serviço nenhum.

## O que foi feito

Depois de o `ask` passar a gerar pela cadeia de provedores, com custo e orçamento
([ADR-006](../04-decisoes/ADR-006-resposta-pela-cadeia.md)):

1. `python -m pytest -q`, com Python 3.14.3 e as dependências de `requirements.txt`. Saída em
   [evidencias/2026-11-24-pytest.txt](evidencias/2026-11-24-pytest.txt).
2. Com o perfil de exemplo e o banco de orçamento em uma pasta temporária: `cli.py budget`,
   `cli.py budget --history 3`, `cli.py budget --rebuild` e `cli.py budget` de novo. Saída em
   [evidencias/2026-11-24-budget.txt](evidencias/2026-11-24-budget.txt).

Nos dois arquivos, o caminho local da máquina foi trocado por `.`, `~` ou `<pasta temporária>`; nada mais
foi alterado.

## Resultado

Verde: 1426 testes passam e nenhum falha. O `budget` mostrou estado normal, gasto zero e os limites do
perfil de exemplo, antes e depois da reconstrução.

Em relação à auditoria anterior:

- Os testes do gerador local direto saíram com ele; no lugar entraram os da resposta pela cadeia.
- Quatro testes da instalação privada de origem não vieram: três só conferiam um perfil que não existe neste repositório, e um
  comparava os esquemas de extração com modelos de nota de um vault que este repositório não traz.

## O que esta auditoria não cobre

- Geração com modelo real: nem servidor local nem provedor de nuvem foram chamados. `ask` e tarefas só
  são exercitados com clientes falsos, sem rede.
- Gasto real: com o perfil de exemplo não há provedor pago, então o orçamento nunca saiu de zero fora
  dos testes.
- O prazo de 120 segundos do perfil de exemplo: é uma estimativa, não foi medido.
- As garantias de privacidade do provedor de nuvem: o motor repassa a declaração do perfil e não confere
  se o provedor a cumpre.
- Outro sistema operacional: tudo foi rodado em uma máquina Windows.
