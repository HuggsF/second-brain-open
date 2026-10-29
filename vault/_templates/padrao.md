---
type: padrao
id: PADRAO-NNN
title: "{Nome do padrão}"
status: active
date: "{YYYY-MM-DD}"
dono: ["{Nome (Área)}"]            # uma ou mais pessoas responsáveis
problema: "{slug-do-problema}"          # mesma chave usada pelos anti-padrões que este padrão corrige
adocao: "{aplicado | proposto}"         # aplicado = existe em código, com evidência em aplicado_em
aplicado_em: []                         # arquivo:linha, ADR ou commit; vazio quando proposto
---
# PADRAO-NNN: {Nome do padrão}

## Problema
{Forças em jogo e o que acontece sem o padrão.}

## Solução
{O que fazer, em passos curtos. Sem código copiado de curso (ADR-015).}

## Onde está aplicado
{Sistemas e evidência. Se `adocao: proposto`, dizer o que falta e o que o sistema usa hoje.}

## Anti-padrões que corrige
{[[ANTIPADRAO-NNN-...]] — a relação é declarada no anti-padrão (`corrigido_por`).}

## Referências
- [[ADR-043-modelo-de-governanca-tipos-e-relacoes]]
