---
etapa: construcao
data: 2026-11-23
veredito: verde
criterio: "A suíte de testes passa."
evidencia: fichas/second-brain-open/06-auditorias/evidencias/2026-11-23b-pytest.txt
---
# Auditoria de construção, 2026-11-23, segunda do dia

## Critério

A suíte de testes passa.

## O que foi feito

A [primeira auditoria do dia](2026-11-23-construcao.md) ficou âmbar porque 92 testes assíncronos não
rodavam: faltava o `pytest-asyncio` em `requirements.txt`. A dependência foi declarada, instalada, e a
suíte foi rodada de novo com `python -m pytest -q`, Python 3.14.3. A saída inteira está na evidência; o
caminho da pasta do repositório foi trocado por `.` e nada mais foi alterado.

## Resultado

Verde: 1037 testes passam e nenhum falha. Os 92 que não rodavam agora rodam e passam, sem mudança no
código que eles testam.

## O que esta auditoria não cobre

A suíte roda sem o banco vetorial e sem o servidor de modelos. Busca e respostas de ponta a ponta
(`cli.py sync` e `ask`) não são exercitadas aqui.
