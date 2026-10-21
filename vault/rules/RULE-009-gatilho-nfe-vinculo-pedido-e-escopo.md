---
id: RULE-009
title: Emissão por NF-e só inicia com vínculo confirmado, em lojas no escopo e em NF-e autorizada
status: active
source: vault/systems/hub-gatilho-nfe-e-politicas-de-emissao.md:22
domain: logistica
---

# RULE-009: Emissão por NF-e só inicia com vínculo confirmado, em lojas no escopo e em NF-e autorizada

## Enunciado

Só os eventos `invoice.created` e `invoice.updated` iniciam emissão; pedido atendido sozinho não inicia. O evento precisa de HMAC válido e a NF é gravada em `invoice_events` antes do 200. A NF é elegível com situação 5 ou 6, número, série, data de emissão e chave de 44 dígitos não zerada, e só NF-e entra (NFC-e não). O pedido é localizado por `numerosLojas[]` ou loja e contato, e o vínculo é confirmado por `pedido.notaFiscal.id`; vínculo ausente ou ambíguo bloqueia a emissão. A busca paginada tem limite de 20 páginas. A emissão ocorre só nas lojas 206264482, 206084387, 206085936 e 206288765 com `gerar_automatico` ativo, e só para pedidos nas situações 6, 9 e 748644, checadas na admissão e de novo pelo motor. NF de pedido diferente do `invoice_id` que disparou vai para `REVIEW_REQUIRED`.

## Origem

[[hub-gatilho-nfe-e-politicas-de-emissao]], seções Gatilho por NF-e (linhas 20 a 29) e Escopo (linhas 31 a 36), PR #30. Invariantes NFE-01 a NFE-08 em [[hub-regras-operacionais-codex]]. A regra de situação 9 para nova etiqueta (branch `fix/validar-pedido-nota-emissao`, linhas 38 a 42) ainda não foi integrada à `main` e fica fora desta regra até o merge.

## Playbooks que a validam

PB-019 (gatilho por NF-e e vínculo pedido-NF em homologação). A conferência por lote de chaves é a regra [[RULE-003-conferencia-nfe-obrigatoria]], validada por PB-014. As execuções ficam no registro local e se consultam com `cli.py evidence RULE-009` ou pela ferramenta MCP `get_rule_evidence`.

## Impacto

- **Time principal:** Logística (Hub).
- **Times dependentes:** Expedição (lojas e transportadora) e Bling (configuração de webhook e lojas).
- **Sistemas:** [[hub-producao]], [[hub-homologacao]], Bling (webhook `invoice.*`).
