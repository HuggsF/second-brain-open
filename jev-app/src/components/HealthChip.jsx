import { healthMeta } from '../lib/lights.js';
import { ToneChip } from './ui.jsx';

// Saude observada de um ambiente ou aspecto. `stale` e dito em texto, nunca so por cor.
export default function HealthChip({ status, stale = false }) {
  const meta = healthMeta(status);
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <ToneChip tone={meta.tone} icon={meta.icon}>
        {meta.label}
      </ToneChip>
      {stale ? <span className="text-xs text-light-yellow">dados desatualizados</span> : null}
    </span>
  );
}
