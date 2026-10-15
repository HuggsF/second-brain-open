// Cliente da API do BFF (mesma origem). Nunca lanca: falha de rede vira {ok:false, status:0, data:null}.

export const observationUrl = (env) => `/v1/observability?environment=${encodeURIComponent(env)}`;
export const assessmentUrl = (env) => `/v1/observability/assessment?environment=${encodeURIComponent(env)}`;

export async function fetchJson(url, init) {
  let response;
  try {
    response = await fetch(url, init);
  } catch {
    return { ok: false, status: 0, data: null };
  }
  let data = null;
  try {
    const text = await response.text();
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  return { ok: response.ok, status: response.status, data };
}

export const getRules = () => fetchJson('/api/rules');
export const getPlaybooks = () => fetchJson('/api/playbooks');
export const getExecutions = (playbookId) =>
  fetchJson(playbookId ? `/api/playbooks/${encodeURIComponent(playbookId)}/executions` : '/api/playbooks/executions');
export const getAssessment = (env) => fetchJson(assessmentUrl(env));
export const postExecution = (payload) =>
  fetchJson('/api/playbooks/executions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

export const getPlaybookDetail = (id) => fetchJson(`/api/playbooks/${encodeURIComponent(id)}`);
export const renderPlaybook = (id, params = {}) =>
  fetchJson(`/api/playbooks/${encodeURIComponent(id)}/render`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ params }),
  });

// Extrai uma lista do corpo `{ [key]: [...] }` quando a resposta e ok; erros passam intactos.
export const pick = (result, key) =>
  result.ok ? { ...result, data: (result.data && result.data[key]) ?? [] } : result;

// Mensagem em portugues para uma resposta que nao foi ok.
export function describeFailure(status) {
  if (status === 0) return 'Sem conexão com o servidor.';
  if (status === 401) return 'Sessão local expirada. Gere um novo link de conexão.';
  if (status === 503) return 'Banco de evidências indisponível.';
  return `Falha ao carregar (HTTP ${status}).`;
}
