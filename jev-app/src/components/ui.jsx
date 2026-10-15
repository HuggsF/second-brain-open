// Pecas visuais pequenas e compartilhadas: icones, badges, estados de carregamento/vazio/erro.
import {
  CircleCheck,
  CircleHelp,
  CircleMinus,
  CircleX,
  HeartPulse,
  Inbox,
  LoaderCircle,
  OctagonAlert,
  TriangleAlert,
} from 'lucide-react';
import { resultMeta, statusMeta, kindMeta } from '../lib/format.js';

const ICONS = { CircleCheck, CircleHelp, CircleMinus, CircleX, HeartPulse, TriangleAlert };

export function Icon({ name, className = 'size-3.5' }) {
  const Cmp = ICONS[name] || CircleHelp;
  return <Cmp className={`${className} shrink-0`} aria-hidden="true" />;
}

// Classes completas e fixas (o Tailwind so gera o que aparece literalmente no codigo).
export const TONE_TEXT = {
  green: 'text-light-green',
  yellow: 'text-light-yellow',
  red: 'text-light-red',
  grey: 'text-light-grey',
};
export const TONE_BORDER = {
  green: 'border-light-green/40',
  yellow: 'border-light-yellow/40',
  red: 'border-light-red/40',
  grey: 'border-light-grey/40',
};

export const CHIP =
  'inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-xs font-medium leading-4 whitespace-nowrap';

export function ToneChip({ tone, icon, children }) {
  return (
    <span className={`${CHIP} ${TONE_TEXT[tone] ?? TONE_TEXT.grey} ${TONE_BORDER[tone] ?? TONE_BORDER.grey}`}>
      {icon ? <Icon name={icon} /> : null}
      {children}
    </span>
  );
}

export function ResultBadge({ result }) {
  const m = resultMeta(result);
  return (
    <ToneChip tone={m.tone} icon={m.icon}>
      {m.label}
    </ToneChip>
  );
}

export function StatusBadge({ status }) {
  const m = statusMeta(status);
  return <ToneChip tone={m.tone}>{m.label}</ToneChip>;
}

export function KindBadge({ kind }) {
  return (
    <span className={`${CHIP} border-border text-muted`}>{kindMeta(kind).label}</span>
  );
}

export function LoadingState({ text = 'Carregando…' }) {
  return (
    <div role="status" className="flex items-center gap-2 px-3 py-6 text-sm text-muted">
      <LoaderCircle className="size-4 animate-spin" aria-hidden="true" />
      <span>{text}</span>
    </div>
  );
}

export function EmptyState({ title, hint }) {
  return (
    <div className="flex flex-col items-center gap-1 px-3 py-8 text-center">
      <Inbox className="size-5 text-muted" aria-hidden="true" />
      <p className="text-sm font-medium">{title}</p>
      {hint ? <p className="text-xs text-muted">{hint}</p> : null}
    </div>
  );
}

export function ErrorState({ message, onRetry }) {
  return (
    <div role="alert" className="flex flex-col items-start gap-2 rounded border border-light-red/40 px-3 py-3">
      <p className="flex items-center gap-2 text-sm text-danger">
        <OctagonAlert className="size-4 shrink-0" aria-hidden="true" />
        <span>{message}</span>
      </p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="rounded border border-field-border px-2.5 py-1 text-sm hover:bg-panel2"
        >
          Tentar novamente
        </button>
      ) : null}
    </div>
  );
}

// Escolhe entre carregando / erro / vazio / conteudo para um estado de useAsync.
export function AsyncBoundary({ state, loadingText, emptyTitle, emptyHint, isEmpty, children }) {
  if (state.error) return <ErrorState message={state.error.message} onRetry={state.reload} />;
  if (state.loading && state.data == null) return <LoadingState text={loadingText} />;
  const empty = state.data == null || (isEmpty ? isEmpty(state.data) : false);
  if (empty) return <EmptyState title={emptyTitle} hint={emptyHint} />;
  return children(state.data);
}
