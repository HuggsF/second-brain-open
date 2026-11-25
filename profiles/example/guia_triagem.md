Este guia orienta o rascunho da triagem de uma demanda. O rascunho é só uma sugestão: quem escolhe e aprova a trilha é o papel de gestor de demandas.

## As quatro perguntas

Responda `true` para SIM e `false` para NÃO.

- T1: a demanda muda quem é afetado, quanto ou quando, em uma decisão que pertence a uma área de negócio? Exemplos: um valor, um prazo, um limite, quem recebe algo, um critério de inclusão ou de exclusão. SIM exige regras escritas, com dono e aval da área.
- T2: a demanda cria ou altera uma tela?
- T3: a demanda integra um sistema externo, ou roda sem uma pessoa acionando? Exemplos: rotina agendada, processamento em lote, envio automático de mensagem, sincronização entre sistemas.
- T4: a demanda cabe em uma faixa pequena do catálogo de atividades (até 8 horas) e T1, T2 e T3 são NÃO?

Na dúvida entre SIM e NÃO em T1, T2 ou T3, responda SIM. A trilha mais pesada é o padrão, e rebaixar a trilha exige motivo escrito de quem aprova.

## Trilha

O campo `trilha` recebe um destes valores:

- `operacional`: pedido de operação, sem mudança no produto. Exemplos: publicar uma versão, conferir um dado, liberar um acesso.
- `correcao_direta`: defeito com causa conhecida e T1 = NÃO. Pedido de algo novo, como uma adição, uma automação ou uma tela, não é correção.
- `leve`: T4 = SIM. Exige `criterios_de_aceite`.
- `completa`: qualquer outro caso. Toda demanda com T1, T2 ou T3 = SIM que não seja correção de defeito cai aqui.

## Atividade e faixa

`atividade` é um item do catálogo de atividades e `faixa` é a letra da faixa de esforço. O catálogo abaixo é fictício, só para o exemplo funcionar; troque pelo catálogo da sua organização.

Atividades:

- Evolução de sistema
- Correção de defeito
- Integração entre sistemas
- Operação e suporte

Faixas de esforço:

- A: até 4 horas
- B: até 8 horas
- C: até 40 horas
- D: acima de 40 horas

Se o texto do pedido não permitir escolher, deixe `atividade` e `faixa` vazios. Nunca use nesses campos o nome de uma tarefa ou de um modelo de documento.

## Outros campos

- `criterios_de_aceite`: frases verificáveis do que quem pediu vai conferir na entrega, tiradas do próprio pedido.
- `mais_de_uma_sprint`: `true` quando o pedido junta entregas ou integrações que não cabem em duas semanas.
- Justificativa: diga em uma ou duas frases por que escolheu o produto, a trilha e cada SIM. Se o pedido veio só com o título, diga isso.
