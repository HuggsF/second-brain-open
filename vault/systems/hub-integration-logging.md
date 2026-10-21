---
type: system
status: active
date: 2026-10-21
related: [hub-regras-operacionais-codex, hub-logistico-schema-regras-negocio, post-deploy-observabilidade-hub]
source: hub-logistico/docs/integration-logging.md
source_branch: codex/detailed-integration-logs
---

# Logs Detalhados de Integração — Hub Logístico

Sistema de logging estruturado para chamadas HTTP dos adapters do Hub Logístico (`adapters/bling.js` e `adapters/jtExpress.js`).

## Mecanismo

Cada chamada HTTP dos adapters produz registros com prefixo `[INTEGRATION]` no console e em `system_logs` com `type='integration'`. Não é necessária migração do banco.

Cada chamada gera dois registros vinculados por `requestId`:
- `http.request` — antes da chamada
- `http.response` ou `http.error` — após a chamada

## Campos Registrados

| Campo | Descrição |
|---|---|
| Horário UTC | Timestamp da chamada |
| Provedor | `bling` ou `jtExpress` |
| Método/URL/Parâmetros | Detalhes do HTTP |
| Status HTTP e duração | Resultado e tempo |
| ERP ID, ID da fila, tentativa | Contexto do worker |
| NF ID e evento | Contexto da admissão fiscal |
| `txlogisticId` | Presente nos envios J&T |

## Segurança nos Logs

- **Ocultados:** tokens, senhas, cookies, assinaturas e contas de autenticação
- **Resumidos:** PDFs, buffers e campos base64 (representados por tamanho)
- **Preservados:** dados de negócio, incluindo dados de destinatário (necessários para diagnóstico)
- O formulário J&T é decodificado para exibir o JSON `bizContent` efetivamente enviado, sem assinaturas

> **INVARIANTE:** Uma falha ao gravar ou imprimir o log não altera o retorno nem o erro HTTP. Registros existentes de etapas e falhas finais do motor são preservados.

## Consultas SQL Úteis

```sql
-- Por pedido (ERP ID)
SELECT datetime(created_at, '-3 hours') AS horario_brasilia, message
FROM system_logs
WHERE type = 'integration'
  AND json_extract(substr(message, instr(message, '{')), '$.erpId') = '<ERP_ID>'
ORDER BY id;

-- Por requestId (request + response)
SELECT message FROM system_logs
WHERE type = 'integration'
  AND json_extract(substr(message, instr(message, '{')), '$.requestId') = '<REQUEST_ID>'
ORDER BY id;

-- Chamadas recentes
SELECT datetime(created_at, '-3 hours') AS horario_brasilia, message
FROM system_logs
WHERE type = 'integration'
ORDER BY id DESC LIMIT 200;
```

## Limitações

- JSON preservado é o corpo do Axios, não captura de pacotes
- Em timeout sem resposta, status e corpo ficam nulos (não há resposta inventada)
- A camada de autenticação OAuth e chamadas Axios fora dos dois adapters **não são instrumentadas**
- Registros só existem para chamadas realizadas após a implantação do módulo
- Logs não devem ser exportados como arquivo público (contêm dados de negócio)
