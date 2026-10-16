# Task 2 Brief — CLEAN-03: Arquivar módulo Phaser

## Objetivo
Mover o diretório `nexus/src/game/` para `nexus/src/_archived_game/` preservando o histórico para referência futura.

## Allowed Files
- `nexus/src/game/*` (mover, não deletar)
- `nexus/src/_archived_game/*` (destino)

## No-Touch Files
- `nexus/src/components/**`
- `nexus/src/scene/**`
- `nexus/src/adapters/**`

## Passos
1. `cd c:\KIOSK\second-brain\nexus`
2. `git mv src/game src/_archived_game`
3. Verificar: `Test-Path src/game` → False
4. Verificar: `Test-Path src/_archived_game/OfficeScene.js` → True
5. Verificar: `node --test` → 82 pass (sem regressão)

## Critério de Aceite
- `nexus/src/game/` não existe
- `nexus/src/_archived_game/` contém `PhaserGame.jsx` e `OfficeScene.js`
- Testes não regridem
