import HealthChip from './HealthChip.jsx';
import { ErrorState, LoadingState } from './ui.jsx';
import { envLabel } from '../lib/format.js';

const NODE_LABELS = {
  process: 'Processo',
  internal: 'Interno',
  external: 'Externo',
  database: 'Banco de dados',
};

// Saude observada do ambiente escolhido no EnvToggle: resumo + os 4 aspectos.
export default function HealthPanel({ env, assessments }) {
  const a = assessments.data ? assessments.data[env] : null;
  let body;
  if (assessments.error) body = <ErrorState message={assessments.error.message} onRetry={assessments.reload} />;
  else if (assessments.loading && assessments.data == null) body = <LoadingState text="Carregando saúde do ambiente…" />;
  else if (!a) body = <p className="px-1 py-3 text-sm text-muted">Avaliação indisponível para este ambiente.</p>;
  else {
    body = (
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <HealthChip status={a.status} stale={a.stale === true} />
        </div>
        <p className="mt-1.5 text-sm">{a.reason}</p>
        {a.rules_available === false ? (
          <p className="mt-1 text-xs text-light-yellow">Regras indisponíveis: contradições não foram avaliadas.</p>
        ) : null}
        <ul className="mt-3 divide-y divide-border border-y border-border">
          {(a.nodes ?? []).map((n) => (
            <li key={n.id} className="grid grid-cols-[6.5rem_1fr] items-start gap-x-2 gap-y-0.5 py-1.5">
              <span className="text-xs text-muted">{NODE_LABELS[n.id] ?? n.id}</span>
              <span className="flex flex-col items-start gap-0.5">
                <HealthChip status={n.status} />
                {n.reason ? <span className="text-xs text-muted">{n.reason}</span> : null}
              </span>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  return (
    <section aria-labelledby="health-panel-title" className="rounded border border-border bg-panel p-3">
      <h2 id="health-panel-title" className="text-sm font-semibold">
        Saúde do ambiente
      </h2>
      <p className="mb-2 font-mono text-xs text-muted">{envLabel(env)}</p>
      {body}
    </section>
  );
}
