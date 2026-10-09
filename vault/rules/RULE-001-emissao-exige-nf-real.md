---
id: RULE-001
title: Toda nova emissão de etiqueta exige NF real
status: active
source: vault/systems/protecoes-processamento-emissao-hub.md:45
domain: logistica
---

# RULE-001: Toda nova emissão de etiqueta exige NF real

## Enunciado

Toda nova emissão exige NF com número positivo, série, chave de 44 dígitos não zerada e data de emissão válida. Falha na consulta da NF ou NF incompleta bloqueia a emissão antes de criar a intenção J&T. Rastreios já existentes continuam reutilizáveis mesmo com a consulta da NF indisponível.

## Origem

[[protecoes-processamento-emissao-hub]], seção Verificação e atualização do PR #13 com a auditoria fiscal de 08/10/2026 (linhas 45 e 61). A validação confere presença e formato; não presume autorização fiscal nem reconciliação histórica.

## Playbooks que a validam

PB-001 (suíte automatizada do Hub) e PB-002 (emissão bloqueada sem NF real). As execuções ficam no registro local e se consultam com `cli.py evidence RULE-001` ou pela ferramenta MCP `get_rule_evidence`.
