---
type: adr
status: Aceito
date: 2026-10-07
---
# ADR-003: Política Mandatória de Git Workflow, Proteção da Branch Main e Pull Requests

## Contexto
Após o versionamento e backup do Hub Logístico no GitHub privado (`userTI10/hub-logistico`), foi estabelecido o fluxo de trabalho de desenvolvimento para a equipe técnica da KIOSK Brands.

O push direto para a branch `main` representa risco operacional para ambientes integrados com ERPs (Bling) e Transportadoras (J&T Express), pois impede a revisão de código, validação de testes automatizados e histórico claro de auditoria para cada alteração.

## Decisão
Fica terminantemente **proibido o push direto para a branch `main` ou `master`** em qualquer circunstância em todos os repositórios da organização.

### Fluxo Obrigatório de Engenharia:
1. **Branch Dedicada:**
   - Todo trabalho (correção de bugs, refatorações, novas funcionalidades) deve iniciar com a criação de uma branch temática (`fix/*`, `feature/*`, `test/*`, `chore/*`).
2. **Push da Branch:**
   - Os commits devem ser enviados exclusivamente para a branch remota correspondente.
3. **Abertura Obrigatória de Pull Request (PR):**
   - Nenhuma alteração é mesclada na `main` sem uma Pull Request formal.
   - O corpo da PR deve conter obrigatoriamente:
     - **Causa Raiz do Erro:** Explicação técnica do motivo da falha.
     - **Correção Realizada:** Relação dos arquivos e métodos modificados.
     - **Evidências e Testes:** Provas de reprodução antes do fix e logs de aprovação de testes automatizados após o fix.

## Aplicação Técnica
- Configurado nas Regras Globais do Antigravity em `~/.gemini/config/GEMINI.md` e `~/.gemini/config/rules/git_workflow.md`.
- Configurado localmente no repositório em `hub-logistico/GEMINI.md`.
- Validado na prática na Pull Request #1 (`fix/duplicidade-etiquetas-jt` -> `main`).
