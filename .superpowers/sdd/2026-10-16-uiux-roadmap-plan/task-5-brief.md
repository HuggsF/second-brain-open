# Task 5 Brief — CLEAN-04 + VISUAL-03: Unificar personas Agent Arena

## Objetivo
Renomear as personas genéricas do `agent-arena.js` para as 5 personas canônicas do Nexus: Maia (Orquestradora), Noah (Pesquisador), Theo (Desenvolvedor), Lia (Escritora), Eva (Revisora).

## Allowed Files
- `dashboard/agent-arena.js`

## No-Touch Files
- `dashboard/app.js`
- `dashboard/core.js`
- `dashboard/DESIGN.md`
- `nexus/src/simulation.mjs` (fonte-de-verdade das personas — apenas leitura)

## Referência: Personas Canônicas (de simulation.mjs)
```
Maia — Orquestradora — Cor: #00f0ff
Noah — Pesquisador — Cor: #ff007f
Theo — Desenvolvedor — Cor: #b8f37b
Lia  — Escritora — Cor: #ffc107
Eva  — Revisora — Cor: #7c4dff
```

## Passos
1. Ler `nexus/src/simulation.mjs` para extrair nomes, roles e cores canônicas
2. Identificar as personas genéricas em `agent-arena.js` (pesquisador, arquiteto, dev, qa, devops, documentador)
3. Mapear: pesquisador→Noah, arquiteto→Maia, dev→Theo, qa→Eva, devops→Theo(secundário), documentador→Lia
4. Renomear mantendo a estrutura do código
5. Atualizar cores para as canônicas
6. Rodar testes: `cd dashboard; node --test` → 178 pass

## Critério de Aceite
- `grep -c "Maia\|Noah\|Theo\|Lia\|Eva" dashboard/agent-arena.js` ≥ 5
- Personas genéricas não aparecem mais como nomes de display
- Testes Dashboard não regridem (178/178)
