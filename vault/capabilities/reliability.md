---
type: capability
status: active
date: 2026-10-13
---
# Capacidade: Confiabilidade & SRE

## Escopo
Automação de pipelines de CI/CD, gestão de ambientes de homologação e produção, observabilidade contínua (Four Golden Signals, USE, RED), resiliência de infraestrutura (Bulkheads, Circuit Breakers), segurança de segredos e planos de Disaster Recovery da KIOSK Brands.

Como a equipe de engenharia é formada pela dupla de desenvolvedores, as práticas de DevOps e SRE são incorporadas diretamente no dia a dia através de **infraestrutura como código**, **telemetria em tempo real** e **automação de ponta a ponta**:
- Não há uma "parede" separando desenvolvimento de operações (*You build it, you run it*).
- Ambientes previsíveis e reproduzíveis diminuem o esforço manual de deploy para zero.
- Telemetria ativa (PM2, Grafana, Prometheus, Loki, OpenTelemetry) alerta a equipe antes que os usuários de negócio percebam qualquer instabilidade.

## Sistemas sob responsabilidade
- [[proposta-pipeline-ci-cd-github-actions]] — Pipeline automatizado de lint, teste e deploy
- [[implantacao-instancia-homologacao]] — Ambiente espelho seguro para testes sem risco de emissões reais
- [[deploy-validacao-hub-2026-10-08]] — Procedimentos e validações pós-deploy
- [[post-deploy-observabilidade-hub]] — Dashboards e alarmes de saúde pós-deploy
- [[rate-limiting-bling-producao]] — Configuração de proxies e limites de vazão em produção
- [[inventario-github]] — Gestão de repositórios, segredos e acessos da organização
- [[inventario-repositorios]] — Mapeamento de branches, dependências e versões

## Diretrizes de Operação (System Design & SRE)
1. **Four Golden Signals Obrigatórios:** Monitoramento contínuo dos 4 sinais vitais do Hub e microsserviços ([[05-capacidade-testes-carga-observabilidade]]):
   - *Latência:* Acompanhada estritamente em P95 e P99 (separando erros de sucessos).
   - *Tráfego:* Requisições por segundo (RPS) e conexões ativas.
   - *Erros:* Taxa percentual de erros HTTP 5xx e falhas de integração.
   - *Saturação:* Uso de CPU, memória e profundidade de filas de espera.
2. **Diagnóstico Sistemático via USE & RED:** Recursos de hardware/banco governados pelo método USE (Utilização, Saturação, Erros); serviços de aplicação governados pelo método RED (Rate, Errors, Duration).
3. **Deploys Seguros (Blue/Green & Canary):**
   - Deploys em produção utilizam estratégia Blue/Green ou Canary com roteamento progressivo ([[04-resiliencia-confiabilidade-alta-escala]]).
   - **Rollback Instantâneo:** Todo deploy deve possuir reversão automática acionada caso a taxa de erros exceda 1% nos primeiros 5 minutos.
4. **Isolamento de Falhas com Bulkheads:** Configurar pools de conexão, limites de memória e réplicas separados para tráfego transacional crítico vs tráfego analítico de relatórios ([[PB-004-resiliencia-circuit-breaker-retry-bulkhead]]).
5. **Auditoria de SPOFs e Disaster Recovery:** Garantir que o plano de contingência atenda às metas contratuais: **RTO $\le 15\text{ minutos}$** e **RPO $= 0\text{ minutos}$** para dados fiscais e de despacho ([[PB-007-disaster-recovery-spof-avaliacao-rto-rpo]]).
6. **Segredos Isolados e Rotatividade:** Chaves de API de produção (Bling v3, J&T, SAP, SEFAZ) nunca trafegam em código ou repositórios públicos.
7. **Homologação Estritamente Sanitizada:** Garantir que nenhuma chave ou webhook ativo em homologação aponte para serviços de produção externos ([[RULE-002-homologacao-sem-chamadas-externas]]).
