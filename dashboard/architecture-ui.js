/* Architecture & System Design page: 30 Modules, 6 Pillars, 4 Specialist Agents & 29 Intelligence Chunks. */
(function () {
'use strict';

const PILLARS = [
  {
    id: 'pillar-1',
    icon: '🌐',
    title: 'Eixo 1: Redes, Gateways & Comunicação',
    tag: 'DEV + DEVOPS',
    doc: 'architecture/system-design/01-redes-gateways-comunicacao.md',
    intelDoc: 'architecture/system-design/inteligencia-time-devops.md',
    description: 'Protocolos de transporte e aplicação (OSI, TCP/UDP, TLS, HTTP/1-2-3), Load Balancers L4/L7 (Envoy), API Gateways (Kong), Rate Limiting (Token/Leaky Bucket), BFF Pattern e Service Mesh com eBPF/ZTunnel.',
    topics: ['Camadas OSI & RTT', 'Load Balancers & Proxies Reversos', 'Kong & Rate Limiting', 'BFF & API Composition', 'Service Mesh (Istio / eBPF)', 'REST vs gRPC vs Webhooks']
  },
  {
    id: 'pillar-2',
    icon: '💾',
    title: 'Eixo 2: Persistência, Storage & Consistência',
    tag: 'DEV + ARQUITETURA',
    doc: 'architecture/system-design/02-persistencia-storage-consistencia.md',
    intelDoc: 'architecture/system-design/inteligencia-time-arquitetura.md',
    description: 'Desempenho de I/O (IOPS, Throughput, NVMe), Teorema CAP & PACELC, modelos ACID vs BASE, B-Trees vs LSM-Trees, Caching (Cache-Aside, mitigação de Cache Stampede), Sharding e Consenso Raft/Paxos.',
    topics: ['IOPS & Throughput', 'Teorema CAP & PACELC', 'ACID vs BASE', 'B-Trees vs LSM-Trees', 'Cache-Aside & Thundering Herd', 'Consistent Hashing & Quorum']
  },
  {
    id: 'pillar-3',
    icon: '⚡',
    title: 'Eixo 3: Sistemas Distribuídos & Eventos',
    tag: 'DEV CORE',
    doc: 'architecture/system-design/03-sistemas-distribuidos-eventos-concorrencia.md',
    intelDoc: 'architecture/system-design/inteligencia-time-dev.md',
    description: 'Concorrência, Mutexes, Locks e Deadlocks, Mensageria e Streaming (Kafka, RabbitMQ, SQS, FIFO, DLQ), CQRS, Saga Pattern (Orquestrada com compensações), Transactional Outbox e Event Sourcing.',
    topics: ['Concorrência & Mutexes', 'Kafka & Streaming', 'CQRS & Projeções', 'Sagas & Compensações', 'Transactional Outbox', 'Event Sourcing & Snapshots']
  },
  {
    id: 'pillar-4',
    icon: '🛡️',
    title: 'Eixo 4: Resiliência, Escala & Confiabilidade',
    tag: 'DEVOPS + SRE',
    doc: 'architecture/system-design/04-resiliencia-confiabilidade-alta-escala.md',
    intelDoc: 'architecture/system-design/inteligencia-time-devops.md',
    description: 'Scale Cube (Eixos X, Y, Z), Circuit Breaker, Exponential Backoff com Full Jitter, Bulkheads lógicos e físicos, Cell-Based Architecture com Shuffle Sharding, Deploys Blue/Green e Canary, SPOFs e Disaster Recovery (RTO/RPO).',
    topics: ['Scale Cube (X, Y, Z)', 'Circuit Breaker & Cooldown', 'Bulkheads de Recursos', 'Cell-Based Architecture', 'Blue/Green & Canary', 'Disaster Recovery (RTO/RPO)']
  },
  {
    id: 'pillar-5',
    icon: '📊',
    title: 'Eixo 5: Capacidade, Testes de Carga & Observabilidade',
    tag: 'QA + DEVOPS',
    doc: 'architecture/system-design/05-capacidade-testes-carga-observabilidade.md',
    intelDoc: 'architecture/system-design/inteligencia-time-qa.md',
    description: 'Capacity Planning matemático com Lei de Little (L = λ × W), Knee Curve, Pirâmide de testes de carga (Smoke, Load, Stress, Spike, Breakpoint), Four Golden Signals, métodos USE/RED e gestão de SLA/SLO/SLI e Error Budgets.',
    topics: ['Lei de Little & Knee Curve', 'Pirâmide de Testes K6', 'Breakpoint Determination', 'Four Golden Signals', 'Métodos USE & RED', 'SLI/SLO & Error Budget']
  },
  {
    id: 'pillar-6',
    icon: '🎯',
    title: 'Eixo 6: Cases Reais & Estudos de Caso',
    tag: 'PRODUTO / ARQ',
    doc: 'architecture/system-design/06-cases-reais-estudos-de-caso.md',
    intelDoc: 'architecture/system-design/inteligencia-time-arquitetura.md',
    description: 'Estudos de caso aprofundados dissecados para a realidade KIOSK Brands: TinyURL (Base62/KGS), Busca em Catálogo (Elasticsearch), Checkout em Saga, Flash Sales com CDN, Telemetria Geoespacial (H3) e Core Banking DDD.',
    topics: ['Encurtador Base62 (KGS)', 'Busca Catálogo Elasticsearch', 'Checkout Distribuído em Saga', 'Flash Sales & CDN Borda', 'Telemetria Geoespacial H3', 'Core Banking com DDD']
  }
];

const AGENT_ALIGNMENTS = [
  {
    role: 'dev',
    avatar: '💻',
    name: 'Dev Full-Cycle',
    badge: 'Concorrência & Transações',
    doc: 'architecture/system-design/inteligencia-time-dev.md',
    principles: [
      'Idempotência Obrigatória via Idempotency-Key única em todo endpoint de escrita (eliminação de DEM-17).',
      'Padrão Transacional Outbox comitando evento no banco local antes do despacho de mensageria.',
      'Sagas Orquestradas com máquinas de estado e transações compensatórias em falhas remotas.',
      'CQRS em consultas de alto volume, mantendo modelos de escrita enxutos e ACID.'
    ],
    playbook: 'PB-006'
  },
  {
    role: 'devops',
    avatar: '🚀',
    name: 'DevOps & SRE',
    badge: 'Resiliência & Zero Downtime',
    doc: 'architecture/system-design/inteligencia-time-devops.md',
    principles: [
      'Circuit Breakers com tolerância de 50% de falha, cooldown de 30s e retries com Full Jitter.',
      'Bulkheads de conexão isolando pools de transportadoras para conter o Blast Radius.',
      'Estratégias de deploy Blue/Green e Canary com reversão instantânea em caso de erro.',
      'Four Golden Signals (Latência P95/P99, Tráfego, Erros, Saturação) monitorados em tempo real.'
    ],
    playbook: 'PB-004'
  },
  {
    role: 'qa',
    avatar: '🧪',
    name: 'QA & Confiabilidade',
    badge: 'Carga & Idempotência',
    doc: 'architecture/system-design/inteligencia-time-qa.md',
    principles: [
      'Pirâmide de Testes de Performance: Smoke -> Average Load -> Stress -> Spike -> Breakpoint.',
      'Testes de concorrência massiva enviando 50 payloads idênticos em paralelo para garantir Zero Duplicidade.',
      'Injeção de falhas e latência em homologação para certificar a abertura graciosa de Circuit Breakers.',
      'Auditoria de conformidade com os SLOs pactuados antes de aprovar deploys para produção.'
    ],
    playbook: 'PB-005'
  },
  {
    role: 'architecture',
    avatar: '🏛️',
    name: 'Produto & Arquitetura',
    badge: 'Trade-offs & Capacidade',
    doc: 'architecture/system-design/inteligencia-time-arquitetura.md',
    principles: [
      'Matriz formal de trade-offs CAP/PACELC em cada nova decisão técnica registrada no Vault.',
      'Modelagem matemática de capacidade guiada pela Lei de Little (L = λ × W) antes de expansão.',
      'Decomposição pelo Scale Cube (X: horizontal, Y: microsserviços, Z: particionamento por franqueado).',
      'Governança de Bounded Contexts (DDD) garantindo fronteiras limpas entre Touti, Amavia e Yes!.'
    ],
    playbook: 'PB-007'
  }
];

const PLAYBOOKS = [
  { id: 'PB-004', doc: 'playbooks/PB-004-resiliencia-circuit-breaker-retry-bulkhead.md', title: 'Protocolo de Resiliência: Circuit Breaker, Exponential Backoff e Bulkheads', badge: 'DEVOPS' },
  { id: 'PB-005', doc: 'playbooks/PB-005-testes-de-carga-stress-breakpoint-qa.md', title: 'Protocolo de Testes de Carga, Estresse e Ponto de Ruptura (QA)', badge: 'QA' },
  { id: 'PB-006', doc: 'playbooks/PB-006-transacoes-distribuidas-saga-outbox.md', title: 'Orquestração de Sagas e Padrão Transacional Outbox (Idempotência)', badge: 'DEV' },
  { id: 'PB-007', doc: 'playbooks/PB-007-disaster-recovery-spof-avaliacao-rto-rpo.md', title: 'Auditoria de SPOFs e Plano de Disaster Recovery (RTO / RPO)', badge: 'SRE / ARQ' }
];

function render(main, U) {
  const { el, button, badge, head, panelTitle, notify, openDoc, copy } = U;
  const manifest = window.SYSTEM_DESIGN_MANIFEST || null;
  const chunks = window.SYSTEM_DESIGN_CHUNKS || [];

  main.append(head(
    'ARQUITETURA & SYSTEM DESIGN / KIOSK BRANDS',
    'Inteligência dos 29 Módulos Principais (Days 0 a 28)',
    'Formação Descomplicando System Design (254 aulas, 42.7h) convertida em chunks de ensinamentos acionáveis para os 4 Agentes Especialistas: DEV, DEVOPS, QA e ARQUITETURA.',
    [
      button('📄 Abrir Índice Mestre', () => openDoc('architecture/system-design-index.md'), 'primary'),
      button('📜 Ver ADR-012', () => openDoc('adrs/ADR-012-padroes-arquiteturais-system-design-para-agentes-especialistas.md'), 'subtle'),
      button('🧠 Ir para Chunks dos Times', () => {
        document.getElementById('chunks-intelligence-section')?.scrollIntoView({ behavior: 'smooth' });
      }, 'subtle')
    ]
  ));

  // --- 1. BANNER HERO ---
  const hero = el('section', { class: 'panel', style: 'border-left: 4px solid var(--accent); margin-bottom: 24px; background: linear-gradient(135deg, rgba(184,243,123,0.08), rgba(184,243,123,0.01));' },
    el('div', { style: 'display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;' },
      el('div', { style: 'display: flex; align-items: center; gap: 12px;' },
        badge('🏛️ ENGENHARIA DE ALTA ESCALA', 'accent'),
        el('strong', { style: 'font-size: 16px;' }, 'Descomplicando System Design ➔ Inteligência dos Times')
      ),
      el('div', { style: 'display: flex; gap: 8px;' },
        badge('29 Chunks Ativos', 'good'),
        badge('ADR-012 Aceita', 'violet')
      )
    ),
    el('p', { class: 'small', style: 'margin: 12px 0 0; line-height: 1.6; color: var(--text);' },
      'Os ensinamentos do conteúdo principal (Days 0 a 28) foram decompostos em chunks de conhecimento contendo Ensinamento Central, Regras de Ouro, Anti-Patterns e Aplicação Direta no ecossistema KIOSK Brands (Hub, Bling v3, Touti, SAP, Salesforce).'
    )
  );
  main.append(hero);

  // --- 2. STATS ---
  const stats = el('div', { class: 'stats', style: 'margin-bottom: 24px;' },
    el('div', { class: 'panel stat' },
      el('div', { class: 'stat-value' }, chunks.length || '29'),
      el('div', { class: 'stat-title' }, 'Chunks de Inteligência'),
      el('div', { class: 'stat-foot' }, 'Days 0 a 28 mapeados')
    ),
    el('div', { class: 'panel stat' },
      el('div', { class: 'stat-value' }, manifest ? manifest.lesson_count : '254'),
      el('div', { class: 'stat-title' }, 'Aulas Indexadas'),
      el('div', { class: 'stat-foot' }, '42.72 horas de conteúdo')
    ),
    el('div', { class: 'panel stat' },
      el('div', { class: 'stat-value' }, '4'),
      el('div', { class: 'stat-title' }, 'Bases dos Agentes'),
      el('div', { class: 'stat-foot' }, 'Guias de inteligência no Vault')
    ),
    el('div', { class: 'panel stat' },
      el('div', { class: 'stat-value' }, '4'),
      el('div', { class: 'stat-title' }, 'Novos Playbooks'),
      el('div', { class: 'stat-foot' }, 'PB-004 a PB-007 ativas')
    )
  );
  main.append(stats);

  // --- 3. SEÇÃO PRINCIPAL: CHUNKS DE INTELIGÊNCIA DOS TIMES (DAYS 0 A 28) ---
  const chunksSection = el('section', { id: 'chunks-intelligence-section', style: 'margin-bottom: 34px;' },
    panelTitle('🧠 Central de Inteligência dos Times (29 Chunks dos Dias 0 a 28)', 'Ensinamentos práticos, regras de ouro e anti-patterns prontos para consumo dos agentes')
  );
  main.append(chunksSection);

  // Filter Tabs
  let activeTeam = 'all';
  let searchText = '';

  const teamCounts = {
    all: chunks.length,
    dev: chunks.filter(c => c.team === 'dev').length,
    devops: chunks.filter(c => c.team === 'devops').length,
    qa: chunks.filter(c => c.team === 'qa').length,
    architecture: chunks.filter(c => c.team === 'architecture').length,
  };

  const tabsBar = el('div', { style: 'display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px;' });
  const tabs = [
    { id: 'all', label: `Todos os Chunks (${teamCounts.all})`, icon: '📚' },
    { id: 'dev', label: `Time DEV (${teamCounts.dev})`, icon: '💻' },
    { id: 'devops', label: `Time DEVOPS (${teamCounts.devops})`, icon: '🚀' },
    { id: 'qa', label: `Time QA (${teamCounts.qa})`, icon: '🧪' },
    { id: 'architecture', label: `Time ARQUITETURA (${teamCounts.architecture})`, icon: '🏛️' },
  ];

  const tabButtons = [];
  for (const t of tabs) {
    const btn = el('button', {
      type: 'button',
      class: t.id === 'all' ? 'primary' : 'subtle',
      style: 'font-size: 13px; padding: 6px 14px;',
      onclick: () => {
        activeTeam = t.id;
        for (const b of tabButtons) b.className = 'subtle';
        btn.className = 'primary';
        renderChunksList();
      }
    }, `${t.icon} ${t.label}`);
    tabButtons.push(btn);
    tabsBar.append(btn);
  }
  main.append(tabsBar);

  const searchInput = el('input', {
    type: 'search',
    placeholder: 'Filtrar chunks por conceito (ex: idempotência, outbox, saga, cap, little, cache, bulkhead, k6, redis)...',
    style: 'width: 100%; margin-bottom: 18px; padding: 10px 14px; border-radius: 6px; background: var(--panel); border: 1px solid rgba(255,255,255,0.1); color: var(--text);'
  });
  main.append(searchInput);

  const chunksContainer = el('div', { style: 'display: flex; flex-direction: column; gap: 14px; margin-bottom: 34px;' });
  main.append(chunksContainer);

  function renderChunksList() {
    chunksContainer.replaceChildren();
    const q = searchText.toLowerCase().trim();

    const filtered = chunks.filter(c => {
      if (activeTeam !== 'all' && c.team !== activeTeam) return false;
      if (!q) return true;
      const haystack = (c.day + ' ' + c.title + ' ' + c.core_teaching + ' ' + (c.golden_rules || []).join(' ') + ' ' + (c.anti_patterns || []).join(' ') + ' ' + c.kiosk_application).toLowerCase();
      return haystack.includes(q);
    });

    if (!filtered.length) {
      chunksContainer.append(el('div', { class: 'empty' },
        el('h3', {}, 'Nenhum chunk encontrado'),
        el('p', {}, 'Tente outro filtro ou termo de busca.')
      ));
      return;
    }

    for (const chunk of filtered) {
      const card = el('article', {
        class: 'panel',
        style: 'border-left: 3px solid var(--accent); padding: 18px 20px;'
      });

      // Header row
      const headRow = el('div', { style: 'display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin-bottom: 12px;' },
        el('div', { style: 'display: flex; align-items: center; gap: 10px;' },
          badge(chunk.day, 'blue'),
          badge(chunk.team_label, 'violet'),
          el('strong', { style: 'font-size: 15px;' }, chunk.title)
        ),
        el('div', { style: 'display: flex; gap: 6px;' },
          button('Copiar Chunk', () => {
            const txt = `[${chunk.day}] ${chunk.title}\n\nEnsinamento Central:\n${chunk.core_teaching}\n\nRegras de Ouro:\n- ${(chunk.golden_rules||[]).join('\n- ')}\n\nAnti-Patterns:\n- ${(chunk.anti_patterns||[]).join('\n- ')}\n\nAplicação KIOSK:\n${chunk.kiosk_application}`;
            copy(txt);
          }, 'subtle'),
          button('Ver Guia do Time →', () => {
            const intelMap = {
              dev: 'architecture/system-design/inteligencia-time-dev.md',
              devops: 'architecture/system-design/inteligencia-time-devops.md',
              qa: 'architecture/system-design/inteligencia-time-qa.md',
              architecture: 'architecture/system-design/inteligencia-time-arquitetura.md'
            };
            openDoc(intelMap[chunk.team] || 'architecture/system-design-index.md');
          }, 'subtle')
        )
      );
      card.append(headRow);

      // Core teaching
      const teachingP = el('p', { style: 'margin: 0 0 14px; line-height: 1.6; font-size: 14px; color: var(--text);' }, chunk.core_teaching);
      card.append(teachingP);

      // Grid for Rules & Anti-patterns
      const grid = el('div', { class: 'grid-2', style: 'margin-bottom: 14px; gap: 14px;' });

      // Golden rules box
      const rulesBox = el('div', { style: 'background: rgba(184,243,123,0.04); border: 1px solid rgba(184,243,123,0.15); border-radius: 6px; padding: 12px 14px;' },
        el('strong', { style: 'color: var(--accent); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 8px;' }, '⭐ Regras de Ouro'),
        el('ul', { style: 'margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.5; color: var(--text);' },
          ...chunk.golden_rules.map(r => el('li', { style: 'margin-bottom: 4px;' }, r))
        )
      );

      // Anti-patterns box
      const antiBox = el('div', { style: 'background: rgba(255,100,100,0.04); border: 1px solid rgba(255,100,100,0.15); border-radius: 6px; padding: 12px 14px;' },
        el('strong', { style: 'color: var(--warn); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 8px;' }, '⚠️ O que NUNCA Fazer (Anti-Patterns)'),
        el('ul', { style: 'margin: 0; padding-left: 18px; font-size: 13px; line-height: 1.5; color: var(--text);' },
          ...chunk.anti_patterns.map(a => el('li', { style: 'margin-bottom: 4px;' }, a))
        )
      );

      grid.append(rulesBox, antiBox);
      card.append(grid);

      // KIOSK Application footer
      const foot = el('div', { style: 'display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--muted); padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.04);' },
        el('strong', { style: 'color: var(--text);' }, 'Aplicação na KIOSK Brands:'),
        el('span', {}, chunk.kiosk_application)
      );
      card.append(foot);

      chunksContainer.append(card);
    }
  }

  searchInput.addEventListener('input', e => {
    searchText = e.target.value;
    renderChunksList();
  });
  renderChunksList();

  // --- 4. OS 4 AGENTES ESPECIALISTAS & SUAS BASES DE INTELIGÊNCIA ---
  main.append(el('div', { style: 'margin-bottom: 14px;' },
    panelTitle('Bases de Inteligência dos 4 Agentes Especialistas', 'Documentos no Vault com diretrizes consolidadas para cada disciplina técnica')
  ));

  const agentsGrid = el('div', { class: 'grid-2', style: 'margin-bottom: 30px;' });
  for (const ag of AGENT_ALIGNMENTS) {
    const card = el('div', { class: 'panel', style: 'display: flex; flex-direction: column; justify-content: space-between;' },
      el('div', {},
        el('div', { style: 'display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;' },
          el('div', { style: 'display: flex; align-items: center; gap: 10px;' },
            el('span', { style: 'font-size: 22px;' }, ag.avatar),
            el('strong', {}, ag.name)
          ),
          badge(ag.badge, 'accent')
        ),
        el('ul', { style: 'padding-left: 18px; margin: 0 0 14px; font-size: 13px; line-height: 1.6; color: var(--text);' },
          ...ag.principles.map(p => el('li', { style: 'margin-bottom: 6px;' }, p))
        )
      ),
      el('div', { style: 'display: flex; justify-content: space-between; align-items: center; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 10px;' },
        button('Abrir Inteligência no Vault →', () => openDoc(ag.doc), 'primary'),
        button('Ver Playbook →', () => {
          const pb = PLAYBOOKS.find(p => p.id === ag.playbook);
          if (pb) openDoc(pb.doc);
        }, 'subtle')
      )
    );
    agentsGrid.append(card);
  }
  main.append(agentsGrid);

  // --- 5. OS 6 EIXOS ARQUITETURAIS ---
  main.append(el('div', { style: 'margin-bottom: 14px;' },
    panelTitle('Os 6 Eixos de System Design no Second Brain', 'Guias temáticos com a visão holística da engenharia distribuída')
  ));

  const pillarsGrid = el('div', { class: 'grid-2', style: 'margin-bottom: 30px;' });
  for (const pillar of PILLARS) {
    const card = el('div', { class: 'panel', style: 'display: flex; flex-direction: column; justify-content: space-between;' },
      el('div', {},
        el('div', { style: 'display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px;' },
          el('div', { style: 'display: flex; align-items: center; gap: 8px;' },
            el('span', { style: 'font-size: 20px;' }, pillar.icon),
            el('strong', { style: 'font-size: 15px;' }, pillar.title)
          ),
          badge(pillar.tag, 'blue')
        ),
        el('p', { class: 'small', style: 'line-height: 1.5; color: var(--muted); margin-bottom: 12px;' }, pillar.description),
        el('div', { style: 'display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px;' },
          ...pillar.topics.map(t => el('span', { class: 'pill', style: 'font-size: 11px;' }, t))
        )
      ),
      el('div', { style: 'display: flex; justify-content: flex-end;' },
        button('Ler Guia no Vault →', () => openDoc(pillar.doc), 'subtle')
      )
    );
    pillarsGrid.append(card);
  }
  main.append(pillarsGrid);

  // --- 6. SEÇÃO DE PLAYBOOKS OPERACIONAIS ---
  const pbSection = el('section', { id: 'playbooks-section', class: 'panel', style: 'margin-bottom: 30px;' },
    panelTitle('Novos Playbooks de Engenharia & Confiabilidade (PB-004 a PB-007)', 'Procedimentos operacionais padronizados no formato Gherkin / Checklist'),
    el('div', { style: 'display: flex; flex-direction: column; gap: 10px; margin-top: 14px;' },
      ...PLAYBOOKS.map(pb => el('div', {
        style: 'display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: rgba(255,255,255,0.02); border-radius: 6px; border: 1px solid rgba(255,255,255,0.05);'
      },
        el('div', { style: 'display: flex; align-items: center; gap: 12px;' },
          badge(pb.id, 'violet'),
          el('strong', { style: 'font-size: 14px;' }, pb.title)
        ),
        el('div', { style: 'display: flex; align-items: center; gap: 10px;' },
          badge(pb.badge, 'blue'),
          button('Abrir no Vault →', () => openDoc(pb.doc), 'subtle')
        )
      ))
    )
  );
  main.append(pbSection);

  // --- 7. EXPLORADOR INTERATIVO DOS 30 MÓDULOS (254 AULAS) ---
  const modulesHeader = el('div', { style: 'display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin-bottom: 14px;' },
    panelTitle('Catálogo Completo das 254 Aulas do Curso', 'Navegue pelos módulos com a minutagem exata de cada vídeo'),
    el('div', { class: 'result-count' }, manifest ? `${manifest.module_count} módulos · ${manifest.lesson_count} aulas · ${manifest.total_duration_hours}h` : '30 módulos')
  );
  main.append(modulesHeader);

  const filterInput = el('input', {
    type: 'search',
    placeholder: 'Filtrar aulas por tema ou título do vídeo...',
    style: 'width: 100%; margin-bottom: 16px; padding: 10px 14px; border-radius: 6px; background: var(--panel); border: 1px solid rgba(255,255,255,0.1); color: var(--text);'
  });
  main.append(filterInput);

  const modulesContainer = el('div', { style: 'display: flex; flex-direction: column; gap: 10px; margin-bottom: 40px;' });
  main.append(modulesContainer);

  function renderModules(filterText = '') {
    modulesContainer.replaceChildren();
    if (!manifest || !manifest.modules) {
      modulesContainer.append(el('p', { class: 'small muted' }, 'Manifesto não carregado.'));
      return;
    }

    const q = filterText.toLowerCase().trim();
    const filtered = manifest.modules.filter(m => {
      if (!q) return true;
      if (m.module_name.toLowerCase().includes(q)) return true;
      return m.lessons.some(l => l.file_name.toLowerCase().includes(q));
    });

    if (!filtered.length) {
      modulesContainer.append(el('div', { class: 'empty' },
        el('h3', {}, 'Nenhum módulo encontrado'),
        el('p', {}, 'Tente outro termo de busca.')
      ));
      return;
    }

    for (const mod of filtered) {
      const details = el('details', {
        class: 'panel',
        style: 'padding: 12px 16px; border: 1px solid rgba(255,255,255,0.06); margin-bottom: 8px;'
      });

      const summary = el('summary', {
        style: 'cursor: pointer; display: flex; align-items: center; justify-content: space-between; user-select: none;'
      },
        el('div', { style: 'display: flex; align-items: center; gap: 10px;' },
          el('strong', { style: 'font-size: 14px;' }, mod.module_name),
          badge(`${mod.lesson_count} aulas`, 'blue')
        ),
        el('div', { style: 'display: flex; align-items: center; gap: 12px;' },
          el('span', { class: 'small muted' }, `${mod.total_duration_hours}h (${mod.total_duration_min} min)`),
          el('span', { class: 'small muted' }, `${mod.total_size_mb} MB`)
        )
      );
      details.append(summary);

      const lessonsList = el('div', {
        style: 'margin-top: 12px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.05); display: flex; flex-direction: column; gap: 6px;'
      });

      for (const lesson of mod.lessons) {
        const cleanName = lesson.file_name.replace('.mp4', '');
        const item = el('div', {
          style: 'display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; background: rgba(255,255,255,0.02); border-radius: 4px; font-size: 13px;'
        },
          el('span', {}, cleanName),
          el('span', { class: 'small muted' }, `${lesson.duration_min} min · ${lesson.size_mb} MB`)
        );
        lessonsList.append(item);
      }
      details.append(lessonsList);
      modulesContainer.append(details);
    }
  }

  filterInput.addEventListener('input', e => renderModules(e.target.value));
  renderModules();
}

window.BrainArchitecture = { render };
})();
