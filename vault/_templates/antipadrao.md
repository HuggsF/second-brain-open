---
type: antipadrao
id: ANTIPADRAO-NNN
title: "{Nome do anti-padrão}"
status: active
date: "{YYYY-MM-DD}"
dono: ["{Nome (Área)}"]            # uma ou mais pessoas responsáveis
problema: "{slug-do-problema}"     # mesma chave do padrão que o corrige
viola: []                          # RULE-NNN ou [CODIGO] do registro do repositório
corrigido_por: []                  # PADRAO-NNN; vazio = sem correção definida
detectado_por: []                  # teste, check ou PB-NNN; vazio = lacuna de prevenção
ocorreu_em: []                     # obrigatório: arquivo:linha, commit ou incidente observado na KIOSK
sintoma: "{o que se vê em produção}"
---
# ANTIPADRAO-NNN: {Nome do anti-padrão}

## O que é
{A solução que parece funcionar e o preço que ela cobra depois.}

## Onde ocorreu
{Incidente, data, sistema e impacto, com citação `caminho:linha`. Só entra anti-padrão observado.}

## Como detectar
{Teste, check ou playbook. Se não houver, dizer explicitamente que é lacuna.}

## Correção
{O padrão que corrige e o que foi feito no sistema.}

## Referências
- [[ADR-043-modelo-de-governanca-tipos-e-relacoes]]
