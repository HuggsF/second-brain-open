---
type: antipadrao
id: ANTIPADRAO-001
title: "Efeito externo sem consultar estado prévio nem registrar intenção"
status: active
date: 2026-10-29
dono: ["Hugo Melo (TI)", "Gustavo Bastos (E-commerce)"]
problema: "efeito-externo-duplicado"
viola: [RULE-006, "[EMISSAO-05]"]
corrigido_por: [PADRAO-001]
detectado_por: [PB-015, PB-017, "hub-logistico tests/suite_duplicidade.test.js"]
ocorreu_em:
  - "vault/systems/investigacao-duplicidade-etiquetas.md:27"
  - "vault/systems/investigacao-duplicidade-etiquetas.md:41"
sintoma: "Duas etiquetas J&T para o mesmo pacote e frete cobrado em dobro"
---
# ANTIPADRAO-001: Efeito externo sem consultar estado prévio nem registrar intenção

## O que é
Decidir criar algo num sistema externo olhando só o estado local, e chamar o sistema externo sem
registrar antes a intenção. Parece correto no caminho feliz; quando o recurso já existe do outro
lado, ou a resposta se perde, o efeito se repete.

## Onde ocorreu
Hub Logístico, incidente analisado em 07/10/2026
([[investigacao-duplicidade-etiquetas]]):
- O adaptador do Bling ignorava rastreios já existentes no pedido
  (`vault/systems/investigacao-duplicidade-etiquetas.md:27`).
- O motor emitia etiqueta J&T sempre que o rastreio local estava vazio e depois sobrescrevia o
  rastreio no Bling (`vault/systems/investigacao-duplicidade-etiquetas.md:41`).
Impacto: etiquetas duplicadas no CD e frete cobrado em dobro.

## Como detectar
- [[PB-015-emissao-sem-race-condition]] (teste) e a suíte de duplicidade do hub-logistico
  (`tests/suite_duplicidade.test.js`, primeiro passo de `npm test`).
- [[PB-017-reconciliacao-emissao-uncertain]] (runbook) para os casos incertos.

## Correção
[[PADRAO-001-intencao-duravel-antes-de-efeito-externo]]: intenção em `jt_emissions` antes da
chamada, reutilização de rastreio existente e revisão humana para resultado incerto
([[RULE-006-intencao-jt-uncertain-bloqueia-reemissao]]).

## Referências
- [[ADR-043-modelo-de-governanca-tipos-e-relacoes]]
- [[ADR-027-recuperacao-logistica-bling-com-intencao-duravel]]
