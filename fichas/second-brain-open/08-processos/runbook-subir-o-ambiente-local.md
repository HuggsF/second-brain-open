---
tipo: runbook
dono: mantenedor
revisado_em: 2026-11-23
---
# Subir o ambiente local e rodar a suíte

## Quando usar

Na primeira instalação, e antes de registrar uma auditoria de construção.

## Passos

1. Criar o ambiente: `python -m venv .venv` e `.venv/Scripts/python -m pip install -r requirements.txt`.
2. Só para busca e respostas: `docker compose up -d` (banco vetorial e servidor de modelos).
3. Rodar a suíte: `.venv/Scripts/python -m pytest -q`.
4. Validar as fichas: `.venv/Scripts/python cli.py ficha validar`.

## Como saber que deu certo

- O passo 4 sai com código 0.
- O passo 3 não mostra falha nova em relação à última auditoria de construção. As falhas já conhecidas
  estão listadas na evidência dessa auditoria.
