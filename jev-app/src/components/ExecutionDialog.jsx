import { useEffect, useId, useRef, useState } from 'react';
import { postExecution } from '../lib/api.js';
import { validateExecution } from '../lib/validation.js';
import { ENVIRONMENTS, envLabel, resultMeta } from '../lib/format.js';

const RESULTS = ['pass', 'fail', 'error', 'skipped'];
const FIELD = 'w-full rounded border border-field-border bg-bg px-2 py-1.5 text-sm text-text';
const FIELD_ERROR = 'border-light-red';

function serverMessage(res) {
  const data = res.data || {};
  if (res.status === 0) return 'Sem conexão com o servidor. Os campos foram mantidos; tente novamente.';
  if (res.status === 400 && data.error === 'VALIDATION_FAILED') {
    return `O servidor recusou o registro: ${data.detail ?? 'dados inválidos'}`;
  }
  if (res.status === 400 && data.error === 'MISSING_FIELD') return `Campo obrigatório ausente: ${data.field}`;
  if (res.status === 409) return 'Esta execução já foi importada (duplicada).';
  if (res.status === 503) return 'Banco de evidências indisponível. Os campos foram mantidos; tente novamente.';
  if (res.status === 401) return 'Sessão local expirada. Gere um novo link de conexão.';
  return `Não foi possível registrar (HTTP ${res.status}).`;
}

function Field({ id, label, error, hint, children }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-muted">
        {label}
      </label>
      {children}
      {hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} className="text-xs text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}

function ExecutionForm({ playbooks, initial, onClose, onSaved, titleId }) {
  const uid = useId();
  const id = (name) => `${uid}-${name}`;
  const params = initial.params && Object.keys(initial.params).length > 0 ? initial.params : null;
  const initialPb = playbooks.find((p) => p.id === initial.playbookId);
  const [form, setForm] = useState({
    playbookId: initial.playbookId ?? '',
    environment: initial.environment ?? initialPb?.environment ?? 'hml',
    result: 'pass',
    summary: params ? `Parâmetros Liquid: ${JSON.stringify(params)}` : '',
    evidenceRef: '',
    commitSha: '',
    runId: '',
  });
  const [errors, setErrors] = useState({});
  const [message, setMessage] = useState({ kind: '', text: '' });
  const [submitting, setSubmitting] = useState(false);
  const formRef = useRef(null);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const onPlaybook = (e) => {
    const pb = playbooks.find((p) => p.id === e.target.value);
    setForm((f) => ({ ...f, playbookId: e.target.value, environment: pb?.environment ?? f.environment }));
  };

  const describedBy = (name, hasHint) =>
    [errors[name] ? `${id(name)}-error` : null, hasHint ? `${id(name)}-hint` : null].filter(Boolean).join(' ') || undefined;

  async function submit(e) {
    e.preventDefault();
    if (submitting) return;
    const v = validateExecution(form);
    const found = { ...v.errors };
    if (!form.playbookId) found.playbookId = 'Escolha um playbook.';
    setErrors(found);
    const first = ['playbookId', 'summary', 'evidenceRef', 'commitSha', 'runId'].find((k) => found[k]);
    if (first) {
      setMessage({ kind: 'error', text: 'Corrija os campos destacados.' });
      formRef.current?.querySelector(`[data-field="${first}"]`)?.focus();
      return;
    }
    setSubmitting(true);
    setMessage({ kind: 'info', text: 'Registrando…' });
    const body = {
      playbook_id: form.playbookId,
      result: form.result,
      environment: form.environment,
      summary: form.summary.trim(),
      evidence_ref: form.evidenceRef.trim(),
      source: 'jev',
    };
    if (form.commitSha.trim()) body.commit_sha = form.commitSha.trim();
    if (form.runId.trim()) body.run_id = form.runId.trim();
    const res = await postExecution(body);
    setSubmitting(false);
    if (res.ok) {
      setMessage({ kind: 'info', text: 'Execução registrada.' });
      onSaved?.(res.data);
      onClose();
    } else {
      setMessage({ kind: 'error', text: serverMessage(res) });
    }
  }

  return (
    <form ref={formRef} noValidate onSubmit={submit} className="flex flex-col gap-3 p-4">
      <h2 id={titleId} className="text-base font-semibold">
        Registrar execução
      </h2>

      <Field id={id('playbook')} label="Playbook" error={errors.playbookId}>
        <select
          id={id('playbook')}
          data-field="playbookId"
          value={form.playbookId}
          onChange={onPlaybook}
          aria-invalid={errors.playbookId ? 'true' : undefined}
          aria-describedby={describedBy('playbook')}
          className={`${FIELD} ${errors.playbookId ? FIELD_ERROR : ''}`}
        >
          <option value="">Selecione…</option>
          {playbooks.map((p) => (
            <option key={p.id} value={p.id}>
              {p.id} — {p.title}
            </option>
          ))}
        </select>
      </Field>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field id={id('env')} label="Ambiente">
          <select id={id('env')} value={form.environment} onChange={set('environment')} className={FIELD}>
            {ENVIRONMENTS.map((env) => (
              <option key={env} value={env}>
                {envLabel(env)}
              </option>
            ))}
          </select>
        </Field>
        <Field id={id('result')} label="Resultado">
          <select id={id('result')} value={form.result} onChange={set('result')} className={FIELD}>
            {RESULTS.map((r) => (
              <option key={r} value={r}>
                {resultMeta(r).label}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <Field id={id('summary')} label="Resumo *" error={errors.summary}>
        <textarea
          id={id('summary')}
          data-field="summary"
          rows={3}
          value={form.summary}
          onChange={set('summary')}
          aria-invalid={errors.summary ? 'true' : undefined}
          aria-describedby={describedBy('summary')}
          className={`${FIELD} ${errors.summary ? FIELD_ERROR : ''}`}
        />
      </Field>

      <Field
        id={id('evidenceRef')}
        label="Referência de evidência *"
        error={errors.evidenceRef}
        hint="caminho:linha, URL http(s) ou id de ticket (DEM-12)"
      >
        <input
          id={id('evidenceRef')}
          data-field="evidenceRef"
          data-autofocus
          type="text"
          value={form.evidenceRef}
          onChange={set('evidenceRef')}
          aria-invalid={errors.evidenceRef ? 'true' : undefined}
          aria-describedby={describedBy('evidenceRef', true)}
          className={`${FIELD} font-mono ${errors.evidenceRef ? FIELD_ERROR : ''}`}
        />
      </Field>

      <div className="grid gap-3 sm:grid-cols-2">
        <Field id={id('commitSha')} label="Commit (opcional)" error={errors.commitSha}>
          <input
            id={id('commitSha')}
            data-field="commitSha"
            type="text"
            value={form.commitSha}
            onChange={set('commitSha')}
            aria-invalid={errors.commitSha ? 'true' : undefined}
            aria-describedby={describedBy('commitSha')}
            className={`${FIELD} font-mono ${errors.commitSha ? FIELD_ERROR : ''}`}
          />
        </Field>
        <Field id={id('runId')} label="ID da execução (opcional)" error={errors.runId}>
          <input
            id={id('runId')}
            data-field="runId"
            type="text"
            value={form.runId}
            onChange={set('runId')}
            aria-invalid={errors.runId ? 'true' : undefined}
            aria-describedby={describedBy('runId')}
            className={`${FIELD} font-mono ${errors.runId ? FIELD_ERROR : ''}`}
          />
        </Field>
      </div>

      <p aria-live="polite" className={`min-h-5 text-sm ${message.kind === 'error' ? 'text-danger' : 'text-muted'}`}>
        {message.text}
      </p>

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-field-border px-3 py-1.5 text-sm hover:bg-panel2"
        >
          Cancelar
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="rounded bg-accent px-3 py-1.5 text-sm font-semibold text-accent-ink hover:opacity-90 disabled:opacity-60"
        >
          Registrar
        </button>
      </div>
    </form>
  );
}

// Registro de execucao em <dialog> nativo (showModal): foco entra no dialogo ao abrir e volta ao
// elemento de origem ao fechar; Esc e Cancelar fecham. O formulario so existe enquanto aberto.
export default function ExecutionDialog({ open, onClose, onSaved, playbooks = [], initial = {}, returnFocusRef }) {
  const ref = useRef(null);
  const titleId = useId();
  const wasOpen = useRef(false);
  const lastActive = useRef(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open) {
      if (!wasOpen.current) lastActive.current = document.activeElement;
      wasOpen.current = true;
      if (!dialog.open) dialog.showModal();
      dialog.querySelector('[data-autofocus]')?.focus();
    } else if (wasOpen.current) {
      wasOpen.current = false;
      if (dialog.open) dialog.close();
      const target = returnFocusRef?.current?.isConnected ? returnFocusRef.current : lastActive.current;
      target?.focus?.();
    }
  }, [open, returnFocusRef]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={() => onClose()}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.preventDefault();
          onClose();
        }
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className="m-auto max-h-[calc(100dvh-2rem)] w-[min(36rem,calc(100vw-2rem))] overflow-y-auto rounded-lg border border-border bg-panel p-0 text-text backdrop:bg-black/60"
    >
      {open ? (
        <ExecutionForm playbooks={playbooks} initial={initial} onClose={onClose} onSaved={onSaved} titleId={titleId} />
      ) : null}
    </dialog>
  );
}
