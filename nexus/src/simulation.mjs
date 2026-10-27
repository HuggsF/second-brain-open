/**
 * Motor de uma demonstração local. Cada tick corresponde a uma etapa fictícia;
 * o consumidor decide a cadência (por exemplo, uma chamada a cada 2 segundos).
 * Timestamps explícitos tornam a execução reproduzível. Não há I/O ou modelos.
 */
export const AGENTS = Object.freeze([
  Object.freeze({ id: 'manager', name: 'Maia', role: 'Orquestrador', room: 'orchestrator', emoji: '📋' }),
  Object.freeze({ id: 'researcher', name: 'Noah', role: 'Researcher', room: 'research', emoji: '🔍' }),
  Object.freeze({ id: 'coder', name: 'Theo', role: 'Coder', room: 'development', emoji: '💻' }),
  Object.freeze({ id: 'writer', name: 'Lia', role: 'Writer', room: 'writing', emoji: '✍️' }),
  Object.freeze({ id: 'reviewer', name: 'Eva', role: 'Reviewer', room: 'meeting', emoji: '🔎' }),
]);

const DEFAULT_TASK = 'Criar um plano de implantação do portal logístico';
const LIMITS = { logs: 60, history: 12, memory: 8, tokens: 20_000, collabEvents: 120 };
const RESPONSIBILITIES = {
  manager: 'Coordenar as entregas',
  researcher: 'Levantar requisitos e referências',
  coder: 'Preparar uma solução de demonstração',
  writer: 'Escrever o plano de implantação',
  reviewer: 'Revisar qualidade e consistência',
};

/** Collaboration event types emitted alongside simulation steps */
export const COLLAB_TYPES = Object.freeze({
  MISSION_RECEIVED: 'mission_received',
  DISTRIBUTE: 'distribute',
  CONTEXT_SHARE: 'context_share',
  PARALLEL_WORK: 'parallel_work',
  HANDOFF_REVIEW: 'handoff_review',
  BRIEF_MEETING: 'brief_meeting',
  APPROVAL_REQUEST: 'approval_request',
  APPROVAL_GRANTED: 'approval_granted',
  CELEBRATION: 'celebration',
  AGENT_ENTER: 'agent_enter',
});

/** Bubble messages associated with collaboration events */
const BUBBLE_MESSAGES = {
  mission_received: 'Nova missão recebida!',
  distribute: 'Distribuindo responsabilidades…',
  context_share: 'Contexto compartilhado',
  parallel_work: null, // no bubble, just visual
  handoff_review: 'Entrega para revisão',
  brief_meeting: 'Reunião rápida',
  approval_request: 'Preciso da sua aprovação',
  approval_granted: 'Aprovação recebida!',
  celebration: 'Missão concluída! 🎉',
};

// Eventos são resumos observáveis de trabalho sintético, sem pensamentos internos.
// Format: [agentId, status, progress, message, logKind, collaboration?]
// collaboration: { type, from?, to?, bubble? }
const STEPS = [
  [],
  [
    ['manager', 'working', 20, 'Responsabilidades distribuídas para a equipe.', 'handoff',
      { type: 'distribute', from: 'manager', to: ['researcher', 'coder', 'writer', 'reviewer'], bubble: 'Equipe, temos uma nova missão!' }],
    ['researcher', 'thinking', 10, 'Organizando os requisitos da missão.', 'info',
      { type: 'agent_enter', from: 'researcher', bubble: 'Vou começar o levantamento' }],
  ],
  [
    ['manager', 'thinking', 28, 'Conferindo dependências entre as entregas.', 'info',
      { type: null, bubble: 'Verificando dependências…' }],
    ['researcher', 'working', 35, 'Reunindo referências operacionais fictícias.', 'info',
      { type: null, bubble: 'Pesquisando referências' }],
  ],
  [
    ['manager', 'working', 35, 'Acompanhando o levantamento inicial.', 'info'],
    ['researcher', 'working', 70, 'Comparando requisitos e registrando premissas.', 'info',
      { type: null, bubble: 'Documentando premissas' }],
  ],
  [
    ['researcher', 'done', 100, 'Pesquisa concluída; requisitos compartilhados.', 'handoff',
      { type: 'context_share', from: 'researcher', to: ['coder', 'writer'], bubble: 'Contexto enviado para Theo e Lia' }],
    ['manager', 'working', 45, 'Liberando desenvolvimento e redação em paralelo.', 'handoff',
      { type: 'parallel_work', from: 'manager', to: ['coder', 'writer'] }],
    ['coder', 'thinking', 10, 'Organizando a solução a partir dos requisitos.', 'info',
      { type: 'agent_enter', from: 'coder', bubble: 'Recebendo contexto de Noah' }],
    ['writer', 'thinking', 15, 'Estruturando o documento com base na pesquisa.', 'info',
      { type: 'agent_enter', from: 'writer', bubble: 'Analisando o material' }],
  ],
  [
    ['manager', 'thinking', 50, 'Conferindo a consistência do plano de trabalho.', 'info'],
    ['coder', 'working', 30, 'Preparando o fluxo de demonstração.', 'info',
      { type: null, bubble: 'Escrevendo código…' }],
    ['writer', 'working', 35, 'Redigindo objetivos, etapas e responsabilidades.', 'info',
      { type: null, bubble: 'Estruturando documento' }],
  ],
  [
    ['manager', 'working', 58, 'Acompanhando as duas entregas em andamento.', 'info',
      { type: null, bubble: 'Acompanhando a equipe' }],
    ['coder', 'thinking', 55, 'Conferindo as regras do fluxo proposto.', 'info',
      { type: null, bubble: 'Revisando lógica…' }],
    ['writer', 'working', 60, 'Detalhando critérios e passos de implantação.', 'info',
      { type: null, bubble: 'Escrevendo detalhes' }],
  ],
  [
    ['manager', 'thinking', 65, 'Organizando a transferência para revisão.', 'info'],
    ['coder', 'working', 80, 'Finalizando a solução de demonstração.', 'info',
      { type: null, bubble: 'Quase pronto!' }],
    ['writer', 'thinking', 80, 'Conferindo clareza e consistência do documento.', 'info',
      { type: null, bubble: 'Revisando texto final' }],
  ],
  [
    ['coder', 'done', 100, 'Solução de demonstração pronta para revisão.', 'handoff',
      { type: 'handoff_review', from: 'coder', to: ['reviewer'], bubble: 'Entrega pronta para Eva' }],
    ['writer', 'done', 100, 'Plano de implantação pronto para revisão.', 'handoff',
      { type: 'handoff_review', from: 'writer', to: ['reviewer'], bubble: 'Documento finalizado' }],
    ['manager', 'working', 75, 'Entregas reunidas e encaminhadas para Eva.', 'handoff',
      { type: 'handoff_review', from: 'manager', to: ['reviewer'] }],
    ['reviewer', 'thinking', 20, 'Organizando a revisão das entregas reunidas.', 'info',
      { type: 'agent_enter', from: 'reviewer', bubble: 'Iniciando revisão' }],
  ],
  [
    ['manager', 'thinking', 80, 'Conferindo critérios para a aprovação local.', 'info'],
    ['reviewer', 'working', 55, 'Revisando requisitos, solução e documentação.', 'info',
      { type: 'brief_meeting', from: 'reviewer', to: ['manager'], bubble: 'Revisando todas as entregas' }],
  ],
  [
    ['manager', 'waitingApproval', 85, 'Execução aguardando sua aprovação local.', 'approval',
      { type: 'approval_request', from: 'manager', bubble: 'Aguardando sua decisão' }],
    ['reviewer', 'waitingApproval', 70, 'Revisão preliminar pronta; aprovação necessária.', 'approval',
      { type: 'approval_request', from: 'reviewer', bubble: 'Preciso da sua aprovação' }],
  ],
  [
    ['manager', 'working', 90, 'Coordenando a finalização da missão aprovada.', 'info',
      { type: 'approval_granted', bubble: 'Aprovação recebida!' }],
    ['reviewer', 'thinking', 85, 'Organizando a validação final aprovada.', 'info',
      { type: null, bubble: 'Finalizando validação' }],
  ],
  [
    ['manager', 'working', 95, 'Reunindo os resultados finais da equipe.', 'info'],
    ['reviewer', 'working', 95, 'Conferindo os critérios finais de entrega.', 'info',
      { type: null, bubble: 'Últimas verificações' }],
  ],
  [
    ['reviewer', 'done', 100, 'Revisão final concluída com aprovação local.', 'success',
      { type: 'celebration', from: 'reviewer', bubble: 'Tudo revisado e aprovado!' }],
    ['manager', 'done', 100, 'Missão concluída; cinco entregas registradas.', 'success',
      { type: 'celebration', from: 'manager', bubble: 'Missão concluída! 🎉' }],
  ],
];

function cloneState(state) {
  return structuredClone({
    ...state,
    agents: state.agents.map((item) => ({
      ...item,
      memory: item.memory.slice(0, LIMITS.memory),
      history: item.history.slice(0, LIMITS.history).map((entry) => ({ ...entry })),
    })),
    logs: state.logs.slice(0, LIMITS.logs).map((entry) => ({ ...entry })),
    collabEvents: (state.collabEvents || []).slice(-LIMITS.collabEvents).map((e) => ({ ...e, to: [...(e.to || [])] })),
  });
}

function logEvent(state, agentId, message, at, kind = 'info') {
  const profile = AGENTS.find(({ id }) => id === agentId);
  const prefix = `${at}:${state.runId}:${state.tick}:${agentId}`;
  const usedIds = new Set(state.logs.map(({ id }) => id));
  let suffix = 0;
  while (usedIds.has(`${prefix}:${suffix}`)) suffix += 1;
  state.logs.unshift({ id: `${prefix}:${suffix}`, agentId, agentName: profile.name, message, at, kind });
  state.logs = state.logs.slice(0, LIMITS.logs);
}

function remember(item, title, at) {
  item.memory = [title, ...item.memory.filter((value) => value !== title)].slice(0, LIMITS.memory);
  item.history = [{ title, at }, ...item.history].slice(0, LIMITS.history);
}

function applyStep(state, step, now) {
  const [id, status, progress, message, kind = 'info', collab] = step;
  const item = state.agents.find((candidate) => candidate.id === id);
  item.status = status;
  item.progress = Math.max(0, Math.min(100, progress));
  const tokens = status === 'working' ? 260 : status === 'thinking' ? 120 : status === 'done' ? 90 : 0;
  item.tokens = Math.min(LIMITS.tokens, item.tokens + tokens);
  if (status === 'done') {
    item.completed = 1;
    item.task = `Entrega concluída: ${state.task}`;
  }
  remember(item, message, now);
  logEvent(state, id, message, now, kind);

  // Emit collaboration event
  if (collab && collab.type) {
    state.collabEvents.push({
      id: `collab:${state.runId}:${state.tick}:${id}:${collab.type}`,
      tick: state.tick,
      type: collab.type,
      from: collab.from || id,
      to: [...(collab.to || [])],
      bubble: collab.bubble || BUBBLE_MESSAGES[collab.type] || null,
      agentId: id,
      at: now,
      consumed: false,
    });
  } else if (collab && collab.bubble) {
    // Bubble-only event (no collaboration type, just a speech bubble)
    state.collabEvents.push({
      id: `bubble:${state.runId}:${state.tick}:${id}`,
      tick: state.tick,
      type: 'bubble_only',
      from: id,
      to: [],
      bubble: collab.bubble,
      agentId: id,
      at: now,
      consumed: false,
    });
  }
}

/** Prepara uma missão limpa, sem iniciar sua execução. */
export function createSimulation(task = DEFAULT_TASK, now = Date.now()) {
  const mission = (typeof task === 'string' && task.trim() ? task.trim() : DEFAULT_TASK).slice(0, 240);
  const state = {
    mode: 'idle',
    tick: 0,
    task: mission,
    agents: AGENTS.map((profile) => ({
      ...profile,
      status: 'idle',
      progress: 0,
      task: `${RESPONSIBILITIES[profile.id]}: ${mission}`,
      memory: [`Responsabilidade: ${RESPONSIBILITIES[profile.id]}.`, `Missão fictícia: ${mission}`],
      history: [],
      completed: 0,
      tokens: 0,
    })),
    logs: [],
    collabEvents: [],
    needsApproval: false,
    runId: 0,
  };
  logEvent(state, 'manager', 'Escritório pronto para iniciar uma missão local simulada.', now, 'system');
  return state;
}

/** Retoma uma pausa ou inicia um ciclo limpo após idle/completed. */
export function startSimulation(state, now = Date.now()) {
  if (state.mode === 'running') return state;
  if (state.mode === 'paused') {
    const next = cloneState(state);
    next.mode = 'running';
    logEvent(next, 'manager', 'Simulação retomada a partir da etapa pausada.', now, 'system');
    return next;
  }
  const next = state.mode === 'completed' ? createSimulation(state.task, now) : cloneState(state);
  next.mode = 'running';
  next.tick = 0;
  next.runId = state.runId + 1;
  next.needsApproval = false;
  next.collabEvents = [];
  const manager = next.agents.find(({ id }) => id === 'manager');
  manager.status = 'thinking';
  remember(manager, 'Missão recebida; preparando a distribuição de responsabilidades.', now);
  logEvent(next, 'manager', 'Missão iniciada; preparando a equipe.', now, 'system');

  // Emit mission received event
  next.collabEvents.push({
    id: `collab:${next.runId}:0:manager:mission_received`,
    tick: 0,
    type: COLLAB_TYPES.MISSION_RECEIVED,
    from: 'manager',
    to: [],
    bubble: 'Nova missão recebida!',
    agentId: 'manager',
    at: now,
    consumed: false,
  });

  return next;
}

/** Congela uma execução ativa; tick e métricas permanecem intactos. */
export function pauseSimulation(state, now = Date.now()) {
  if (state.mode !== 'running') return state;
  const next = cloneState(state);
  next.mode = 'paused';
  logEvent(next, 'manager', 'Simulação pausada; etapa e métricas preservadas.', now, 'system');
  return next;
}

/** Avança exatamente uma etapa, salvo pausa, aprovação pendente ou término. */
export function tickSimulation(state, now = Date.now()) {
  if (state.mode !== 'running' || state.needsApproval) return state;
  const next = cloneState(state);
  next.tick += 1;
  // Mark previous collab events as consumed
  next.collabEvents.forEach((e) => { e.consumed = true; });
  for (const step of STEPS[next.tick] ?? []) applyStep(next, step, now);
  next.collabEvents = next.collabEvents.slice(-LIMITS.collabEvents);
  if (next.tick === 10) next.needsApproval = true;
  if (next.tick >= STEPS.length - 1) next.mode = 'completed';
  return next;
}

/** Aprovação local libera revisão; uma pausa continua pausada. */
export function approveTask(state, now = Date.now()) {
  if (!state.needsApproval || !['running', 'paused'].includes(state.mode)) return state;
  const next = cloneState(state);
  next.needsApproval = false;
  next.collabEvents.forEach((e) => { e.consumed = true; });
  for (const id of ['manager', 'reviewer']) {
    const item = next.agents.find((candidate) => candidate.id === id);
    item.status = 'working';
    remember(item, 'Aprovação local recebida; finalização liberada.', now);
  }
  logEvent(next, 'manager', 'Aprovação local recebida; revisão final liberada.', now, 'approval');
  next.collabEvents.push({
    id: `collab:${next.runId}:${next.tick}:manager:approval_granted`,
    tick: next.tick,
    type: COLLAB_TYPES.APPROVAL_GRANTED,
    from: 'manager',
    to: ['reviewer'],
    bubble: 'Aprovação recebida! Finalizando...',
    agentId: 'manager',
    at: now,
    consumed: false,
  });
  return next;
}

/** Returns only new (unconsumed) collaboration events from state */
export function getNewCollabEvents(state) {
  return (state.collabEvents || []).filter((e) => !e.consumed);
}

/** Total number of steps in the simulation */
export const TOTAL_STEPS = STEPS.length - 1;


