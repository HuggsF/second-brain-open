---
type: system
status: active
date: 2026-10-21
related: [hub-regras-operacionais-codex, hub-logistics-preflight, hub-producao, hub-homologacao]
source: hub-logistico/docs/deploy-rollback.md
source_branch: codex/logistics-preflight
---

# Deploy e Rollback Controlados — Hub Logístico

Procedimentos operacionais para implantação e reversão do Hub Logístico em produção e homologação, documentados a partir do deploy de 08/10/2026.

## Pré-requisitos de Deploy

- Implantar somente SHA aprovado com testes Node 18/20 e manifesto SHA-256.
- Homologação primeiro; produção só após validação completa em HML.
- Produção inicia com `HUB_WORKER_ENABLED=0` (worker pausado).

## Validação Pós-Ativação

Antes de liberar a fila, verificar:

1. **PM2** — processo rodando e estável
2. **HTTP interno/público** — endpoints respondendo
3. **SHA** — REVISION bate com o SHA esperado
4. **Ambiente** — variáveis de ambiente corretas
5. **SQLite** — `quick_check` sem corrupção
6. **Lojas** — configuração das lojas autorizadas consistente

Observar tráfego natural por pelo menos **cinco minutos** e comparar com janela anterior equivalente.

## Procedimento de Rollback

1. Parar PM2
2. Criar backup SQLite consistente do estado atual
3. Restaurar **somente código** anterior (manter banco atual, credenciais e node_modules)
4. Iniciar código anterior com worker pausado

> **INVARIANTE:** Nunca restaurar banco pré-deploy automaticamente — apagaria confirmações de etiquetas e dados do ledger.

O preload externo `worker-gate.cjs` suprime `startEngine` no código antigo. Reconciliar chamadas J&T incertas e jobs interrompidos antes de autorizar reativação.

## Gatilhos para Rollback

- HTTP indisponível
- SHA/ambiente/política incorretos
- Corrupção SQLite
- Reinício inesperado do PM2
- Novo erro terminal não previsto
- Inconsistência de rastreio
- 429 recuperável gera alerta; falta de progresso com backlog ou crescimento persistente de 429 exige pausar e investigar

## Controle Externo

Script: `/home/ti-kiosk/hub-deploy/deploy-control.py`

Comandos principais:

```bash
# Preparação (testa em release isolado com adapters simulados)
deploy-control.py prepare --environment production --sha <SHA> --archive <path>

# Ativação
deploy-control.py activate --environment production --state <state.json>

# Verificação pós-deploy
node scripts/post-deploy-check.js --environment production --expected-sha <SHA> --worker-enabled 0 --since <UTC>

# Liberação da fila
deploy-control.py release --environment production --state <state.json>

# Inspeção
deploy-control.py inspect --environment production --state <state.json>

# Rollback
deploy-control.py rollback --environment production --state <state.json>
```

## Considerações Operacionais

- Homologação usa `--environment hml` e permanece pausada.
- Persistir PM2 após estabilidade com `pm2 save`.
- O controlador **não** agenda rollback sozinho; operador aplica política aos relatórios.
- Falha durante cópia restaura código e inicia pausado.
- `REVISION` contém SHA exportado do Git; `/healthz` usa marcador sem Git.
- Backups e dump PM2 contêm dados privados — não anexar a issues.
- A reinicialização do PM2 executa no diretório da aplicação; `NODE_OPTIONS` aplica-se ao CLI e preload resolve `engine.js` pelo `cwd`.
