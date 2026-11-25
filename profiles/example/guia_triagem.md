Use este guia para redigir a triagem de uma demanda. O que sai daqui é uma proposta: a trilha só vale depois que o papel de gestor de demandas a escolhe e aprova.

## Quatro perguntas de sim ou não

Cada resposta vai como `true` (sim) ou `false` (não).

- T1, regra de negócio. O pedido altera uma decisão que é de uma área de negócio, e não do time técnico? Pense em quem passa a ser atingido, em que medida e em que momento: um preço, um limite, uma data de corte, o destinatário de algo, quem entra ou sai de uma lista. Se sim, a mudança precisa de regra escrita, com responsável e aprovação da área.
- T2, tela. Alguma tela nasce ou muda por causa do pedido?
- T3, integração ou automação. O pedido conversa com um sistema de fora, ou executa por conta própria, sem alguém clicar? Entram aqui tarefa agendada, carga em lote, mensagem disparada automaticamente e cópia de dados entre sistemas.
- T4, mudança pequena. As três perguntas anteriores deram não e o esforço fica nas faixas menores do catálogo de atividades, com teto de 8 horas?

Ficou em dúvida em T1, T2 ou T3? Marque sim. O caminho mais completo é o ponto de partida; para sair dele, quem aprova tem de registrar o motivo.

## Qual trilha propor

O campo `trilha` aceita quatro valores:

- `operacional`: é serviço de operação e o produto não muda. Por exemplo, colocar uma versão no ar, checar uma informação ou conceder um acesso.
- `correcao_direta`: é um defeito, a causa já se conhece e T1 é não. Funcionalidade nova, automação nova ou tela nova nunca entram aqui, mesmo que pequenas.
- `leve`: T4 é sim. Só vale com `criterios_de_aceite` preenchido.
- `completa`: todo o resto, o que inclui qualquer pedido com sim em T1, T2 ou T3 que não seja conserto de defeito.

## Atividade e faixa

`atividade` nomeia o tipo de trabalho e `faixa` é a letra que indica o tamanho do esforço. Os dois vêm de um catálogo de atividades. O catálogo a seguir é fictício e existe só para o exemplo rodar: substitua pelo da sua organização.

Tipos de atividade:

- Evolução de sistema
- Correção de defeito
- Integração entre sistemas
- Operação e suporte

Faixas:

- A: até 4 horas
- B: até 8 horas
- C: até 40 horas
- D: acima de 40 horas

Quando o pedido não dá base para escolher, os dois campos ficam em branco. Eles não servem para guardar título de tarefa nem nome de documento.

## Demais campos

- `criterios_de_aceite`: o que a pessoa que pediu vai checar ao receber, escrito de um jeito que dê para conferir e extraído do texto do pedido.
- `mais_de_uma_sprint`: marque `true` se o pedido reúne várias entregas ou integrações e passa de duas semanas de trabalho.
- Justificativa: em poucas linhas, explique o produto escolhido, a trilha e o motivo de cada sim. Se só havia o título para ler, registre isso.
