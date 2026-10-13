---
type: adr
status: Aceito
date: 2026-10-12
---
# ADR-009: Modelo de Maturidade de IA em 5 Dimensões e AI Readiness da KIOSK Brands

## Contexto
A KIOSK Brands opera um ecossistema de IA crescente (Second Brain, 9 squads autônomos, integrações de ERP e automações logísticas) sem um **framework formal para medir e evoluir o nível de maturidade organizacional em IA**. Decisões sobre investimento em infraestrutura, contratação de capacidades, governança ética e adoção de ferramentas eram feitas de forma reativa e sem uma métrica comparável ao longo do tempo.

A formação **AI Product Specialist** (Juliana Araújo — *"Modelos de Maturidade e Readiness de IA"* e *"Guardrails, Segurança e Proteção do Usuário na prática"*) forneceu um modelo estruturado em 5 dimensões para avaliar a prontidão da organização.

### Problemas Enfrentados
- Sem diagnóstico formal de AI Readiness, era impossível responder à pergunta "estamos prontos para escalar a IA para as 3 holdings simultaneamente?".
- Investimentos em infraestrutura de dados (Qdrant, Redis, embeddings) não tinham priorização comparativa com investimentos em governança (Guardrails, NeMo) ou cultura (treinamento de operadores).
- Ausência de um roadmap de evolução que conectasse o nível atual ao próximo nível desejado, com critérios de aceitação objetivos.
- Risco de operar IA com responsabilidade insuficiente em dimensões menos visíveis (ex: ética, compliance com LGPD) enquanto a dimensão técnica avançava.

## Alternativas Consideradas

### Opção A: Avaliação Ad-Hoc por Projeto
- **Prós:** Simples, sem overhead.
- **Contras:** Sem comparabilidade temporal. Impossível medir evolução. Não revela gaps ocultos.

### Opção B: Adotar o Modelo de 5 Dimensões de AI Readiness (Escolhida)
- **Prós:** Framework holístico cobrindo tecnologia, negócio, cultura e ética simultaneamente. Escala de 1 a 5 permite medir evolução trimestral. Cada dimensão tem critérios de aceitação verificáveis. Compatível com frameworks de mercado (Gartner AI Maturity, Microsoft AI Readiness).
- **Contras:** Exige reavaliação trimestral disciplinada. Dimensão "Cultura & Pessoas" é mais difícil de mensurar objetivamente.

## Decisão
Adotar o **Modelo de Maturidade de IA em 5 Dimensões** como instrumento formal de avaliação trimestral da KIOSK Brands, com **classificação atual, meta de curto prazo e critérios de aceitação** documentados para cada dimensão.

### As 5 Dimensões e Diagnóstico Atual

#### Dimensão 1: Estratégia & Negócio (Nível 3.8/5 — Sistêmico)
- **Estado Atual:** Radar de Demandas com RICE Score cobrindo 17 frentes, 5 declarações HMW formalizadas, NSM definida.
- **Meta (Nível 4 — Otimizado):** Previsão ativa de demandas e recomendação proativa de novas iniciativas usando dados de telemetria.
- **Critério de Aceitação:** Integração do Radar de Demandas aos OKRs trimestrais das holdings com atualização automática de progresso.

#### Dimensão 2: Dados & Infraestrutura (Nível 4.2/5 — Otimizado)
- **Estado Atual:** Vault local sincronizado com Google Drive (23 docs), GraphRAG em memória com 93 fontes, ingestão incremental com SHA-256 e manifest JSON.
- **Meta (Nível 4.5):** Pipeline contínuo com Qdrant vetorial, embeddings dimensionais e cache Redis para busca semântica em < 200ms.
- **Critério de Aceitação:** Benchmark de latência P95 de busca semântica < 200ms com Qdrant em produção.

#### Dimensão 3: Governança & Ética (Nível 4.5/5 — Otimizado)
- **Estado Atual:** 4 Linhas de Defesa implementadas (Sanitização, Action-Gates humanos, Jailbreak Evals no CI, Grounding Gate). Quarentena de Memória ativa. FlowLogger com `batch_trace_id`.
- **Meta (Nível 5 — Adaptativo):** Guardrails automatizados em tempo de inferência usando NeMo Guardrails ou Llama-Guard. LGPD Compliance Audit automatizado.
- **Critério de Aceitação:** 0% de bypass de Action-Gates e suíte de jailbreak no CI com pass-rate < 1%.

#### Dimensão 4: Pessoas & Cultura (Nível 3.5/5 — Sistêmico)
- **Estado Atual:** Liderança Full-Cycle (Hugo Melo) operando com assistência do Second Brain e 9 squads autônomos.
- **Meta (Nível 4 — Otimizado):** Democratização do acesso guiado para operadores das 3 holdings (Touti, Amavia, Yes!) para autoatendimento de dúvidas fiscais e logísticas.
- **Critério de Aceitação:** >= 3 operadores usando o copiloto para autoatendimento sem escalonamento para TI.

#### Dimensão 5: Operações — LLMOps & Evals (Nível 4.0/5 — Otimizado)
- **Estado Atual:** Testes unitários com pytest (9 testes passando), mocks isolados, FlowLogger visual no terminal, Golden Dataset com 150 questões de score humano.
- **Meta (Nível 4.5):** Observabilidade contínua com Langfuse/OpenTelemetry, Golden Dataset Evals integrados ao CI/CD com blocking de regressão, TTFT monitorado em produção.
- **Critério de Aceitação:** Pipeline de CI rodando benchmark automaticamente a cada push com bloqueio se score < 93.0.

### Cadência de Reavaliação
- **Frequência:** Trimestral (alinhado ao ciclo de OKRs da KIOSK Brands).
- **Responsável:** Hugo Melo (Product & Tech Lead).
- **Armazenamento:** Snapshot de cada avaliação no Vault em `vault/product/ai-readiness-snapshots/`.
- **Visualização:** Painel interativo no Dashboard do Second Brain na página "Produto & OKRs".

## Consequências

### Positivas
- Visibilidade holística: a holding sabe exatamente onde está avançada (Governança: 4.5/5) e onde precisa investir (Cultura: 3.5/5).
- Roadmap de evolução com critérios objetivos verificáveis, eliminando debates subjetivos sobre "estamos prontos?".
- Compliance proativo: a dimensão de Governança & Ética é tratada com a mesma prioridade que a dimensão técnica, prevenindo riscos regulatórios (LGPD).
- Compatível com auditorias externas e certificações de IA responsável.

### Desafios / Riscos
- A dimensão "Pessoas & Cultura" é inerentemente mais difícil de pontuar objetivamente — mitigar usando proxies quantificáveis (# de operadores usando autoatendimento, # de escalações evitadas).
- Risco de "gaming" da métrica: equipes otimizando para a pontuação em vez de para o impacto real — mitigar vinculando os critérios de aceitação a outcomes reais (MTTR, FCR, ROI).
- Requer disciplina na cadência trimestral; se não avaliada regularmente, o modelo perde valor.

## Times Impactados
- **Engenharia Full-Cycle (Hugo Melo):** Responsável pela avaliação trimestral e pelo roadmap de evolução.
- **Todos os 9 Squads Autônomos:** Cada squad contribui para a evolução de pelo menos uma dimensão (ex: Squad de Knowledge contribui para Dados & Infra).
- **Stakeholders Executivos (Tadeu, Davi):** Consumidores do painel de AI Readiness para decisões de investimento.
- **Operações (Touti, Amavia, Yes!):** Diretamente impactados pela evolução da dimensão 4 (Democratização do Acesso).

## Referências
- [[references/17-modelos-de-maturidade-e-readiness-de-ia-juliana-araujo]]
- [[references/16-guardrails-seguranca-e-protecao-do-usuario-na-pratica-juliana-araujo]]
- [[product/product-vision-ai-specialist]] — Seção 8 (Modelo de Maturidade & AI Readiness)
- [[ADR-007-hierarquia-metricas-l1-l2-framework-hhh-ragas]] — Métricas L2 alimentam a dimensão 5 (LLMOps)
