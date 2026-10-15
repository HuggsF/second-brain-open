---
id: PD-OVR-002
date: 2026-10-15
status: APPROVED
decision: Unicode normaliza APENAS para injection scan, PII opera no original
context: DLP Guardrail precisa de normalização Unicode para detectar injection via homoglifos. Questão se PII masking também deve normalizar.
alternatives_considered:
  - A) Normalizar para injection scan E PII masking
  - B) Normalizar APENAS para injection scan, PII no original
  - C) Não normalizar (manter como está)
rationale: |
  Normalizar NFKC para PII poderia alterar:
  - Endereços com caracteres especiais
  - Nomes com acentos legítimos (José → Jose antes do match)
  - Formatos de documento que dependem de caracteres exatos
  O injection scan precisa de normalização porque atacantes usam homoglifos
  (Cyrillic а em vez de Latin a) e zero-width chars para evadir regex.
  O PII masking opera sobre texto real do usuário onde a formatação importa.
---

# PD-OVR-002: Unicode Normalization — Apenas Injection Scan

## Decisão
Normalizar Unicode (NFKC + strip zero-width chars) **apenas para o scan de injection** no DLP. O PII masking opera sobre o **texto original** (não normalizado), preservando a formatação real dos dados sensíveis.

## Contexto
A vulnerabilidade F-DLP-04 permite bypass do injection detector via homoglifos Unicode e zero-width characters. A normalização NFKC resolve isso, mas aplicá-la ao PII masking poderia alterar dados legítimos.

## Evidência
- `dlp_guardrail.py:178-188` — `_detect_injection()` roda regex no texto sem normalização (bug)
- `dlp_guardrail.py:190-213` — `_mask_pii()` usa `pattern.finditer(text)` no original
- Normalizar para PII alteraria `José` → `Jose`, comprometendo detecção de nomes reais
