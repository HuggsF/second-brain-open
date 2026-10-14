import LightChip from './LightChip.jsx';
import HealthChip from './HealthChip.jsx';
import ContradictionBanner from './ContradictionBanner.jsx';
import { AsyncBoundary } from './ui.jsx';
import { envLabel } from '../lib/format.js';

const OBSERVED = ['production', 'hml'];

// Ambientes em que os playbooks de teste da regra rodam e que o Hub observa.
const observedEnvs = (rule) => OBSERVED.filter((e) => (rule.test_environments ?? []).includes(e));

function HealthCell({ rule, assessments }) {
  const envs = observedEnvs(rule);
  if (envs.length === 0) return <span className="text-xs text-muted">Sem ambiente observado</span>;
  if (assessments.loading && assessments.data == null) {
    return <span className="text-xs text-muted">Carregando saúde…</span>;
  }
  return (
    <div className="flex flex-col gap-1.5">
      {envs.map((env) => {
        const a = assessments.data ? assessments.data[env] : null;
        return (
          <div key={env} className="flex flex-col items-start gap-0.5">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted">{envLabel(env)}</span>
              {a ? (
                <HealthChip status={a.status} stale={a.stale === true} />
              ) : (
                <span className="text-xs text-muted">Saúde indisponível</span>
              )}
            </div>
            {a && a.status !== 'green' && a.reason ? <span className="text-xs text-muted">{a.reason}</span> : null}
          </div>
        );
      })}
    </div>
  );
}

// Duas luzes por regra, sempre separadas: o teste (LightChip) e a saude do ambiente (HealthChip).
export default function RulesView({ rules, assessments }) {
  const contradictions = Object.values(assessments.data ?? {}).flatMap((a) => (a && a.contradictions) || []);
  return (
    <div>
      <ContradictionBanner contradictions={contradictions} />
      <AsyncBoundary
        state={rules}
        loadingText="Carregando regras…"
        emptyTitle="Nenhuma regra encontrada"
        emptyHint="As regras vêm de vault/rules; confira se a pasta tem definições ativas."
        isEmpty={(d) => d.length === 0}
      >
        {(data) => (
          <div className="overflow-x-auto rounded border border-border bg-panel">
            <table className="w-full min-w-[44rem] border-collapse text-left text-sm">
              <caption className="sr-only">Regras com luz de teste e saúde do ambiente</caption>
              <thead className="bg-panel2 text-xs text-muted">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">Regra</th>
                  <th scope="col" className="px-3 py-2 font-medium">Luz de teste</th>
                  <th scope="col" className="px-3 py-2 font-medium">Saúde do ambiente de teste</th>
                  <th scope="col" className="px-3 py-2 font-medium">Playbooks de teste</th>
                </tr>
              </thead>
              <tbody>
                {data.map((rule) => (
                  <tr key={rule.id} className="border-t border-border align-top">
                    <th scope="row" className="px-3 py-2 font-normal">
                      <span className="font-mono text-xs text-accent">{rule.id}</span>
                      <span className="block">{rule.title}</span>
                    </th>
                    <td className="px-3 py-2">
                      <LightChip light={rule.light} reason={rule.light_reason} />
                    </td>
                    <td className="px-3 py-2">
                      <HealthCell rule={rule} assessments={assessments} />
                    </td>
                    <td className="px-3 py-2 font-mono text-xs text-muted">
                      {(rule.test_playbooks ?? []).length ? rule.test_playbooks.join(', ') : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </AsyncBoundary>
    </div>
  );
}
