import { lightMeta } from '../lib/lights.js';
import { ToneChip } from './ui.jsx';

// Luz de teste da regra: icone + rotulo em texto; o motivo fica visivel como texto de apoio.
export default function LightChip({ light, reason }) {
  const meta = lightMeta(light);
  return (
    <div className="flex flex-col items-start gap-1">
      <ToneChip tone={meta.tone} icon={meta.icon}>
        {meta.label}
      </ToneChip>
      {reason ? <span className="text-xs text-muted">{reason}</span> : null}
    </div>
  );
}
