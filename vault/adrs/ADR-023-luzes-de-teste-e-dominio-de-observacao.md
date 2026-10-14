---
type: adr
scope: second-brain
status: Aceito
date: 2026-10-14
related: [ADR-005, ADR-019, ADR-021, ADR-022]
---
# ADR-023: Luzes de teste e domínio de observação

> Esta ADR trata do próprio repositório `second-brain`, não do Hub Logístico.

## Contexto
A Fase 6 da plataforma (ADR-021) tinha de entregar o JEV (a tela de regras, playbooks e execuções) com a luz de cada regra. Havia quatro problemas:
- **Uma luz só, sem critério.** A luz de uma regra misturava "o teste passou" com "o sistema está saudável". Uma execução local de PB-001 bastava para pintar RULE-001 de verde, embora a regra exija a evidência de PB-002 em homologação.
- **Qualquer playbook contava.** Runbooks de operação (diagnóstico, rotação de credenciais) são procedimentos, não testes; não deviam aprovar nem reprovar uma regra.
- **A saúde observada vivia só em JavaScript.** A função `project()` de `dashboard/hub-topology.js` decide o estado de cada nó da topologia, mas o backend não podia usá-la, e portanto não podia comparar saúde com teste.
- **JEV em JavaScript sem teste de componente.** `dashboard/jev-ui.js` tinha rota errada de observação, `evidence_ref` obrigatório fora de um `<dialog>`, sem tratamento de playbook `retired`, e sem endpoint de regras.

## Alternativas Consideradas
- **Uma luz só, combinando teste e saúde:** descartada. Esconde o caso mais útil, a divergência: testes verdes com produção vermelha, ou o contrário. Duas luzes separadas tornam a divergência visível e acusável.
- **Contar todo playbook na luz da regra:** descartada. Runbooks não têm resultado de aprovação definido, e PB-003 é uma verificação manual em homologação: se contasse, RULE-002 ficaria sempre amarela por um passo que nenhum runner executa.
- **Reimplementar a projeção de saúde em Python sem conferência:** descartada. Dois códigos para a mesma regra divergem. O JavaScript continua sendo a fonte da verdade e o port Python é conferido contra um conjunto dourado gerado dele.
- **Migrar todo o dashboard para React nesta fase:** descartada. É uma frente própria; só o JEV foi reescrito.
- **Um segundo servidor (porta) para a API de playbooks:** descartada. Duas origens exigiriam CORS e duas verificações de sessão; as duas APIs passaram a responder na origem única do BFF.

## Decisão
1. **`Playbook.kind` e `ttl_hours`.** `kind` é `test` ou `runbook` (padrão `runbook`); `ttl_hours` é a validade de uma aprovação (padrão 168, faixa 1 a 8760). Só PB-001 e PB-002 são `kind: test`. PB-003 continua `runbook` porque é verificação manual em homologação, sem execução automática que a comprove. A evidência ganhou as colunas `commit_sha` e `run_id` (`ALTER TABLE ADD COLUMN`, tolerante a migração concorrente), e `EvidenceStore.latest` aceita `environment=None` para filtrar pelo ambiente.
2. **Regra de cor da luz de teste (`core/evidence.py: rule_light`).** Conta só playbooks ativos com `kind: test`. Precedência: vermelho, cinza, amarelo, verde.
   - **Vermelho:** a última execução geral, ou a última no ambiente do próprio playbook, é `fail` ou `error`.
   - **Cinza:** nenhum playbook contado tem execução (ou não há playbook de teste ativo).
   - **Amarelo:** algum playbook contado não tem execução, só tem `skipped` no próprio ambiente, tem aprovação vencida, só rodou em ambiente diferente do exigido (por exemplo só local onde se exige `hml`) ou tem data inválida.
   - **Verde:** todo playbook contado tem a última execução `pass` no próprio ambiente, dentro do TTL.
   `list_rules` devolve `light`, `light_reason`, `test_playbooks` e `test_environments` por regra. Com a semente, RULE-001 (PB-001 em `local` e PB-002 em `hml`) só fica verde com a aprovação de PB-002; RULE-002 (só PB-001 conta) fica verde com PB-001 local.
3. **Domínio de observação em `core/domain/observation/`.** Port de `project()` de `dashboard/hub-topology.js`, com `ServiceHealth`, `ObservationSnapshot` e `Contradiction`, só biblioteca padrão e sem E/S. Um conjunto dourado de 86 casos (`tests/fixtures/observation_golden.json`), gerado do próprio JavaScript por `scripts/generate_observation_golden.js`, prende ids, ordem, estados e textos. Diferenças deliberadas: ambiente inválido levanta `ValueError` (no JS, `RangeError`), e qualquer exceção inesperada degrada o snapshot para desconhecido.
4. **Contradição = luz de teste verde + saúde vermelha no mesmo ambiente.** `detect_contradictions` só emite quando a luz da regra é verde, o ambiente observado (`production` ou `hml`) está vermelho e esse ambiente é um dos `test_environments` da regra. Uma regra cujo único playbook de teste é local nunca contradiz.
5. **Uma origem para as duas APIs.** `backend/server.py` serve `/api/playbooks*` (`backend/playbooks_api.py`), `/api/rules` e `/v1/observability/assessment` (`backend/assessment.py`) atrás da verificação de sessão e de origem. Corpo inválido devolve 400 `INVALID_JSON`; exceção não prevista, 500 `INTERNAL` com `request_id`; banco indisponível, 503 com `detail` fixo. O assessment responde mesmo sem o banco de evidência, com `rules_available: false` e sem contradições: a saúde observada não depende da evidência.
6. **JEV em React.** `jev-app/` usa React 19.3.0, Tailwind 4.3.3 e Vite 8.3.4, com versões exatas. O build vai para `dashboard/jev/` e é commitado. O dashboard o embute por `iframe` de mesma origem, a partir de `dashboard/app.js`, e o tema é sincronizado do dashboard. A CSP `frame-ancestors 'self'` vale só para `dashboard/jev/` (no BFF e em `dashboard/serve.py`); o resto continua com `'none'`. O registro de execução usa `<dialog>` (o portão `modal_semantics` passou a verde). A tela mostra as duas luzes separadas.
7. **O que saiu de `dashboard/jev-ui.js`, removido, e não foi portado:** o grafo de topologia em SVG, o painel de métricas brutas, a extração de variáveis Liquid não declaradas, a renderização em markdown da prévia e a leitura de contingência em SQLite.

## Consequências
- `dashboard/liquid-engine.js` ficou sem uso, mas continua carregado por `dashboard/index.html`; remover é follow-up.
- O resto do dashboard continua em JavaScript puro; migrá-lo é uma frente própria.
- O build de `jev-app/` é commitado e precisa ser refeito após qualquer mudança em `src/` (`cd jev-app && npm test && npm run build`); não há CI que acuse o esquecimento.
- Uma linha de execução com data inválida deixa o playbook amarelo, de forma conservadora, mesmo havendo aprovação válida mais antiga.
- Contradições só existem para ambientes `hml` e `production`; uma regra com playbook de teste só local não é conferida contra saúde alguma.
- A luz de teste e a saúde são auto-reportadas (ADR-005): provam que alguém registrou o resultado, não que ele é verdadeiro.
- O assessment relê as definições do vault a cada consulta (a cada poll da tela), sem cache.
- Os testes do `<dialog>` em jsdom usam um polyfill; o comportamento em navegador real (modal, foco, Esc) foi conferido à mão.
- O portão `hardcoded_values` do dashboard continua vermelho (263 ocorrências contra o limite de 253).
- Ficam fora desta fase: alertas ativos (Teams e e-mail), luzes de outros sistemas além do Hub, relatórios (Fase 8) e o runner de testes (Fase 9).
