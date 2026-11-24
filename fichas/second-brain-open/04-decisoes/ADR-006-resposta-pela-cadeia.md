---
id: ADR-006
status: aceito
data: 2026-11-24
---
# Resposta gerada pela cadeia de provedores, com custo e orçamento

## Contexto

O `ask` gerava a resposta chamando o servidor local de modelos direto, por um caminho só dele. As tarefas
(`cli.py task`) já passavam por uma cadeia de provedores declarada no perfil. Eram dois caminhos de
geração, e nenhum dos dois registrava quanto custava uma chamada nem tinha um teto de gasto. Sem isso, não
dá para ligar um provedor pago com segurança. Código que sustenta a decisão: `core/cost.py`,
`core/budget.py`, `core/local_tasks/answer.py`, `core/local_tasks/router.py` e `core/retriever.py`.

## Opções consideradas

1. **Um caminho só: o `ask` gera pela cadeia do perfil, e toda chamada registra custo e respeita um
   orçamento.** Os módulos já existiam e estavam testados em uma instalação privada do mesmo autor;
   entram aqui sem o vocabulário dela.
2. **Reescrever custo e orçamento do zero.** Duplicaria código já testado e criaria uma segunda versão
   para manter.
3. **Trazer custo e orçamento, mas deixar o `ask` no gerador local direto.** Manteria os dois caminhos
   e deixaria o `ask` fora do orçamento.

## Decisão

Opção 1. Cada chamada de modelo produz um registro de custo (modelo, provedor, tokens, tempo, valor
pago e valor equivalente em um modelo pago de referência). O perfil pode declarar um orçamento diário e
mensal; o gasto fica em `.runtime/budget.db`, que nunca é commitado. Com o orçamento esgotado, a cadeia
usa só provedores locais; se não houver nenhum, a tarefa devolve `budget_exceeded` e o `ask` mostra as
fontes sem gerar a resposta. O gerador local direto foi removido.

Esta decisão substitui a última consequência do [ADR-005](ADR-005-busca-textual.md), que descrevia o
gerador local isolado.

## Consequências

- Sem provedor de nuvem no perfil, nada muda para quem usa: a geração continua no servidor local e o
  gasto registrado é zero.
- O orçamento barra só a nuvem. Chamada local e tarefa que não usa modelo passam sempre.
- Com orçamento declarado, todo provedor de nuvem precisa declarar preço; sem isso o perfil não carrega.
- O prazo do perfil de exemplo subiu de 30 para 120 segundos, porque o `ask` passou a usar o prazo do
  perfil e 30 segundos é pouco para um modelo pequeno em CPU. O prazo vale também para as tarefas.
- Conteúdo de tarefa só deve ir a provedor de nuvem que declare retenção zero e recusa de coleta ou
  treino. O perfil de exemplo mostra onde declarar. O motor repassa essa declaração ao provedor e não
  confere se ele a cumpre.
- O gasto das tarefas também fica no log de eventos, de onde `budget --rebuild` o refaz. O gasto do
  `ask` fica só no banco de orçamento: se o banco se perder, esse gasto se perde e o período recomeça
  sem ele.
- A geração por provedor de nuvem e por modelo local real não tem teste automático: os testes usam
  clientes falsos e não fazem chamada de rede.
