---
id: PB-007
title: Auditoria de SPOFs e Plano de Disaster Recovery (RTO / RPO)
status: active
validates: [RULE-001, RULE-002]
environment: production
targets: [Hub Produção, Srv-API, Bancos de Dados, Redis]
---

# PB-007: Auditoria de SPOFs e Plano de Disaster Recovery (RTO / RPO)

## Cenário
- **Dado** o ambiente produtivo da KIOSK Brands hospedando sistemas críticos de despacho, e-commerce e faturamento.
- **Quando** ocorrer desastre catastrófico (queda de data center, corrupção de disco, perda de cluster Docker/K8s ou ataque externo).
- **Então** o plano de continuidade de negócio é acionado garantindo retorno operacional dentro do RTO pactuado e perda máxima de dados delimitada pelo RPO.

## Metas de Serviço (Holding KIOSK)

| Sistema / Componente | RTO (Tempo Máx. de Parada) | RPO (Perda Máx. de Dados) | Estratégia de DR |
| :--- | :--- | :--- | :--- |
| **Emissão Fiscal / Hub Logístico** | 15 minutos | 0 minutos (Zero Data Loss) | PostgreSQL com Replicação Síncrona / Multi-AZ |
| **Banco de Dados de Pedidos** | 30 minutos | < 5 minutos | WAL Archiving contínuo no S3 / Cloud Storage |
| **Second Brain & Dashboards** | 2 horas | < 1 hora | Backups diários com snapshot de volume |
| **Cache Redis** | 5 minutos (Reinicialização) | N/A (Reconstrução a frio) | Cache recriável via banco primário |

## Procedimento Semestral de Auditoria de SPOFs

1. **Auditoria de DNS:** Validar se o TTL dos domínios centrais está configurado para $\le 300\text{ segundos}$ para permitir chaveamento ágil de IP em emergência.
2. **Teste de Failover do Banco:** Simular corte de rede na instância primária e cronometrar o tempo de eleição da réplica secundária para líder.
3. **Teste de Restauração de Backup a Frio:** Restaurar o backup mais recente em uma instância isolada e validar a integridade criptográfica dos dados (checksums).
4. **Verificação de Segredos & Variáveis:** Garantir que cópias encriptadas das chaves e certificados de produção estão replicadas em cofre de segurança secundário (*Key Vault*).

## Resultado Esperado
- Certificado de prontidão operacional emitido pelo time de DevOps e aprovado pelo Tech Lead.
