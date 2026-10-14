// Apoio dos testes de componente (nao entra no bundle: so os testes importam).
import { vi } from 'vitest';

export const state = (data, extra = {}) => ({ loading: false, error: null, data, reload: vi.fn(), ...extra });

export const assessment = (environment, over = {}) => ({
  environment,
  status: 'green',
  reason: `Ambiente ${environment} responde normalmente.`,
  stale: false,
  nodes: [
    { id: 'process', status: 'green', reason: 'Processo no ar' },
    { id: 'internal', status: 'green', reason: 'Fila interna ok' },
    { id: 'external', status: 'green', reason: 'Integrações ok' },
    { id: 'database', status: 'green', reason: 'Banco ok' },
  ],
  contradictions: [],
  rules_available: true,
  ...over,
});

export const rule = (over) => ({
  id: 'RULE-X',
  title: 'Regra de exemplo',
  status: 'active',
  playbooks: [],
  playbook_latest: {},
  state: '',
  light: 'grey',
  light_reason: 'sem execução de teste registrada',
  test_playbooks: ['PB-001'],
  test_environments: ['hml'],
  ...over,
});

export const RULES = [
  rule({ id: 'RULE-G', title: 'Regra verde', light: 'green', light_reason: 'PB-002 passou há pouco', test_environments: ['hml'] }),
  rule({ id: 'RULE-Y', title: 'Regra amarela', light: 'yellow', light_reason: 'última execução de teste expirou', test_environments: ['production', 'hml'] }),
  rule({ id: 'RULE-C', title: 'Regra cinza', light: 'grey', light_reason: 'sem execução de teste registrada', test_environments: ['hml', 'local'] }),
];

export const RED_RULE = rule({ id: 'RULE-R', title: 'Regra vermelha', light: 'red', light_reason: 'PB-001 falhou em hml', test_environments: ['hml'] });

export const PLAYBOOKS = [
  { id: 'PB-001', title: 'Suíte automatizada do Hub', status: 'active', kind: 'test', environment: 'local', validates: ['RULE-G'], ttl_hours: 168, targets: [], params: [], filename: 'PB-001.md' },
  { id: 'PB-002', title: 'Emissão bloqueada sem NF real', status: 'active', kind: 'test', environment: 'hml', validates: ['RULE-G'], ttl_hours: 168, targets: [], params: [], filename: 'PB-002.md' },
  { id: 'PB-003', title: 'Verificação manual de homologação', status: 'draft', kind: 'runbook', environment: 'hml', validates: [], ttl_hours: null, targets: [], params: [], filename: 'PB-003.md' },
  { id: 'PB-004', title: 'Procedimento antigo de deploy', status: 'retired', kind: 'runbook', environment: 'production', validates: [], ttl_hours: null, targets: [], params: [], filename: 'PB-004.md' },
];

export const EXECUTIONS = [
  { playbook_id: 'PB-002', ts: '2026-10-10T10:00:00-03:00', result: 'pass', environment: 'hml', evidence_ref: 'vault/x.md:57', summary: 'Emissão bloqueada como esperado', commit_sha: 'abc1234', run_id: 'run-77', source: 'dashboard' },
  { playbook_id: 'PB-001', ts: '2026-10-12T10:00:00-03:00', result: 'fail', environment: 'local', evidence_ref: 'DEM-12', summary: 'Cenário 7 falhou', source: 'cli' },
  { playbook_id: 'PB-002', ts: '2026-10-01T10:00:00-03:00', result: 'error', environment: 'hml', evidence_ref: 'https://ci.example/run/9', summary: 'Runner indisponível', _origin: 'seed' },
];

export const json = (body, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

// routes: { 'GET /api/rules': body | (url, init) => body|Response, ... }. Rota ausente = 404.
export function mockFetch(routes) {
  const fn = vi.fn(async (url, init) => {
    const method = (init && init.method) || 'GET';
    const key = `${method} ${url}`;
    const hit = routes[key] ?? routes[`${method} ${url.split('?')[0]}`];
    if (hit === undefined) return json({ error: 'NOT_FOUND' }, 404);
    const value = typeof hit === 'function' ? await hit(url, init) : hit;
    if (value instanceof Response) return value;
    return json(value);
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

export const urls = (fn) => fn.mock.calls.map(([u]) => u);

export const baseRoutes = (over = {}) => ({
  'GET /api/rules': { rules: [...RULES, RED_RULE] },
  'GET /api/playbooks': { playbooks: PLAYBOOKS },
  'GET /api/playbooks/executions': { executions: EXECUTIONS },
  'GET /v1/observability/assessment?environment=production': { schema_version: 1, ...assessment('production') },
  'GET /v1/observability/assessment?environment=hml': {
    schema_version: 1,
    ...assessment('hml', { reason: 'Homologação com aviso de coleta.' }),
  },
  ...over,
});
