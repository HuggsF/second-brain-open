---
type: system
status: active
date: 2026-10-21
related: [hub-ontologia-ddd-proposta, hub-mapa-entidades-dominios, protecoes-processamento-emissao-hub, hub-gatilho-nfe-e-politicas-de-emissao]
---

# Regras Operacionais do Hub Logístico — Catálogo Codex

Este documento consolida as **74 invariantes** extraídas dos documentos normativos do Hub Logístico,
organizadas em 8 categorias funcionais. Cada regra possui rastreabilidade ao documento-fonte e branch de origem.

---

## A. Emissão e Segurança

Documento-fonte: `protecoes-processamento-emissao.md` Branch: `main + codex/logistics-preflight`

| ID | Descrição | Documento-Fonte | Branch |
|----|-----------|-----------------|--------|
| INV-01 | processQueue impede reentrada por conexão com WeakSet + finally | protecoes-processamento-emissao.md | main |
| INV-02 | Reserva atômica SQLite com UPDATE+RETURNING subquery, sem transação aberta durante HTTP | protecoes-processamento-emissao.md | main |
| INV-03 | jt_emissions com txlogistic_id persistido ANTES da chamada J&T, state uncertain ou confirmed | protecoes-processamento-emissao.md | main |
| INV-04 | billCode confirmado → atualiza registro ANTES de salvar rastreio e ANTES de registrar sucesso | protecoes-processamento-emissao.md | main |
| INV-05 | Timeout/rejeição após intenção → uncertain + failed com REVIEW_REQUIRED; rejeição inequívoca tratada conservadoramente | protecoes-processamento-emissao.md | main |
| INV-06 | Reenvio manual NÃO limpa intenção → bloqueia repetição automática mesmo após restart | protecoes-processamento-emissao.md | main |
| INV-07 | Sem idempotência presumida da J&T; sem resolução automática de uncertain | protecoes-processamento-emissao.md | main |
| INV-08 | Failed pode conter etiqueta válida; reaproveitamento preservado | protecoes-processamento-emissao.md | main |
| INV-09 | Código cancelado em QUALQUER linha do mesmo pedido bloqueia reaproveitamento | protecoes-processamento-emissao.md | main |
| INV-10 | Cancelamento durante chamada HTTP externa requer verificação manual; sem cancelamento transacional | protecoes-processamento-emissao.md | main |
| INV-11 | Gravações finais/retentativa NÃO sobrescrevem cancelamento recebido durante HTTP | protecoes-processamento-emissao.md | main |
| INV-12 | Divergência Hub-ERP → REVIEW_REQUIRED sem sobrescrever ERP | protecoes-processamento-emissao.md | main |
| INV-13 | NF exige número positivo, série, chave de 44 dígitos não zerada, data de emissão válida | protecoes-processamento-emissao.md | main |
| INV-14 | Falha de consulta NF ou NF incompleta bloqueia emissão ANTES de criar intenção J&T; 429 volta à fila com cooldown | protecoes-processamento-emissao.md | main |
| INV-15 | Rastreios existentes reutilizáveis mesmo com NF indisponível | protecoes-processamento-emissao.md | main |
| INV-16 | Adapter J&T rejeita placeholders em chamadas diretas | protecoes-processamento-emissao.md | main |
| INV-17 | HUB_ENV=hml bloqueia processamento; valores desconhecidos falham fechados | protecoes-processamento-emissao.md | codex/logistics-preflight |
| INV-18 | Banco novo HML carrega todas lojas com gerar_automatico=0 | protecoes-processamento-emissao.md | codex/logistics-preflight |
| INV-19 | Motor mantém jobs pending sem chamar ERP/J&T/WMS em HML; generateLabel rejeita; sem bypass | protecoes-processamento-emissao.md | codex/logistics-preflight |

## B. Preflight Logístico

Documento-fonte: `correcao-preflight-logistica-2026-10-08.md` Branch: `codex/logistics-preflight`

| ID | Descrição | Documento-Fonte | Branch |
|----|-----------|-----------------|--------|
| PREFLIGHT-01 | Zero volumes ou ID ausente → REVIEW_REQUIRED: LOGISTICS_OBJECT_MISSING antes de emissão | correcao-preflight-logistica-2026-10-08.md | codex/logistics-preflight |
| PREFLIGHT-02 | Múltiplos volumes → REVIEW_REQUIRED: MULTIPLE_VOLUMES_UNDEFINED antes de emissão | correcao-preflight-logistica-2026-10-08.md | codex/logistics-preflight |
| PREFLIGHT-03 | Jobs bloqueados não gastam retries automáticos nem geram novas intenções | correcao-preflight-logistica-2026-10-08.md | codex/logistics-preflight |
| PREFLIGHT-04 | Webhook repetido reconhece código novo e mensagem estrutural antiga; não duplica job | correcao-preflight-logistica-2026-10-08.md | codex/logistics-preflight |
| PREFLIGHT-05 | Etiqueta existente preservada; após regularização, motor reutiliza rastreio | correcao-preflight-logistica-2026-10-08.md | codex/logistics-preflight |
| PREFLIGHT-06 | Adapter revalida objeto no segundo GET para detectar alterações entre preflight e UPDATE | correcao-preflight-logistica-2026-10-08.md | codex/logistics-preflight |
| PREFLIGHT-07 | Sem contrato presumido para criação automática, seleção multi-volume ou cancel/reemissão | correcao-preflight-logistica-2026-10-08.md | codex/logistics-preflight |

## C. Admissão NF-e

Documento-fonte: `gatilho-nfe.md` Branch: `main`

| ID | Descrição | Documento-Fonte | Branch |
|----|-----------|-----------------|--------|
| NFE-01 | Gatilho: invoice.created ou invoice.updated apenas | gatilho-nfe.md | main |
| NFE-02 | NF deve ser situação 5 ou 6, com número, série, data de emissão, chave de acesso de 44 dígitos | gatilho-nfe.md | main |
| NFE-03 | Pedido localizado por numerosLojas[] ou loja+contato; binding confirmado por pedido.notaFiscal.id | gatilho-nfe.md | main |
| NFE-04 | Busca paginada limitada a 20 páginas; binding ausente/ambíguo bloqueia emissão | gatilho-nfe.md | main |
| NFE-05 | Situações permitidas: 6, 9, 748644 — checadas na admissão E novamente pelo motor | gatilho-nfe.md | main |
| NFE-06 | Escopo restrito a 4 lojas (IDs: 206264482, 206084387, 206085936, 206288765) | gatilho-nfe.md | main |
| NFE-07 | Inserção atômica impede nova entrada se pending/processing/success/cancelado/REVIEW_REQUIRED ou intenção uncertain existe | gatilho-nfe.md | main |
| NFE-08 | Eventos com mesmo eventId+NF ID não reprocessados; sem eventId, dedup por pedido | gatilho-nfe.md | main |
| NFE-09 | Validação interrompida reserva retomável após 10 minutos com token de reserva | gatilho-nfe.md | main |
| NFE-10 | Motor re-busca pedido+NF, revalida checks fiscais, confirma binding invoice_id antes de emissão | gatilho-nfe.md | main |
| NFE-11 | 10 retries além da primeira tentativa (11 execuções total); cooldown 30/60/90...300s | gatilho-nfe.md | main |
| NFE-12 | HTTP 429 em chamadas Bling: até 10 retries por chamada, min 1500ms, limiter 3 calls/s | gatilho-nfe.md | main |
| NFE-13 | Nenhum retry de NF-e repete emissão J&T de resultado incerto | gatilho-nfe.md | main |

## D. Recuperação Logística Bling

Documento-fonte: `bling-logistics-recovery.md` Branch: `main`

| ID | Descrição | Documento-Fonte | Branch |
|----|-----------|-----------------|--------|
| RECOVERY-01 | Quando pedido não tem transporte.volumes, adapter busca objeto vinculado à NF e bling_logistics_creations | bling-logistics-recovery.md | main |
| RECOVERY-02 | POST /logisticas/objetos com pedido+NF+serviço+rastreio existente; resposta verificada por GET | bling-logistics-recovery.md | main |
| RECOVERY-03 | Intenção SQLite reservada antes do POST; ID persistido antes de continuar | bling-logistics-recovery.md | main |
| RECOVERY-04 | Timeout/5xx/ID ausente → criação uncertain → REVIEW_REQUIRED; sem retry automático POST | bling-logistics-recovery.md | main |
| RECOVERY-05 | Recuperação NÃO chama J&T addOrder: preserva etiqueta existente | bling-logistics-recovery.md | main |
| RECOVERY-06 | Embalagem padrão: Caixa M 16671795179, 0.05 kg quando sem informação | bling-logistics-recovery.md | main |
| RECOVERY-07 | dataSaida zerada/inválida → substituída pela data de criação | bling-logistics-recovery.md | main |

## E. Cache de Produtos e Peso

Documento-fonte: `product-catalog-weight.md` Branch: `codex/product-weight-cache (local)`

| ID | Descrição | Documento-Fonte | Branch |
|----|-----------|-----------------|--------|
| WEIGHT-01 | Preservar transporte.pesoBruto > 0.1 kg; para ausente/inválido/≤0.1, calcular de pesos de produto | product-catalog-weight.md | codex/product-weight-cache |
| WEIGHT-02 | peso = sum(peso bruto produto × qty item NF) + peso embalagem | product-catalog-weight.md | codex/product-weight-cache |
| WEIGHT-03 | Cálculo ocorre após check de elegibilidade, antes de intenção de emissão | product-catalog-weight.md | codex/product-weight-cache |
| WEIGHT-04 | Cancelamento recebido durante cálculo impede addOrder | product-catalog-weight.md | codex/product-weight-cache |
| WEIGHT-05 | Lookup de cache por product ID ou SKU exato; SKU duplicado e peso zero/ausente bloqueiam emissão | product-catalog-weight.md | codex/product-weight-cache |
| WEIGHT-06 | Eventos de produto (created/updated/deleted) com HMAC; persistir antes de ACK; detalhe buscado da API | product-catalog-weight.md | codex/product-weight-cache |
| WEIGHT-07 | Deleção invalida cache imediatamente; eventos antigos não ressuscitam produtos deletados | product-catalog-weight.md | codex/product-weight-cache |
| WEIGHT-08 | Objeto existente → embalagem do Bling; sem embalagem → Caixa M | product-catalog-weight.md | codex/product-weight-cache |
| WEIGHT-09 | Objeto com rastreio correspondente ainda atualizado se falta embalagem/peso ou peso recalculado divergente | product-catalog-weight.md | codex/product-weight-cache |

## F. Monitor de Fila

Documento-fonte: `queue-status-events.md` Branch: `main`

| ID | Descrição | Documento-Fonte | Branch |
|----|-----------|-----------------|--------|
| QMON-01 | "Situação Bling" vem da projeção order_bling_status, alimentada apenas por webhooks e respostas HTTP 200 | queue-status-events.md | main |
| QMON-02 | Observações não iniciam consultas adicionais, não re-enfileiram, não alteram admissão NF-e | queue-status-events.md | main |
| QMON-03 | Falhas de persistência de projeção não interrompem emissão | queue-status-events.md | main |
| QMON-04 | Tela atualiza a cada 5s via leitura local do DB; nenhuma query Bling pela tela | queue-status-events.md | main |
| QMON-05 | completedOrders conta ERP IDs distintos com "Fluxo completo" em system_logs do dia (São Paulo tz) | queue-status-events.md | main |
| QMON-06 | Histórico depende de retenção do system_logs; remover logs reduz contagem | queue-status-events.md | main |

## G. Logging de Integração

Documento-fonte: `integration-logging.md` Branch: `main`

| ID | Descrição | Documento-Fonte | Branch |
|----|-----------|-----------------|--------|
| LOG-01 | Cada chamada HTTP produz http.request + http.response/http.error vinculados por requestId | integration-logging.md | main |
| LOG-02 | Tokens, senhas, cookies, assinaturas, contas auth são redatados | integration-logging.md | main |
| LOG-03 | PDFs/buffers/base64 representados apenas pelo tamanho | integration-logging.md | main |
| LOG-04 | Dados de negócio (incluindo destinatário) permanecem para diagnóstico — NÃO exportar log como arquivo público | integration-logging.md | main |
| LOG-05 | Falha de logging não altera retorno HTTP nem erro | integration-logging.md | main |

## H. Deploy e Rollback

Documento-fonte: `deploy-rollback.md` Branch: `main`

| ID | Descrição | Documento-Fonte | Branch |
|----|-----------|-----------------|--------|
| DEPLOY-01 | Deploy somente SHA aprovado com testes Node 18/20 + manifesto SHA-256 | deploy-rollback.md | main |
| DEPLOY-02 | HML primeiro; produção inicia com HUB_WORKER_ENABLED=0 | deploy-rollback.md | main |
| DEPLOY-03 | Validar PM2, HTTP interno/público, SHA, env, SQLite quick_check, config de lojas antes de liberar fila | deploy-rollback.md | main |
| DEPLOY-04 | Observar tráfego natural ≥5 minutos, comparar com janela equivalente anterior | deploy-rollback.md | main |
| DEPLOY-05 | Rollback: parar PM2, backup SQLite atual, restaurar SÓ CÓDIGO (manter DB, credenciais, node_modules), iniciar com worker pausado | deploy-rollback.md | main |
| DEPLOY-06 | NÃO restaurar DB pré-deploy automaticamente: apagaria confirmações de etiqueta | deploy-rollback.md | main |
| DEPLOY-07 | Gatilhos de rollback: HTTP indisponível, SHA/env/policy incorretos, SQLite corrupto, restart inesperado, novo erro terminal, inconsistência de rastreio | deploy-rollback.md | main |
| DEPLOY-08 | 429 recuperável → alertar, verificar progresso; 429 persistente sem progresso → pausar e investigar | deploy-rollback.md | main |

---

## DEM-NN Pendentes

Itens identificados durante a consolidação que requerem decisão ou implementação futura:

| ID | Descrição | Status |
|----|-----------|--------|
| DEM-01 | Definir política de retenção de system_logs e impacto em QMON-05/QMON-06 | pendente |
| DEM-02 | Padronizar contrato de criação automática de objeto logístico para múltiplos volumes (PREFLIGHT-07) | pendente |
| DEM-03 | Avaliar resolução semiautomática de estados uncertain com confirmação humana (INV-07) | pendente |
| DEM-04 | Definir estratégia de cache warm-up para produtos sem peso cadastrado (WEIGHT-05) | pendente |
| DEM-05 | Estabelecer SLA de observabilidade pós-deploy com métricas quantitativas (DEPLOY-04) | pendente |
| DEM-06 | Documentar procedimento de verificação manual para cancelamentos durante HTTP (INV-10) | pendente |
