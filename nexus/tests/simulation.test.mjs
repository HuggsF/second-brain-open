import assert from 'node:assert/strict';
import test from 'node:test';

// The explicit assertion makes an absent engine an expected RED, not a loader error.
const engine = await import('../src/simulation.mjs').catch((error) => {
  if (error.code !== 'ERR_MODULE_NOT_FOUND') throw error;
  return null;
});

const NOW = 1_800_000_000_000;
const TASK = 'Preparar o novo fluxo de recebimento';
const IDS = ['manager', 'researcher', 'coder', 'writer', 'reviewer'];

function api() {
  assert.ok(engine, 'O motor puro ainda não foi implementado');
  return engine;
}

function agent(state, id) {
  return state.agents.find((item) => item.id === id);
}

function advance(state, count, now = NOW) {
  for (let index = 1; index <= count; index += 1) {
    state = api().tickSimulation(state, now + index * 2000);
  }
  return state;
}

function awaitingApproval() {
  return advance(api().startSimulation(api().createSimulation(TASK, NOW), NOW), 20);
}

function completed() {
  return advance(api().approveTask(awaitingApproval(), NOW + 42_000), 20, NOW + 42_000);
}

function deepFreeze(value) {
  Object.freeze(value);
  for (const child of Object.values(value)) {
    if (child && typeof child === 'object' && !Object.isFrozen(child)) deepFreeze(child);
  }
  return value;
}

test('nova missão prepara cinco agentes identificáveis sem executar trabalho', () => {
  const { createSimulation, AGENTS } = api();
  const state = createSimulation(TASK, NOW);
  assert.deepEqual(AGENTS.map(({ id }) => id), IDS);
  assert.deepEqual(state.agents.map(({ id }) => id), IDS);
  assert.deepEqual(state.agents.map(({ name }) => name), ['Maia', 'Noah', 'Theo', 'Lia', 'Eva']);
  assert.deepEqual(state.agents.map(({ room }) => room), ['orchestrator', 'research', 'development', 'writing', 'meeting']);
  assert.equal(state.mode, 'idle');
  assert.equal(state.runId, 0);
  assert.equal(state.tick, 0);
  assert.equal(state.task, TASK);
  assert.equal(state.needsApproval, false);
  for (const item of state.agents) {
    assert.equal(item.status, 'idle');
    assert.equal(item.progress, 0);
    assert.equal(item.tokens, 0);
    assert.equal(item.completed, 0);
    assert.ok(Array.isArray(item.history));
    assert.ok(item.memory.length > 0);
    assert.ok(item.task.length > 0);
  }
});

test('iniciar cria uma execução coordenada pelo orquestrador', () => {
  const { createSimulation, startSimulation } = api();
  const state = startSimulation(createSimulation(TASK, NOW), NOW + 2000);
  assert.equal(state.mode, 'running');
  assert.equal(state.runId, 1);
  assert.equal(state.tick, 0);
  assert.equal(agent(state, 'manager').status, 'thinking');
  assert.equal(agent(state, 'researcher').status, 'idle');
  assert.ok(state.logs.some(({ agentId }) => agentId === 'manager'));
});

test('pesquisa acontece antes de desenvolvimento e redação', () => {
  const { createSimulation, startSimulation } = api();
  const state = advance(startSimulation(createSimulation(TASK, NOW), NOW), 2);
  assert.equal(agent(state, 'researcher').status, 'working');
  assert.ok(agent(state, 'researcher').progress > 0);
  assert.equal(agent(state, 'coder').status, 'idle');
  assert.equal(agent(state, 'writer').status, 'idle');
  assert.equal(agent(state, 'reviewer').status, 'idle');
});

test('pesquisa concluída libera desenvolvimento e redação juntos', () => {
  const { createSimulation, startSimulation, tickSimulation } = api();
  let state = startSimulation(createSimulation(TASK, NOW), NOW);
  for (let index = 1; index <= 8 && agent(state, 'researcher').status !== 'done'; index += 1) {
    state = tickSimulation(state, NOW + index * 2000);
  }
  assert.equal(agent(state, 'researcher').status, 'done');
  assert.equal(agent(state, 'researcher').progress, 100);
  assert.equal(agent(state, 'researcher').completed, 1);
  assert.notEqual(agent(state, 'coder').status, 'idle');
  assert.notEqual(agent(state, 'writer').status, 'idle');
  assert.equal(agent(state, 'reviewer').status, 'idle');
});

test('revisão só começa após código e texto concluídos', () => {
  const { createSimulation, startSimulation, tickSimulation } = api();
  let state = startSimulation(createSimulation(TASK, NOW), NOW);
  for (let index = 1; index <= 15 && agent(state, 'reviewer').status === 'idle'; index += 1) {
    state = tickSimulation(state, NOW + index * 2000);
  }
  assert.notEqual(agent(state, 'reviewer').status, 'idle');
  assert.equal(agent(state, 'coder').status, 'done');
  assert.equal(agent(state, 'writer').status, 'done');
  assert.equal(agent(state, 'coder').progress, 100);
  assert.equal(agent(state, 'writer').progress, 100);
});

test('aprovação bloqueia conclusão e congela trabalho pendente', () => {
  const state = awaitingApproval();
  assert.equal(state.mode, 'running');
  assert.equal(state.needsApproval, true);
  assert.equal(agent(state, 'reviewer').status, 'waitingApproval');
  assert.equal(agent(state, 'manager').status, 'waitingApproval');
  assert.ok(agent(state, 'reviewer').progress < 100);
  assert.deepEqual(advance(state, 100, NOW + 100_000), state);
});

test('aprovar antes do pedido ou depois do fim não altera a execução', () => {
  const { createSimulation, startSimulation, approveTask } = api();
  const idle = createSimulation(TASK, NOW);
  const running = startSimulation(idle, NOW);
  assert.deepEqual(approveTask(idle, NOW + 2000), idle);
  assert.deepEqual(approveTask(running, NOW + 2000), running);
  const done = completed();
  assert.deepEqual(approveTask(done, NOW + 100_000), done);
});

test('aprovação libera revisão e a missão termina com cinco entregas', () => {
  const { approveTask } = api();
  const pending = awaitingApproval();
  const approved = approveTask(pending, NOW + 42_000);
  assert.equal(approved.needsApproval, false);
  assert.equal(approved.mode, 'running');
  assert.notEqual(agent(approved, 'reviewer').status, 'waitingApproval');
  assert.equal(approved.tick, pending.tick);
  const done = advance(approved, 20, NOW + 42_000);
  assert.equal(done.mode, 'completed');
  assert.equal(done.needsApproval, false);
  for (const item of done.agents) {
    assert.equal(item.status, 'done');
    assert.equal(item.progress, 100);
    assert.equal(item.completed, 1);
    assert.ok(item.tokens > 0);
    assert.ok(item.history.length > 0);
  }
  assert.ok(done.logs.some(({ kind }) => kind === 'approval'));
  assert.equal(done.logs[0].kind, 'success');
});

test('pausa congela tick, progresso, contexto e métricas', () => {
  const { createSimulation, startSimulation, pauseSimulation } = api();
  const running = advance(startSimulation(createSimulation(TASK, NOW), NOW), 3);
  const paused = pauseSimulation(running, NOW + 7000);
  assert.equal(paused.mode, 'paused');
  assert.equal(paused.tick, running.tick);
  assert.deepEqual(paused.agents, running.agents);
  assert.deepEqual(advance(paused, 100, NOW + 100_000), paused);
  assert.deepEqual(pauseSimulation(paused, NOW + 120_000), paused);
});

test('retomar preserva execução e avança a partir do tick pausado', () => {
  const { createSimulation, startSimulation, pauseSimulation, tickSimulation } = api();
  const running = advance(startSimulation(createSimulation(TASK, NOW), NOW), 3);
  const paused = pauseSimulation(running, NOW + 7000);
  const resumed = startSimulation(paused, NOW + 120_000);
  assert.equal(resumed.mode, 'running');
  assert.equal(resumed.runId, running.runId);
  assert.equal(resumed.tick, running.tick);
  assert.deepEqual(resumed.agents, paused.agents);
  assert.equal(tickSimulation(resumed, NOW + 122_000).tick, running.tick + 1);
});

test('iniciar uma execução ativa é idempotente', () => {
  const { createSimulation, startSimulation } = api();
  const running = advance(startSimulation(createSimulation(TASK, NOW), NOW), 3);
  assert.deepEqual(startSimulation(running, NOW + 100_000), running);
});

test('aprovação durante pausa só avança depois da retomada', () => {
  const { approveTask, pauseSimulation, startSimulation } = api();
  const pending = pauseSimulation(awaitingApproval(), NOW + 42_000);
  const approved = approveTask(pending, NOW + 44_000);
  assert.equal(approved.mode, 'paused');
  assert.equal(approved.needsApproval, false);
  assert.deepEqual(advance(approved, 20, NOW + 44_000), approved);
  assert.equal(advance(startSimulation(approved, NOW + 100_000), 20, NOW + 100_000).mode, 'completed');
});

test('iniciar após conclusão cria novo ciclo e incrementa runId', () => {
  const { startSimulation } = api();
  const done = completed();
  const next = startSimulation(done, NOW + 100_000);
  assert.equal(next.runId, done.runId + 1);
  assert.equal(next.task, TASK);
  assert.equal(next.tick, 0);
  assert.equal(next.mode, 'running');
  assert.equal(next.needsApproval, false);
  for (const item of next.agents) {
    assert.equal(item.progress, 0);
    assert.equal(item.tokens, 0);
    assert.equal(item.completed, 0);
  }
});

test('missão nova limpa contexto da missão anterior', () => {
  const { createSimulation, startSimulation } = api();
  const old = completed();
  const fresh = startSimulation(createSimulation('Organizar a equipe da tarde', NOW + 100_000), NOW + 100_000);
  assert.equal(fresh.runId, 1);
  assert.equal(fresh.task, 'Organizar a equipe da tarde');
  assert.equal(fresh.tick, 0);
  assert.ok(fresh.agents.every(({ tokens, completed }) => tokens === 0 && completed === 0));
  assert.ok(fresh.logs.every(({ id }) => !old.logs.some((item) => item.id === id)));
});

test('mesma missão e timestamps geram resultados determinísticos', () => {
  api();
  assert.deepEqual(completed(), completed());
});

test('todas as operações aceitam snapshots congelados sem mutá-los', () => {
  const { createSimulation, startSimulation, pauseSimulation, tickSimulation, approveTask } = api();
  const operations = [
    [createSimulation(TASK, NOW), startSimulation],
    [startSimulation(createSimulation(TASK, NOW), NOW), tickSimulation],
    [advance(startSimulation(createSimulation(TASK, NOW), NOW), 3), pauseSimulation],
    [pauseSimulation(awaitingApproval(), NOW + 42_000), startSimulation],
    [awaitingApproval(), approveTask],
    [completed(), startSimulation],
  ];
  for (const [state, operation] of operations) {
    const before = structuredClone(state);
    deepFreeze(state);
    const next = operation(state, NOW + 100_000);
    assert.deepEqual(state, before);
    assert.notEqual(next, state);
    next.agents[0].memory.push('Alteração apenas no snapshot novo');
    assert.deepEqual(state, before);
  }
});

test('logs recentes, memória e histórico permanecem limitados', () => {
  const { createSimulation, startSimulation, tickSimulation } = api();
  const state = startSimulation(createSimulation(TASK, NOW), NOW);
  state.logs = Array.from({ length: 60 }, (_, index) => ({ id: `anterior-${index}`, agentId: 'manager', agentName: 'Maia', message: 'Evento anterior', at: NOW - index - 1, kind: 'info' }));
  state.agents = state.agents.map((item) => ({
    ...item,
    memory: Array.from({ length: 8 }, (_, index) => `Contexto anterior ${index}`),
    history: Array.from({ length: 12 }, (_, index) => ({ title: `Etapa anterior ${index}`, at: NOW - index - 1 })),
  }));
  const next = tickSimulation(state, NOW + 2000);
  assert.equal(next.logs.length, 60);
  assert.equal(next.logs[0].at, NOW + 2000);
  assert.ok(next.logs.every((log, index) => index === 0 || log.at <= next.logs[index - 1].at));
  assert.equal(new Set(next.logs.map(({ id }) => id)).size, 60);
  for (const item of next.agents) {
    assert.ok(item.memory.length <= 8);
    assert.ok(item.history.length <= 12);
    assert.ok(item.progress >= 0 && item.progress <= 100);
    assert.ok(item.tokens >= 0 && item.tokens <= 20_000);
  }
});

test('ticks em idle ou completed e pausa fora da execução são inertes', () => {
  const { createSimulation, tickSimulation, pauseSimulation } = api();
  const idle = createSimulation(TASK, NOW);
  const done = completed();
  assert.deepEqual(tickSimulation(idle, NOW + 2000), idle);
  assert.deepEqual(pauseSimulation(idle, NOW + 2000), idle);
  assert.deepEqual(tickSimulation(done, NOW + 100_000), done);
  assert.deepEqual(pauseSimulation(done, NOW + 100_000), done);
});

test('missão vazia recebe exemplo e texto longo é limitado', () => {
  const { createSimulation } = api();
  assert.equal(createSimulation('   ', NOW).task, createSimulation(undefined, NOW).task);
  assert.equal(createSimulation(null, NOW).task, createSimulation(undefined, NOW).task);
  assert.equal(createSimulation('  Planejar chegada  ', NOW).task, 'Planejar chegada');
  assert.equal(createSimulation('a'.repeat(500), NOW).task.length, 240);
});
