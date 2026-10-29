---
type: antipadrao
id: ANTIPADRAO-002
title: "Falha silenciosa de integração: erro acumula sem alerta"
status: active
date: 2026-10-29
dono: ["Hugo Melo (TI)", "Gustavo Bastos (E-commerce)"]
problema: "falha-de-integracao-nao-detectada"
viola: []
corrigido_por: []
detectado_por: []
ocorreu_em:
  - "vault/systems/incidente-2026-10-13-oauth-bling-hub.md:7"
  - "vault/systems/incidente-2026-10-13-oauth-bling-hub.md:18"
sintoma: "Pedidos em failed por dias sem que ninguém saiba"
---
# ANTIPADRAO-002: Falha silenciosa de integração

## O que é
Tratar erro de integração só como registro na fila e no log, sem sinal ativo para quem opera. O
sistema continua de pé, a fila continua girando, e a falha só aparece quando alguém reclama.

## Onde ocorreu
Hub Logístico, incidente de 08 a 13/10/2026
([[incidente-2026-10-13-oauth-bling-hub]]): a troca do app OAuth do Bling fez o Hub perder acesso
aos pedidos; a detecção levou cerca de 4 dias
(`vault/systems/incidente-2026-10-13-oauth-bling-hub.md:7`) e 140 pedidos entraram em `failed`
(`vault/systems/incidente-2026-10-13-oauth-bling-hub.md:18`).

## Como detectar
**Lacuna de prevenção.** Nenhum teste, check ou playbook ativo detecta hoje taxa de falha alta ou
token sem acesso. A checagem pós-deploy ([[post-deploy-observabilidade-hub]]) observa só a janela
após um deploy; o incidente começou por mudança de credencial, sem deploy.

## Correção
Sem padrão definido. O ponto de partida é o [[hub-plano-observabilidade]] (rascunho): alerta por
taxa de falha da fila e por saúde do token. A troca de credencial tem procedimento próprio em
[[PB-012-rotacao-e-revalidacao-credenciais-oauth-bling]].

## Referências
- [[ADR-043-modelo-de-governanca-tipos-e-relacoes]]
