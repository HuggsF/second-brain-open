# Time: QA & Testes (Garantia da Qualidade & Confiabilidade)

## Escopo
Garantia de qualidade, validação funcional e de integração, proteção contra efeitos colaterais críticos (como duplicidade de etiquetas de frete e emissões indevidas de NFs), testes de concorrência e execução da suíte de testes de carga e estresse de sistemas distribuídos.

## Papel no Modelo Full-Cycle
No modelo full-cycle da KIOSK Brands:
- A disciplina de QA é praticada pela dupla de engenharia através de **testes automatizados de regressão**, **rotinas de auto-auditoria** e **testes de performance contínuos**.
- O foco primário é proteger as regras mais críticas da empresa (onde um bug gera prejuízo financeiro direto ou atrito com clientes/franqueados).
- Utilizam-se coleções organizadas no Postman ([[postman-collection]]), checklists de pré-voo ([[hub-logistics-preflight]]) e execução de testes de carga e concorrência antes de liberações em produção.

## Sistemas sob responsabilidade
- [[comparativo-prod-homolog-postman]] — Comparação sistemática de respostas e payloads entre ambientes
- [[postman-collection]] — Coleção de requisições de teste para todas as rotas do Hub e integrações
- [[investigacao-duplicidade-etiquetas]] — Caso de referência e regras de proteção contra etiquetas duplicadas
- [[hub-logistics-preflight]] — Checklist de verificação antes de liberar o fluxo logístico
- [[protecoes-processamento-emissao-hub]] — Validação de travas e semáforos de processamento concorrente
- [[metodo-auto-auditoria]] — Rotinas automáticas de conciliação de dados emitidos

## Regras e Diretrizes do Time (System Design & Qualidade)
1. **Zero Emissão Duplicada (Teste de Concorrência):** Testes de concorrência com payloads idênticos enviados em paralelo (10 a 50 threads concorrentes) devem sempre retornar `HTTP 409 Conflict` ou devolver a mesma etiqueta já gerada (idempotência absoluta garantida por [[PB-006-transacoes-distribuidas-saga-outbox]]).
2. **Pirâmide de Testes de Carga Obrigatória:** Antes de grandes campanhas ou atualizações de infraestrutura, executar rigorosamente o protocolo [[PB-005-testes-de-carga-stress-breakpoint-qa]]:
   - *Smoke Test* (1 a 5 VUs): Sanidade de contratos e ausência de exceptions.
   - *Average Load Test* (50 RPS): Validação de latência P95 $< 300\text{ms}$ e saturação controlada.
   - *Stress Test* (150 RPS): Validação de estabilidade sob carga 2x superior ao pico diário.
   - *Spike Test* (0 a 300 RPS): Validação de proteção por Rate Limiting e recusa graciosa.
   - *Breakpoint Test*: Determinação do ponto de saturação física da infraestrutura.
3. **Validação de Circuit Breakers e Degradação Graciosa:** Injetar falhas artificiais e latência simulada nos mocks de homologação para certificar que o disjuntor abre e o sistema não trava em cascata ([[PB-004-resiliencia-circuit-breaker-retry-bulkhead]]).
4. **Comparativo Homologação vs Produção:** Antes de subir alteração de payload, validar se o contrato é 100% retrocompatível ([[comparativo-prod-homolog-postman]]).
5. **Auditoria Contínua:** Auditoria periódica comparando pedidos no ERP vs pedidos emitidos no Hub.
6. **Isolamento de Homologação:** Homologação opera estritamente sem chamadas a serviços externos reais ([[RULE-002-homologacao-sem-chamadas-externas]]).

## Canais de Comunicação
- **Desenvolvimento (`demand`):** Registro de bugs, divergências de contrato, race conditions ou gargalos de latência identificados em testes.
- **DevOps & Infra (`handoff`):** Aprovação técnica ("sinal verde") após validação de carga e concorrência em homologação, autorizando o deploy em produção.
- **Logística / Operações (`adr` / `playbook`):** Orientações sobre casos de borda e playbooks de contingência operacional.
