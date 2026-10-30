---
type: system
status: active
date: 2026-10-22
---
# Hub de Integração SAP B1 (hub-sap)

## Visão Geral
Recebe cadastros de franqueados (Salesforce Screen Flow via Apex `HubSapCadastro`, ou webhook JSON) e cria no [[sap]] B1, via Service Layer, o Parceiro de Negócio (`BusinessPartners`) e depois a tabela adicional UDO `HCO003`. Gera o código do cliente por empresa (YES `Y`, AMAVIA `A`, TOUTI `0`) com reserva. Tela **Recebidos** com modo automático e manual.

| Campo | Valor |
|-------|-------|
| **Time responsável** | erp-integrations |
| **Ambiente** | production (única instância) |
| **Repositório** | `userTI10/hub-sap` (privado) |
| **Tecnologia** | Node.js, Express 4, SQLite, axios |
| **Status** | Ativo |

## Arquitetura
- Salesforce → HTTPS → Nginx (443) → hub em `127.0.0.1:3100` → Service Layer (Skyone, porta 50000). Fonte: `deploy/DEPLOY.md` no repo.
- Roda no [[srv-api]] como serviço systemd `hub-sap`, usuário `hub`, código em `/opt/hub-sap`, banco em `/var/lib/hub-sap/hub.db`, backups diários em `/var/backups/hub-sap`.
- **Runtime:** Node 22 próprio em `/opt/hub-sap-node` (o `instalar.sh` reescreve o `ExecStart`), porque o Node do sistema no SRV-API é 18.19. Nunca rodar `npm ci` do hub com o Node do PATH: o `sqlite3` nativo fica com ABI errada.

## Deploy (estado em 2026-10-22)
- **Manual:** copiar o código para o servidor e `sudo bash deploy/atualizar.sh` (backup, rsync para `/opt/hub-sap`, `npm ci --omit=dev` com o Node do hub, restart, GET em `/hub/`). `/opt/hub-sap` **não é clone git**.
- `atualizar.sh` não sai com erro quando o health check falha, e ignora falha do backup (`|| true`). Precisa mudar antes de servir de base para um pipeline.
- **Homologação** não é instância: é a base SAP `TSTTOUTI3`, configurada como outra conexão na mesma instância (produção: `SBOTOUTI`). Não existe branch `hml`.
- **GitHub:** Actions bloqueado por cobrança da conta em 22/10 (runs 39827147791 e 39827251986 nem iniciaram). Proteção de branch indisponível (403, plano gratuito com repo privado). Nenhum secret ou environment.

## Limitações Conhecidas
- PR #1 (`feature/kiosk-bootstrap`): a versão original (`a083443`) trazia deploys incompatíveis com o servidor. O commit `7808b84` removeu os workflows de deploy, passou o CI para Node 22 (só `pull_request` + `workflow_dispatch`), criou `CLAUDE.md` e `.gitattributes` e alinhou o ADR-001 (Proposto) ao `deploy/DEPLOY.md`. CI ainda sem execução por causa da cobrança do Actions.
- `npm test` no Windows: 87 de 87 cenários OK, mas exit 1 por EPERM no `fs.rmSync` da pasta temporária (`tests/e2e.js:46`).
- Fallback de senha do admin quando `HUB_ADMIN_SENHA` está vazio (`database.js:114`); o `instalar.sh` gera senha aleatória.
- UI em HTML/CSS puro (`public/hub.css`), tema claro primeiro e acento azul: fora do design system KIOSK.

## Bootstrap v2 (2026-10-29)
Fonte: relatório do agente do Antigravity (`kiosk-bootstrap` 1.3.0); não conferido no GitHub por esta nota.
- PR #1 (`feature/kiosk-bootstrap`) recriada a partir da `main` com force-push. Substitui o estado descrito em "Limitações Conhecidas" (commits `a083443` e `7808b84` da v1 continuam no histórico).
- `AGENTS.md` é a única fonte de regras do repositório; `CLAUDE.md` só importa `@AGENTS.md`; o `GEMINI.md` da v1, que repetia as regras globais, saiu do PR (recuperável em `7808b84`). `ci.yml` inalterado; ADR-001 reescrito para a stack com frontend React em `web/`, o que torna desatualizada a linha sobre UI em HTML/CSS puro acima.
- A UI pede disparos de comunicação ao `regua-cobranca` por proxy em `server.js`; envio e controle de duplicatas ficam no `regua-cobranca`.
- **Segurança:** `server.js:125` tem um JWT fixo como fallback de `COBRANCA_SERVICE_TOKEN`, commitado em todas as branches. Pendente: confirmar se o `regua-cobranca` aceita esse token em algum ambiente, invalidar e girar o segredo de assinatura se aceitar, e trocar o fallback por falha no boot. Valor não registrado.
- Pendente: as tabelas de entidades e integrações do `AGENTS.md` da v1 não foram transferidas para esta nota; a origem é o histórico da v1 (`7808b84`), possivelmente desatualizado.
- Pendentes do relatório: Actions bloqueado por cobrança, proteção da `main`, saída com erro do `atualizar.sh`, EPERM do `npm test` no Windows, `strict` no `web/tsconfig.json`, `docs/regras/ids/` e caminho do contrato Salesforce.

## Referências
- [[srv-api]]
- [[sap]]
- [[salesforce]]
- [[inventario-repositorios]]
