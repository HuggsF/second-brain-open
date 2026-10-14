---
type: adr
scope: second-brain
status: Aceito
date: 2026-10-14
related: [ADR-012, ADR-015, ADR-017, ADR-018]
---
# ADR-021: Escopo do Second Brain: conhecimento, observabilidade e plataforma multiagente

> Esta ADR trata do próprio repositório `second-brain`, não do Hub Logístico.

## Contexto
Entre 13 e 14/10 o repositório recebeu, além do núcleo de conhecimento, funcionalidades do produto Hub Logístico: conectores Bling v3, J&T Express e Corpem WMS, um módulo de analytics de vendas e fulfillment, wireframes e design system do front-end do Hub e uma análise de engenharia reversa da documentação pública da UserIn. O dono do projeto definiu que isso não pertence ao Second Brain: aqui entram o conhecimento, a observabilidade (relatórios e painel) e a plataforma multiagente. O projeto `crm_hggs` é só referência de padrões, e nenhum conteúdo dele deve ser copiado para este repositório.

## Alternativas Consideradas
- **Manter tudo no mesmo repositório:** descartada. Mistura código de produto do Hub, que tem ciclo de entrega e dono próprios, com a base de conhecimento, e o `CLAUDE.md` já declara o Hub como repositório separado e somente leitura.
- **Mover o código do Hub para o repositório do Hub nesta mudança:** descartada. O Hub é somente leitura a partir daqui. O material sai deste repositório e fica preservado na tag `archive/hub-fora-do-escopo`; quem cuida do Hub decide como incorporá-lo.
- **Apagar o histórico:** descartada. A remoção é um commit; o conteúdo continua recuperável pela tag.

## Decisão
1. **Dentro do escopo:** (a) conhecimento: vault, recuperação, ADRs, regras e playbooks; (b) evidência e rastreio: `trace_id`, execuções registradas; (c) observabilidade: painel e relatórios sobre os sistemas observados, em modo somente leitura; (d) plataforma multiagente: orquestração, ferramentas, aprovação humana e portões (gates).
2. **Fora do escopo:** funcionalidades de produto do Hub (conectores, analytics de vendas e fulfillment, wireframes e design system do front-end do Hub) e documentação de produto externa. **Conhecimento sobre o Hub continua aqui**: notas de sistema, regras, playbooks e evidências. A política é "conhecimento sobre o Hub fica; código e produto do Hub saem".
3. O material removido nesta mudança (`hub-connectors/`, `dashboard/hub-wireframes-kit.html`, as notas `architecture/analytics-vendas-bling-hub`, `architecture/padrao-conector-integracoes-hub`, `architecture/wireframes-agnosticos-hub-logistico`, `architecture/hub-design-system-agnostico.css` e `architecture/blueprint-documentacao-mintlify-userin`) fica acessível na tag `archive/hub-fora-do-escopo`, que aponta para o último commit que o continha.
4. **Nuvem:** o dono autoriza o envio de dados do vault a provedores de nuvem. Continuam valendo a restrição do ADR-018 a provedores sem retenção nem treino e a guarda de dados sensíveis (tokens, chaves privadas, CPF e chave de NF), que é uma proteção de segurança e não de privacidade: segredos não vão ao log, ao registro de evidências nem à nuvem.
5. **Projetos de referência** (`crm_hggs`, UserIn) orientam padrões de UX e de documentação; não se copia o conteúdo deles para o vault nem para o código.
6. O desenho da plataforma multiagente é descrito em spec própria e só vira implementação depois da aprovação do dono.

## Consequências
- O dashboard perde a página "Wireframes Hub". O snapshot do grafo é regenerado sem as notas removidas.
- A ADR-016 e o ADR-018 não foram editadas; esta ADR registra a decisão nova.
- Cabe ao dono do Hub decidir se recupera os conectores e o módulo de analytics a partir da tag.
- Notas sobre o Hub que descrevem funcionalidades futuras de produto devem ir para o repositório do Hub, não para o vault do Second Brain.
