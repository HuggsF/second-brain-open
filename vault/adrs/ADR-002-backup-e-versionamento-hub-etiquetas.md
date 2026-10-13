---
type: adr
status: Aceito
date: 2026-10-07
---
# ADR-002: Backup, Clonagem Local e Versionamento do Hub Logístico de Etiquetas

## Contexto
Durante a auditoria técnica realizada no primeiro dia de trabalho no servidor de produção `SRV-API` (`191.233.18.195`), identificou-se que os 7 serviços essenciais da KIOSK Brands operam sem controle de versão Git ativo no servidor.

Entre esses serviços, o **Hub Logístico Modular** (`/home/ti-kiosk/hub` - `hub-logistico-v4-completo`), responsável pela emissão de etiquetas de frete, transportadora **J&T Express**, operador logístico **Corpem** e **Bling**, é peça crítica na operação diária de expedição dos pedidos de reposição para os quiosques.

Foi apresentada a proposta de mitigação de riscos de código para a liderança técnica.

## Decisão
O supervisor direto **Davi** autorizou formalmente o seguinte escopo restrito de atuação imediata:

1. **Escopo Aprovado:**
   - Realizar o backup completo do **Hub Logístico de Etiquetas** (`/home/ti-kiosk/hub`).
   - Clonar/baixar o código para a máquina local do desenvolvedor em `C:\KIOSK\hub-logistico`.
   - Inicializar o versionamento Git local, higienizando segredos e arquivos gerados em tempo de execução.
   - Subir o repositório para o GitHub corporativo da Touti Cosmetics (`userTI10`).

2. **Escopo Não Autorizado (Mantido como Está):**
   - Os demais serviços (`hub-sap`, `salesforceapi`, `api-saurus`, `apileads`, `webhook-getnet-prod`, `bling`) permanecem inalterados no servidor e sob governança atual até novas deliberações.

---

## Plano de Execução Técnica

1. **Empacotamento Seguro no Servidor:**
   - Gerar um tarball comprimido de `/home/ti-kiosk/hub` excluindo `node_modules/` (que pode ser reinstalado via `npm install`).
2. **Download Seguro via SFTP/SCP:**
   - Transferir o pacote para `C:\KIOSK\hub-logistico`.
3. **Higienização de Credenciais:**
   - Garantir que arquivos como `.env`, senhas, chaves de API do Bling/J&T e o banco de dados SQLite local (`hub.db`) fiquem fora do Git através de um `.gitignore` rigoroso.
   - Criar `.env.example` sanitizado.
4. **Versionamento e Publicação:**
   - Inicializar repositório Git local (`git init`).
   - Criar commit inicial: `feat: initial commit hub logistico v4.1.0`.
   - Criar repositório privado no GitHub (`hub-logistico` ou `hub-etiquetas`) e realizar o push.
