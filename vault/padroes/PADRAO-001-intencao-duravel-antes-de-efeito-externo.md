---
type: padrao
id: PADRAO-001
title: "Intenção durável antes de efeito externo irreversível"
status: active
date: 2026-10-29
dono: ["Hugo Melo (TI)", "Gustavo Bastos (E-commerce)"]
problema: "efeito-externo-duplicado"
adocao: aplicado
aplicado_em:
  - "vault/systems/protecoes-processamento-emissao-hub.md:25"
  - "vault/systems/protecoes-processamento-emissao-hub.md:27"
  - "ADR-027-recuperacao-logistica-bling-com-intencao-duravel"
---
# PADRAO-001: Intenção durável antes de efeito externo irreversível

## Problema
Uma chamada a sistema externo cria algo que não se desfaz (etiqueta de transportadora, objeto
logístico no ERP). Se a resposta se perde por timeout ou o processo reinicia, repetir a chamada pode
duplicar o efeito e a cobrança. O fornecedor não garante idempotência.

## Solução
1. Gravar a intenção, com identificador próprio, **antes** de chamar o sistema externo.
2. Enviar o identificador registrado na chamada.
3. Confirmada a resposta, atualizar a intenção antes de qualquer outro passo.
4. Resultado incerto (timeout, rejeição ambígua, falha após a intenção) bloqueia nova chamada
   automática e manda para revisão humana; reenvio manual não limpa a intenção.
5. Nas tentativas seguintes, reutilizar o que já foi criado em vez de criar de novo.

## Onde está aplicado
- Hub Logístico, emissão J&T: tabela `jt_emissions`, uma intenção por `erp_id` com `txlogistic_id`
  gravado antes da chamada (`vault/systems/protecoes-processamento-emissao-hub.md:25` a `:28`).
- Hub Logístico, objeto logístico no Bling: `bling_logistics_creations`
  ([[ADR-027-recuperacao-logistica-bling-com-intencao-duravel]]).
- Regra e código: [[RULE-006-intencao-jt-uncertain-bloqueia-reemissao]] e `[EMISSAO-05]`.

O custo aceito é disponibilidade menor durante a incerteza em troca de não duplicar frete (ADR-027).

## Anti-padrões que corrige
- [[ANTIPADRAO-001-efeito-externo-sem-estado-previo-nem-intencao]]

## Referências
- [[ADR-043-modelo-de-governanca-tipos-e-relacoes]]
- [[protecoes-processamento-emissao-hub]]
