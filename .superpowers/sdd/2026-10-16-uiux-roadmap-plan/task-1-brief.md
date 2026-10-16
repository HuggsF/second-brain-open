# Task 1 Brief — CLEAN-01/02: Remover Phaser e Zustand

## Objetivo
Remover as dependências `phaser` e `zustand` do `package.json` do Nexus. Ambas são órfãs (nenhum import ativo no código).

## Allowed Files
- `nexus/package.json`
- `nexus/package-lock.json` (gerado automaticamente)

## No-Touch Files
- `nexus/src/**` (nenhuma alteração de código)

## Passos
1. `cd c:\KIOSK\second-brain\nexus`
2. `npm uninstall phaser zustand`
3. Verificar: `npm ls phaser` → "empty"
4. Verificar: `npm ls zustand` → "empty"
5. Verificar: `node --test` → 82 pass, 2 fail (pré-existentes)

## Critério de Aceite
- `phaser` e `zustand` não aparecem em `package.json` (nem `dependencies` nem `devDependencies`)
- `npm install` roda sem erros
- Testes não regridem (82/84)
