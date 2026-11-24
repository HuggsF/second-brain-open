---
tipo: runbook
dono: mantenedor
revisado_em: 2026-11-24
---
# Subir o ambiente local e rodar a suíte

## Quando usar

Na primeira instalação, e antes de registrar uma auditoria de construção.

## Passos

1. Criar o ambiente: `python -m venv .venv` e `.venv/Scripts/python -m pip install -r requirements.txt`.
2. Apontar o vault: variável `BRAIN_VAULT_DIR` (o repositório não traz um). Depois, `cli.py sync` e
   `cli.py buscar "uma pergunta"`. Nenhum serviço é necessário.
3. Rodar a suíte: `.venv/Scripts/python -m pytest -q`.
4. Validar as fichas: `.venv/Scripts/python cli.py ficha validar`.
5. Conferir o orçamento: `.venv/Scripts/python cli.py budget`. Se o estado for `esgotado`, nenhuma chamada vai
   à nuvem até o dia ou o mês virar, ou até o limite do perfil ser revisto. Se o banco de orçamento estiver
   ilegível, apague `.runtime/budget.db` e rode `cli.py budget --rebuild`. Isso recupera o gasto das tarefas,
   que fica no log de eventos; o gasto do `ask` não fica no log e se perde, então o período recomeça sem ele.

## Como saber que deu certo

- O passo 4 sai com código 0.
- O passo 3 termina sem falha. Se houver falha, registre uma auditoria de construção com a saída.
