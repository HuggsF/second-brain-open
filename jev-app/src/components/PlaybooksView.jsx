import { useId, useMemo, useState } from 'react';
import { ClipboardPlus, RefreshCw } from 'lucide-react';
import { AsyncBoundary, EmptyState, ErrorState, KindBadge, LoadingState, ResultBadge, StatusBadge } from './ui.jsx';
import { useAsync } from '../hooks/useAsync.js';
import { getPlaybookDetail, renderPlaybook } from '../lib/api.js';
import { ENVIRONMENTS, envLabel, parseTs, relativeTime, sortByTsDesc } from '../lib/format.js';

const FILTERS = {
  environment: { label: 'Ambiente', options: ENVIRONMENTS.map((e) => [e, envLabel(e)]) },
  kind: { label: 'Tipo', options: [['test', 'Teste'], ['runbook', 'Runbook']] },
  status: { label: 'Status', options: [['active', 'Ativo'], ['draft', 'Rascunho'], ['retired', 'Aposentado']] },
};

// playbook_id -> { ambiente -> execucao mais recente }
export function lastByPlaybookEnv(executions) {
  const out = {};
  for (const e of executions) {
    const t = parseTs(e.ts);
    const slot = (out[e.playbook_id] ??= {});
    const prev = slot[e.environment];
    if (!prev || (!Number.isNaN(t) && t > parseTs(prev.ts)) || Number.isNaN(parseTs(prev.ts))) slot[e.environment] = e;
  }
  return out;
}

const nonEmpty = (values) => Object.fromEntries(Object.entries(values).filter(([, v]) => v !== ''));
const defaultsOf = (params) =>
  Object.fromEntries((params ?? []).map((p) => [p.name, p.default == null ? '' : String(p.default)]));

function Filters({ filters, onChange }) {
  return (
    <div role="group" aria-label="Filtros" className="mb-3 flex flex-wrap items-end gap-3">
      {Object.entries(FILTERS).map(([key, f]) => (
        <label key={key} className="flex flex-col gap-0.5 text-xs text-muted">
          {f.label}
          <select
            value={filters[key]}
            onChange={(e) => onChange({ ...filters, [key]: e.target.value })}
            className="rounded border border-field-border bg-panel px-2 py-1 text-sm text-text"
          >
            <option value="">Todos</option>
            {f.options.map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </label>
      ))}
    </div>
  );
}

function LastRuns({ runs, executions }) {
  if (executions.error) return <span className="text-xs text-muted">Execuções indisponíveis</span>;
  if (executions.loading && executions.data == null) return <span className="text-xs text-muted">Carregando…</span>;
  const envs = ENVIRONMENTS.filter((e) => runs && runs[e]);
  if (envs.length === 0) return <span className="text-xs text-muted">Sem execução</span>;
  return (
    <div className="flex flex-col gap-1">
      {envs.map((env) => (
        <div key={env} className="flex flex-wrap items-center gap-1.5">
          <span data-last-env className="text-xs text-muted">{envLabel(env)}</span>
          <ResultBadge result={runs[env].result} />
          <span className="text-xs text-muted">{relativeTime(runs[env].ts)}</span>
        </div>
      ))}
    </div>
  );
}

function ParamsAndPreview({ playbook, detail, executions, onRecord }) {
  const params = detail.meta?.params ?? playbook.params ?? [];
  const baseId = useId();
  const [values, setValues] = useState(() => defaultsOf(params));
  const [applied, setApplied] = useState(() => nonEmpty(defaultsOf(params)));
  const preview = useAsync(() => renderPlaybook(playbook.id, applied), [playbook.id, applied]);
  const runs = sortByTsDesc((executions.data ?? []).filter((e) => e.playbook_id === playbook.id));

  return (
    <div className="space-y-4">
      {params.length > 0 ? (
        <div>
          <h3 className="mb-1.5 text-xs font-semibold text-muted">Parâmetros Liquid</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {params.map((p, i) => (
              <label key={p.name} htmlFor={`${baseId}-${i}`} className="flex flex-col gap-0.5 text-xs text-muted">
                {p.label || p.name}
                <input
                  id={`${baseId}-${i}`}
                  type="text"
                  value={values[p.name] ?? ''}
                  onChange={(e) => setValues({ ...values, [p.name]: e.target.value })}
                  className="rounded border border-field-border bg-panel px-2 py-1 text-sm text-text"
                />
              </label>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setApplied(nonEmpty(values))}
            className="mt-2 inline-flex items-center gap-1.5 rounded border border-field-border px-2.5 py-1 text-sm hover:bg-panel2"
          >
            <RefreshCw className="size-3.5" aria-hidden="true" />
            Atualizar prévia
          </button>
        </div>
      ) : null}

      <div>
        <h3 className="mb-1.5 text-xs font-semibold text-muted">Prévia renderizada pelo servidor</h3>
        <div aria-live="polite" aria-busy={preview.loading}>
          {preview.error ? (
            <ErrorState message={preview.error.message} onRetry={preview.reload} />
          ) : preview.data == null ? (
            <LoadingState text="Renderizando prévia…" />
          ) : (
            <pre className="max-h-96 overflow-auto rounded border border-border bg-bg p-3 font-mono text-xs break-words whitespace-pre-wrap">
              {preview.data.rendered_content}
            </pre>
          )}
        </div>
      </div>

      <div>
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <h3 className="text-xs font-semibold text-muted">Execuções deste playbook</h3>
          <button
            type="button"
            onClick={(e) =>
              onRecord(
                {
                  playbookId: playbook.id,
                  params: nonEmpty(values),
                  environment: playbook.environment,
                },
                e.currentTarget,
              )
            }
            className="inline-flex items-center gap-1.5 rounded bg-accent px-2.5 py-1 text-sm font-semibold text-accent-ink hover:opacity-90"
          >
            <ClipboardPlus className="size-4" aria-hidden="true" />
            Registrar execução
          </button>
        </div>
        {runs.length === 0 ? (
          <p className="text-sm text-muted">Nenhuma execução registrada para este playbook.</p>
        ) : (
          <ul className="divide-y divide-border rounded border border-border">
            {runs.map((e, i) => (
              <li key={`${e.ts}-${i}`} className="flex flex-col gap-0.5 px-2.5 py-1.5 text-sm">
                <span className="flex flex-wrap items-center gap-1.5">
                  <ResultBadge result={e.result} />
                  <span className="text-xs text-muted">{envLabel(e.environment)}</span>
                  <span className="text-xs text-muted">{relativeTime(e.ts)}</span>
                </span>
                <span>{e.summary}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function PlaybookDetail({ playbook, executions, onRecord }) {
  const detail = useAsync(() => getPlaybookDetail(playbook.id), [playbook.id]);
  return (
    <section aria-label="Detalhe do playbook" className="rounded border border-border bg-panel p-3">
      <h2 className="mb-3 text-sm font-semibold">
        <span className="font-mono text-accent">{playbook.id}</span> {playbook.title}
      </h2>
      <AsyncBoundary state={detail} loadingText="Carregando detalhe…" emptyTitle="Playbook sem conteúdo">
        {(d) => <ParamsAndPreview key={playbook.id} playbook={playbook} detail={d} executions={executions} onRecord={onRecord} />}
      </AsyncBoundary>
    </section>
  );
}

export default function PlaybooksView({ playbooks, executions, onRecord, selectedId, onSelect }) {
  const [filters, setFilters] = useState({ environment: '', kind: '', status: '' });
  const [inner, setInner] = useState(null);
  const current = selectedId === undefined ? inner : selectedId;
  const select = onSelect ?? setInner;
  const runs = useMemo(() => lastByPlaybookEnv(executions.data ?? []), [executions.data]);

  return (
    <div>
      <Filters filters={filters} onChange={setFilters} />
      <AsyncBoundary
        state={playbooks}
        loadingText="Carregando playbooks…"
        emptyTitle="Nenhum playbook encontrado"
        emptyHint="Os playbooks vêm de vault/playbooks."
        isEmpty={(d) => d.length === 0}
      >
        {(all) => {
          const shown = all.filter((p) => Object.entries(filters).every(([k, v]) => !v || p[k] === v));
          const selected = all.find((p) => p.id === current) ?? null;
          return (
            <div className="space-y-4">
              {shown.length === 0 ? (
                <EmptyState title="Nenhum playbook com esses filtros" hint="Limpe um filtro para ver mais." />
              ) : (
                <div className="overflow-x-auto rounded border border-border bg-panel">
                  <table className="w-full min-w-[48rem] border-collapse text-left text-sm">
                    <caption className="sr-only">Playbooks</caption>
                    <thead className="bg-panel2 text-xs text-muted">
                      <tr>
                        <th scope="col" className="px-3 py-2 font-medium">Playbook</th>
                        <th scope="col" className="px-3 py-2 font-medium">Status</th>
                        <th scope="col" className="px-3 py-2 font-medium">Tipo</th>
                        <th scope="col" className="px-3 py-2 font-medium">Ambiente</th>
                        <th scope="col" className="px-3 py-2 font-medium">Última execução por ambiente</th>
                      </tr>
                    </thead>
                    <tbody>
                      {shown.map((p) => (
                        <tr key={p.id} className={`border-t border-border align-top ${p.id === current ? 'bg-panel2' : ''}`}>
                          <th scope="row" className="px-3 py-2 font-normal">
                            <button
                              type="button"
                              aria-pressed={p.id === current}
                              onClick={() => select(p.id === current ? null : p.id)}
                              className="font-mono text-xs text-accent underline-offset-2 hover:underline"
                            >
                              {p.id}
                            </button>
                            <span className="block">{p.title}</span>
                          </th>
                          <td className="px-3 py-2"><StatusBadge status={p.status} /></td>
                          <td className="px-3 py-2"><KindBadge kind={p.kind} /></td>
                          <td className="px-3 py-2">{envLabel(p.environment)}</td>
                          <td className="px-3 py-2"><LastRuns runs={runs[p.id]} executions={executions} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {selected ? <PlaybookDetail key={selected.id} playbook={selected} executions={executions} onRecord={onRecord} /> : null}
            </div>
          );
        }}
      </AsyncBoundary>
    </div>
  );
}

