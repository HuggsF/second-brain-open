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
