# Task 7 Brief — DEDUP-01: Consolidar Playbooks no JEV

## Objetivo
A rota `#page=playbooks` do Dashboard deve mostrar a experiência do JEV (PlaybooksView) ao invés do `playbooks-ui.js` proprietário. O `playbooks-ui.js` deve ser preservado (não deletado) mas não mais invocado.

## Allowed Files
- `dashboard/app.js` (seção de roteamento da página playbooks)

## No-Touch Files
- `dashboard/playbooks-ui.js` (preservar, não deletar — referência futura)
- `dashboard/core.js`
- `jev-app/src/**`

## Passos
1. Localizar em `app.js` onde `#page=playbooks` renderiza o conteúdo
2. Substituir a chamada ao `playbooks-ui.js` por um iframe apontando para a URL do JEV compilado (`jev/index.html`) com a aba Playbooks selecionada, ou por redirect para `#page=jev`
3. Adicionar fallback graceful caso o JEV não esteja disponível (mensagem de orientação)
4. Rodar testes: `cd dashboard; node --test` → 178 pass

## Critério de Aceite
- Navegar para `#page=playbooks` mostra a experiência do JEV
- Se JEV não carrega, mostra fallback amigável
- `playbooks-ui.js` continua existindo no filesystem
- Testes não regridem (178/178)
