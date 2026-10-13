---
id: PB-004
title: "Protocolo de Resiliência: Circuit Breaker, Exponential Backoff e Bulkheads"
status: active
validates: [RULE-001, RULE-002]
environment: hml
targets: [Hub Logístico, Bling ERP Integrations, Webhook Engine]
---

# PB-004: Protocolo de Resiliência: Circuit Breaker, Exponential Backoff e Bulkheads

## Cenário
- **Dado** uma chamada de integração crítica com terceiros (ex: Bling ERP v3, J&T Express, SEFAZ, Salesforce, SAP).
- **Quando** o serviço remoto apresentar lentidão (latência > 3.000ms), indisponibilidade temporária ou retornar erros 5xx consecutivos.
- **Então** o sistema ativa isolamento automático de falhas (*Circuit Breaker*), protege os recursos internos via *Bulkheads* e escalona retries com *Exponential Backoff e Full Jitter*, impedindo degradação em cascata do Hub.

## Procedimento e Regras de Configuração

### 1. Parâmetros do Circuit Breaker
- **Volume Mínimo:** 10 requisições na janela deslizante de 20 segundos.
- **Taxa de Falha para Abertura:** $\ge 50\%$ de erros (5xx ou timeouts).
- **Tempo em Aberto (Cooldown):** 30 segundos.
- **Modo Half-Open:** Permite 3 requisições de teste. Se as 3 forem bem-sucedidas, transiciona para Fechado (Closed). Se qualquer uma falhar, reabre por mais 60 segundos.
- **Ação em Aberto:** Falha instantânea (*Fast Fail*) retornando payload de contingência ou enfileirando em Dead Letter Queue (DLQ).

### 2. Política de Retry
- **Máximo de Tentativas:** 3 retries.
- **Fórmula de Delay:** $\text{random}(0, \min(5000, 200 \times 2^{\text{tentativa}}))\text{ ms}$.
- **Condição:** Nunca retentar erros 4xx (exceto 429 Too Many Requests, respeitando header `Retry-After`).

### 3. Bulkhead de Conexões
- **Pool de Conexões Dedicado:** Máximo de 10 conexões simultâneas por integração externa.
- O esgotamento do pool da transportadora A nunca bloqueia as requisições da transportadora B ou os endpoints internos do Hub.

## Resultado Esperado
- Zero bloqueio ou crash de processos no Hub causado por lentidão de APIs parceiras.
- Alarme de advertência no dashboard de observabilidade assim que o Circuit Breaker entrar no estado `OPEN`.
