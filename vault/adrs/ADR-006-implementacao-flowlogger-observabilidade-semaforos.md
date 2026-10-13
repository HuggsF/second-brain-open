---
type: adr
status: Aceito
date: 2026-10-12
---
# ADR-006: Implementação do FlowLogger para Observabilidade e Semáforos Visuais

## Contexto
O sistema operava anteriormente em um cenário de "apagão" de observabilidade, onde o uso de logs genéricos dificultava a identificação do ponto exato de falha de uma mensagem (seja na fila, no banco ou no postback). Para garantir a rastreabilidade ponta a ponta (E2E) e viabilizar a "Documentação Inteligente", foi necessária a padronização rigorosa da emissão de logs no projeto `true-postback`.

### Problemas Enfrentados
- Dificuldade em correlacionar falhas entre fila de mensagens, banco de dados e endpoints de postback.
- Ausência de rastreabilidade única por requisição entre fornecedores e sistemas legados.
- Logs sem estruturação legível tanto para humanos em tempo de depuração quanto para coletores de telemetria automatizados.

## Decisão
Adotar a biblioteca **FlowLogger** como o motor unificado e estruturado de logs do projeto `true-postback`, combinando uma interface visual baseada em cores e árvores no terminal, juntamente com saídas em JSON estruturado para coleta por sistemas de telemetria.

### 1. Especificações Técnicas
- **Identificação de Rastreabilidade:** Toda requisição deve obrigatoriamente gerar e propagar um `batch_trace_id` (UUID v4) logo na sua entrada, que viajará por toda a infraestrutura e chamadas subsequentes.
- **Padrão Visual e Cores:** O sistema possui suporte (controlado pela variável de ambiente `FLOW_COLORS`) para coloração no terminal:
  - 🟢 **Verde:** Operações concluídas com sucesso e dados validados.
  - 🟡 **Amarelo:** Operações em andamento ou tempo de espera / I/O de rede.
  - 🔴 **Vermelho:** Erros e falhas de processamento.
  - ⚪ **Branco:** Dados estruturais neutros e configurações.
- **Árvore de Fluxo Visual:** O terminal desenha o ciclo de vida da mensagem usando caracteres de caixa (`┌──`, `├──`, `└──`, `→`, `←`), facilitando a leitura humana imediata.
- **Padrão de Timestamp:** Todos os eventos apresentam data e hora no formato UTC-3 (Brasília): `YYYY-MM-DD HH:MM:SS`.
- **Saída Estruturada (JSON):** Emissão paralela de dados com a estrutura `{ timestamp, level, tag, message, data }`, contendo tags padronizadas (ex.: `[DB_FETCH]`, `[HTTP_REQUEST]`, `[VALIDATION]`, `[BUFFER_FLUSH]`) para ingestão por agentes e sistemas de telemetria.

### 2. Serviços Cobertos pelo FlowLogger
O FlowLogger deve mapear ativamente os seguintes componentes do pipeline:
1. **Ingestão de Fornecedores:** Endpoints de recepção de webhooks no servidor Express principal (`app.postback.js`) para Pushfy, Sona, Infobip, Yup e Plugni.
2. **Normalização de Dados:** O componente `normalizer.js`, validando os volumes processados de SMS/VoIP.
3. **Controle de Buffers:** Serviços de armazenamento temporário e escoamento em lote, especificamente o `InfobipBuffer`.
4. **Despacho (Destinos):** O `DispatcherService`, documentando os disparos HTTP para o sistema legado (`status.php`) e os repasses assíncronos para a fila do RabbitMQ (`ack-status-consumer`).

### 3. Implementação no Fluxo (Semáforos Verde, Amarelo e Vermelho)
Para viabilizar a cultura de living documentation e painéis em tempo real:
- **🟢 Sinal Verde (Sucesso):** Flag `ok = true` em métodos como `flow.requestReceived()`, `flow.dataNormalized()` e `flow.destinations()`. Ao término do ciclo (recepção → processamento → despacho), invoca-se `flow.success()`.
- **🟡 Sinal Amarelo (Andamento/Trânsito):** Durante processos com I/O de rede, buffers e chamadas externas, invoca-se `flow.sending()` ou `flow.section()` (para buffers em lote). Visualmente, a requisição entra em estado amarelo enquanto os callbacks não retornam.
- **🔴 Sinal Vermelho (Falha):** Exceções ou quebras de validação disparam `flow.error(msg)` e registros com tag `[ERROR]` ou `[FATAL]`.
- **Sincronização com Daemons:** Daemons em background no RabbitMQ ou agregadores de métricas correlacionam eventos pelo `batch_trace_id`, enviando os estados visualmente para o Hub centralizador via SSE ou WebSocket.

## Consequências

### Positivas
- Rastreamento ponta a ponta desde o webhook do fornecedor até o RabbitMQ e o sistema legado.
- Diagnóstico em segundos no terminal com visualização em árvore sem poluição visual.
- Telemetria JSON estruturada pronta para consumo por coletores e pelo Second Brain.
- Compatibilidade conceitual com o W3C Trace Context do [[ADR-004-trace-ids-e-log-unificado-nas-chamadas-mcp]].

### Desafios / Riscos
- Overhead mínimo de CPU na formatação visual das árvores (mitigado desativando `FLOW_COLORS` em alta carga se necessário).
- Necessidade de propagar rigorosamente o `batch_trace_id` em todos os callbacks assíncronos e jobs do RabbitMQ.

## Times Impactados
- **Dev:** Implementação dos interceptores e chamadas nos 4 componentes (`app.postback.js`, `normalizer.js`, `InfobipBuffer`, `DispatcherService`).
- **QA:** Criação de testes de rastreabilidade ponta a ponta e validação dos semáforos em ambiente de homologação.
- **DevOps:** Configuração da variável `FLOW_COLORS` e ingestão dos logs JSON no pipeline de observabilidade.
- **Arquitetura:** Alinhamento de governança entre o `batch_trace_id` e o `trace_id` corporativo.

## Referências
- [[ADR-004-trace-ids-e-log-unificado-nas-chamadas-mcp]]
- [[systems/hub-producao]]
