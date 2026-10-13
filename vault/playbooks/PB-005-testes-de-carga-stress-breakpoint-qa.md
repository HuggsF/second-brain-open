---
id: PB-005
title: Protocolo de Testes de Carga, Estresse e Ponto de Ruptura (QA)
status: active
validates: [RULE-001, RULE-002]
environment: hml
targets: [Hub Homologação, Srv-API, Webhooks]
---

# PB-005: Protocolo de Testes de Carga, Estresse e Ponto de Ruptura (QA)

## Cenário
- **Dado** o ambiente de Homologação sanitizado (sem chamadas a emissores reais, conforme [[RULE-002-homologacao-sem-chamadas-externas]]).
- **Quando** o time de QA executa a suíte de avaliação de desempenho antes de grandes campanhas ou deploys arquiteturais estruturais.
- **Então** o sistema é submetido a estágios controlados de carga (Smoke -> Average Load -> Stress -> Spike -> Breakpoint), gerando os limites operacionais certificados e o ponto ótimo da Lei de Little.

## Fases da Execução

```
Estágio 1: Smoke (10 RPS / 5 VUs por 2 min) ────► Validar 0% de erro funcional
                 │
Estágio 2: Average Load (50 RPS por 10 min) ────► P95 < 250ms, CPU < 60%
                 │
Estágio 3: Stress Test (150 RPS por 10 min) ────► Validar auto-recuperação
                 │
Estágio 4: Spike Test (0 a 300 RPS em 10s)  ────► Validar Rate Limiting / 429
                 │
Estágio 5: Breakpoint Test (Ramping contínuo) ──► Descobrir RPS de colapso
```

### Checklist Pré-Voo de QA:
1. Confirmar que o mock server de homologação está ativo e isolado.
2. Zerar contadores de telemetria e iniciar coleta de Four Golden Signals.
3. Executar o script K6 ou Locust com ramp-up gradual.
4. Monitorar saturação de pools de conexão e consumo de CPU/Memória do PostgreSQL.

### Critérios de Aceite e Limiares:
- **Taxa de Erro:** $< 0.1\%$ em Average Load.
- **Latência P95:** $< 300\text{ms}$ para geração de despacho.
- **Latência P99:** $< 800\text{ms}$.
- **Comportamento no Breakpoint:** O sistema deve rejeitar graciosamente com HTTP 429 / 503 com header `Retry-After`, sem travar o processo Node.js ou corromper dados no banco.

## Resultado Esperado
Relatório de homologação emitido com o RPS máximo suportado com segurança pela infraestrutura atual.
