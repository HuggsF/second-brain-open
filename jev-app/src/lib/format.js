// Formatacao e metadados de exibicao. Modulo puro, sem DOM.

const has = (table, key) => typeof key === 'string' && Object.prototype.hasOwnProperty.call(table, key);

export const ENVIRONMENTS = ['production', 'hml', 'local'];
const ENV_LABELS = { production: 'Produção', hml: 'Homologação', local: 'Local' };
export const envLabel = (env) => (has(ENV_LABELS, env) ? ENV_LABELS[env] : String(env ?? ''));

const RESULT_META = {
  pass: { label: 'Aprovada', icon: 'CircleCheck', tone: 'green' },
  fail: { label: 'Falhou', icon: 'CircleX', tone: 'red' },
  error: { label: 'Erro', icon: 'TriangleAlert', tone: 'yellow' },
  skipped: { label: 'Ignorada', icon: 'CircleMinus', tone: 'grey' },
};
export const resultMeta = (result) => ({
  ...(has(RESULT_META, result) ? RESULT_META[result] : { label: 'Desconhecido', icon: 'CircleHelp', tone: 'grey' }),
});

const STATUS_META = {
  active: { label: 'Ativo', tone: 'green' },
  draft: { label: 'Rascunho', tone: 'yellow' },
  retired: { label: 'Aposentado', tone: 'grey' },
};
export const statusMeta = (status) => ({
  ...(has(STATUS_META, status) ? STATUS_META[status] : { label: 'Desconhecido', tone: 'grey' }),
});

const KIND_META = { test: { label: 'Teste' }, runbook: { label: 'Runbook' } };
export const kindMeta = (kind) => ({ ...(has(KIND_META, kind) ? KIND_META[kind] : { label: 'Desconhecido' }) });

export const parseTs = (ts) => (typeof ts === 'string' ? Date.parse(ts) : NaN);

export function relativeTime(ts, now = Date.now()) {
  const t = parseTs(ts);
  if (Number.isNaN(t)) return 'data inválida';
  const seconds = Math.floor((now - t) / 1000);
  if (seconds < -60) return 'no futuro';
  if (seconds < 60) return 'agora há pouco';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `há ${hours} h`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `há ${days} d`;
  const months = Math.floor(days / 30);
  if (months < 12) return `há ${months} ${months === 1 ? 'mês' : 'meses'}`;
  const years = Math.floor(days / 365);
  return `há ${years} ${years === 1 ? 'ano' : 'anos'}`;
}

export function formatDateTime(ts) {
  const t = parseTs(ts);
  if (Number.isNaN(t)) return String(ts ?? '');
  return new Date(t).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

// Mais novo primeiro; datas invalidas por ultimo; nao muta a entrada.
export function sortByTsDesc(rows) {
  const key = (r) => {
    const t = parseTs(r.ts);
    return Number.isNaN(t) ? -Infinity : t;
  };
  return [...rows].sort((a, b) => key(b) - key(a));
}
