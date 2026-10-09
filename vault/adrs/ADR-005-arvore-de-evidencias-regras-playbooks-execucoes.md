# ADR-005: Árvore de evidências: regras, playbooks e execuções registradas no Second Brain

> Esta ADR trata do próprio repositório `second-brain`, não do Hub Logístico.

## Status
Aprovado e implementado (2026-10-09)

## Data
2026-10-09

## Contexto
A análise 360 do Second Brain (perfil Piloto, 2026-10-09) apontou que as regras de negócio vivem em prosa nas notas e que os resultados de testes são narrados em texto, sem ligação formal entre regra, teste e execução (dimensões D01 e D07). Não era possível responder, com prova, "esta regra está sendo respeitada?". O passo 0 (ADR-004) já dá a cada chamada MCP um `trace_id`; faltava o modelo que liga uma regra ao que a verifica.

## Decisão
1. Duas camadas. **Definições estáticas, versionadas no git:** regras em `vault/rules/RULE-NNN-*.md` e playbooks em `vault/playbooks/PB-NNN-*.md`, notas Markdown com cabeçalho YAML (`id`, `title`, `status`, `source` ou `validates`, `environment`, `targets`). **Execuções dinâmicas:** linhas em `.runtime/evidence.db` (SQLite, WAL), porque crescem a cada teste e não devem reescrever arquivos versionados.
2. O Second Brain **só registra e liga**; não executa teste algum. Quem roda o teste (pessoa ou agente) informa o resultado pela ferramenta MCP `record_test_execution`.
3. Cada execução guarda resultado, ambiente, uma referência (`caminho:linha`, URL ou id de ticket), um resumo de até 500 caracteres e o `trace_id` da chamada que a registrou. **Nunca guarda o conteúdo de pedidos**; uma trava recusa tokens, CPF e chave de NF, e a mesma tabela mascara esses valores no log de rastreio.
4. Consulta: `list_rules`, `get_rule_evidence` (MCP) e `cli.py evidence [RULE_ID]`. `cli.py evidence --lint` reprova playbook sem regra, regra ativa sem playbook ativo e referência quebrada. Regra sem execução mostra "sem evidência ainda", nunca um "passou".
5. Dados iniciais reais, tirados de `protecoes-processamento-emissao-hub.md`: RULE-001 (emissão exige NF real), RULE-002 (homologação não chama ERP, J&T ou WMS), três playbooks e uma execução importada (26 cenários do `npm test`), marcada `imported`.
6. As notas do vault ficam em CRLF no disco (`.gitattributes`), porque o dashboard calcula hash byte a byte das notas.

## Alternativas descartadas
- **Tudo no catálogo visual (`graph-catalog.json`):** cada nó exige coordenadas e vistas, e o validador do dashboard rejeita nós sem documento e domínio; misturaria este passo com o mapa de topologia.
- **Neo4j agora:** grande demais para um piloto de um usuário. O modelo é o mesmo e pode migrar depois.

## Consequências
- A evidência é **auto-reportada** e o banco não é à prova de adulteração; `source` e `recorded_by` ficam visíveis. Separar utilizadores e agentes (identidade real) continua sendo trabalho de governança.
- Não há política de retenção das execuções.
- Regras e playbooks novos são escritos à mão; não há ferramenta de autoria.
- A execução importada é uma leitura de uma frase da nota, com data aproximada; o responsável confirma ou remove.
- Passos seguintes (mapa com semáforo e vista dos agentes) consomem este registro.
