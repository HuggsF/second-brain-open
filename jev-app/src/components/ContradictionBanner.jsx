import { ShieldAlert } from 'lucide-react';
import { envLabel } from '../lib/format.js';

// Regra com testes verdes enquanto a saude observada do ambiente esta vermelha.
export default function ContradictionBanner({ contradictions }) {
  if (!contradictions || contradictions.length === 0) return null;
  return (
    <section role="alert" className="mb-3 rounded border border-light-red/50 bg-panel2 px-3 py-2">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-danger">
        <ShieldAlert className="size-4 shrink-0" aria-hidden="true" />
        Contradição: teste verde, ambiente com falha
      </h2>
      <ul className="mt-1 space-y-0.5 text-sm">
        {contradictions.map((c) => (
          <li key={`${c.rule_id}-${c.environment}`}>
            <span className="font-mono">{c.rule_id}</span> em {envLabel(c.environment)}
            {c.reason ? <span className="text-muted">: {c.reason}</span> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
