const OPTIONS = [
  { value: 'production', label: 'Produção' },
  { value: 'hml', label: 'Homologação' },
];

// Escolha do ambiente observado: radios nativos (setas funcionam), visual de botao segmentado.
export default function EnvToggle({ value, onChange }) {
  return (
    <fieldset className="m-0 flex items-center gap-2 border-0 p-0">
      <legend className="sr-only">Ambiente observado</legend>
      <span className="text-xs text-muted" aria-hidden="true">
        Ambiente
      </span>
      <div className="inline-flex overflow-hidden rounded border border-field-border">
        {OPTIONS.map((o) => (
          <label key={o.value} className="relative cursor-pointer">
            <input
              type="radio"
              name="jev-env"
              value={o.value}
              checked={value === o.value}
              onChange={() => onChange(o.value)}
              className="peer sr-only"
            />
            <span className="block px-3 py-1 text-sm text-muted peer-checked:bg-accent peer-checked:font-semibold peer-checked:text-accent-ink peer-focus-visible:outline-2 peer-focus-visible:outline-offset-[-2px] peer-focus-visible:outline-accent">
              {o.label}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
