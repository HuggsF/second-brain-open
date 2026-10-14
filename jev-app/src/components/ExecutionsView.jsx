import { useMemo } from 'react';
import { ClipboardPlus } from 'lucide-react';
import { AsyncBoundary, ResultBadge, TONE_TEXT } from './ui.jsx';
import { envLabel, formatDateTime, parseTs, relativeTime, resultMeta, sortByTsDesc } from '../lib/format.js';

const MAX_POINTS = 40;
const Y_BY_RESULT = { pass: 14, skipped: 32, error: 32, fail: 50 };

// Linha do tempo: um ponto por execucao (mais antiga a esquerda), altura pelo resultado.
// So atributos SVG e classes; sem atributo style.
export function ExecutionTimeline({ executions }) {
  const points = sortByTsDesc(executions).slice(0, MAX_POINTS).reverse();
  const n = points.length;
  const x = (i) => 12 + (n === 1 ? 0 : (i * 376) / (n - 1));
  const path = points.map((p, i) => `${x(i)},${Y_BY_RESULT[p.result] ?? 32}`).join(' ');
  return (
    <figure className="mb-3 rounded border border-border bg-panel px-3 py-2">
      <figcaption className="mb-1 text-xs text-muted">
        Linha do tempo (alto = aprovada, meio = erro ou ignorada, baixo = falhou)
      </figcaption>
      <svg
        viewBox="0 0 400 64"
        role="img"
        aria-label={`Linha do tempo das execuções: ${n} registros, do mais antigo ao mais novo`}
        className="h-16 w-full"
        preserveAspectRatio="none"
      >
        <line x1="0" y1="32" x2="400" y2="32" className="stroke-border" strokeWidth="1" strokeDasharray="3 3" />
        <polyline points={path} fill="none" className="stroke-border" strokeWidth="1" />
        {points.map((p, i) => {
          const m = resultMeta(p.result);
          return (
            <circle key={`${p.playbook_id}-${p.ts}-${i}`} cx={x(i)} cy={Y_BY_RESULT[p.result] ?? 32} r="4.5" fill="currentColor" className={TONE_TEXT[m.tone]}>
              <title>{`${p.playbook_id} · ${m.label} · ${formatDateTime(p.ts)}`}</title>
            </circle>
          );
        })}
      </svg>
    </figure>
  );
}

function RecordButton({ onRecord }) {
  return (
    <button
      type="button"
      onClick={(e) => onRecord({}, e.currentTarget)}
      className="inline-flex items-center gap-1.5 rounded bg-accent px-3 py-1.5 text-sm font-semibold text-accent-ink hover:opacity-90"
    >
      <ClipboardPlus className="size-4" aria-hidden="true" />
      Registrar execução
    </button>
  );
}

export default function ExecutionsView({ executions, playbooks, onRecord }) {
  const titles = useMemo(
    () => Object.fromEntries((playbooks?.data ?? []).map((p) => [p.id, p.title])),
    [playbooks?.data],
  );
  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">Execuções, da mais recente para a mais antiga</h2>
        <RecordButton onRecord={onRecord} />
      </div>
      <AsyncBoundary
        state={executions}
        loadingText="Carregando execuções…"
        emptyTitle="Nenhuma execução registrada"
        emptyHint="Use Registrar execução depois de rodar um playbook."
        isEmpty={(d) => d.length === 0}
      >
        {(data) => {
          const rows = sortByTsDesc(data);
          return (
            <>
              {rows.length >= 2 ? (
                <ExecutionTimeline executions={rows} />
              ) : (
                <p className="mb-3 text-xs text-muted">A linha do tempo aparece com 2 ou mais execuções.</p>
              )}
              <div className="overflow-x-auto rounded border border-border bg-panel">
                <table className="w-full min-w-[56rem] border-collapse text-left text-sm">
                  <caption className="sr-only">Execuções de playbooks</caption>
                  <thead className="bg-panel2 text-xs text-muted">
                    <tr>
                      <th scope="col" className="px-3 py-2 font-medium">Resultado</th>
                      <th scope="col" className="px-3 py-2 font-medium">Playbook</th>
                      <th scope="col" className="px-3 py-2 font-medium">Ambiente</th>
                      <th scope="col" className="px-3 py-2 font-medium">Quando</th>
                      <th scope="col" className="px-3 py-2 font-medium">Resumo</th>
                      <th scope="col" className="px-3 py-2 font-medium">Evidência</th>
                      <th scope="col" className="px-3 py-2 font-medium">Commit</th>
                      <th scope="col" className="px-3 py-2 font-medium">Run</th>
                      <th scope="col" className="px-3 py-2 font-medium">Origem</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((e, i) => (
                      <tr key={`${e.playbook_id}-${e.ts}-${i}`} className="border-t border-border align-top">
                        <td className="px-3 py-2"><ResultBadge result={e.result} /></td>
                        <td className="px-3 py-2">
                          <span className="font-mono text-xs text-accent">{e.playbook_id}</span>
                          {titles[e.playbook_id] ? <span className="block text-xs text-muted">{titles[e.playbook_id]}</span> : null}
                        </td>
                        <td className="px-3 py-2">{envLabel(e.environment)}</td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          <time dateTime={e.ts} className="font-mono text-xs tabular-nums">{formatDateTime(e.ts)}</time>
                          <span className="block text-xs text-muted">{Number.isNaN(parseTs(e.ts)) ? '' : relativeTime(e.ts)}</span>
                        </td>
                        <td className="px-3 py-2">{e.summary}</td>
                        <td className="px-3 py-2 font-mono text-xs break-all">{e.evidence_ref || '—'}</td>
                        <td className="px-3 py-2 font-mono text-xs">{e.commit_sha ? e.commit_sha.slice(0, 7) : '—'}</td>
                        <td className="px-3 py-2 font-mono text-xs break-all">{e.run_id || '—'}</td>
                        <td className="px-3 py-2 text-xs text-muted">{e.source || e._origin || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          );
        }}
      </AsyncBoundary>
    </div>
  );
}
