import { useCallback, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import EnvToggle from './components/EnvToggle.jsx';
import ExecutionDialog from './components/ExecutionDialog.jsx';
import ExecutionsView from './components/ExecutionsView.jsx';
import HealthPanel from './components/HealthPanel.jsx';
import PlaybooksView from './components/PlaybooksView.jsx';
import RulesView from './components/RulesView.jsx';
import { useAsync } from './hooks/useAsync.js';
import { getAssessment, getExecutions, getPlaybooks, getRules, pick } from './lib/api.js';

const TABS = [
  { id: 'rules', label: 'Regras' },
  { id: 'playbooks', label: 'Playbooks' },
  { id: 'executions', label: 'Execuções' },
];

// Os dois ambientes sao avaliados juntos: cada regra mostra a saude do(s) ambiente(s) dos seus testes,
// e o painel mostra o ambiente escolhido no EnvToggle.
async function loadAssessments() {
  const [production, hml] = await Promise.all([getAssessment('production'), getAssessment('hml')]);
  if (!production.ok && !hml.ok) return production;
  return {
    ok: true,
    status: 200,
    data: { production: production.ok ? production.data : null, hml: hml.ok ? hml.data : null },
  };
}

export default function App() {
  const [env, setEnv] = useState('production');
  const [tab, setTab] = useState('rules');
  const [selectedPlaybook, setSelectedPlaybook] = useState(null);
  const [dialog, setDialog] = useState(null);
  const [notice, setNotice] = useState('');
  const opener = useRef(null);

  const rules = useAsync(() => getRules().then((r) => pick(r, 'rules')), []);
  const playbooks = useAsync(() => getPlaybooks().then((r) => pick(r, 'playbooks')), []);
  const executions = useAsync(() => getExecutions().then((r) => pick(r, 'executions')), []);
  const assessments = useAsync(loadAssessments, []);

  const refreshing = [rules, playbooks, executions, assessments].some((s) => s.loading);
  const refreshAll = () => {
    setNotice('');
    for (const s of [rules, playbooks, executions, assessments]) s.reload();
  };

  const openRecord = useCallback((spec, openerEl) => {
    opener.current = openerEl;
    setNotice('');
    setDialog(spec);
  }, []);

  const onKeyDownTabs = (e) => {
    const i = TABS.findIndex((t) => t.id === tab);
    let next = null;
    if (e.key === 'ArrowRight') next = (i + 1) % TABS.length;
    else if (e.key === 'ArrowLeft') next = (i - 1 + TABS.length) % TABS.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = TABS.length - 1;
    if (next === null) return;
    e.preventDefault();
    setTab(TABS[next].id);
    document.getElementById(`tab-${TABS[next].id}`)?.focus();
  };

  return (
    <div className="min-h-dvh">
      <header className="border-b border-border bg-rail">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-3 px-4 py-3">
          <h1 className="text-lg font-semibold tracking-tight">JEV — Evidência e luzes de teste</h1>
          <div className="flex flex-wrap items-center gap-3">
            <EnvToggle value={env} onChange={setEnv} />
            <button
              type="button"
              onClick={refreshAll}
              aria-busy={refreshing}
              className="inline-flex items-center gap-1.5 rounded border border-field-border px-3 py-1 text-sm hover:bg-panel2"
            >
              <RefreshCw className={`size-3.5 ${refreshing ? 'animate-spin' : ''}`} aria-hidden="true" />
              Atualizar
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-[1400px] gap-4 px-4 py-4 lg:grid-cols-[minmax(0,1fr)_21rem]">
        <div>
          <div role="tablist" aria-label="Seções do JEV" onKeyDown={onKeyDownTabs} className="mb-3 flex gap-1 border-b border-border">
            {TABS.map((t) => (
              <button
                key={t.id}
                id={`tab-${t.id}`}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                aria-controls={tab === t.id ? `panel-${t.id}` : undefined}
                tabIndex={tab === t.id ? 0 : -1}
                onClick={() => setTab(t.id)}
                className={`-mb-px border-b-2 px-3 py-1.5 text-sm ${
                  tab === t.id ? 'border-accent font-semibold text-text' : 'border-transparent text-muted hover:text-text'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <p aria-live="polite" className="mb-2 min-h-5 text-xs text-good">
            {notice}
          </p>

          <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
            {tab === 'rules' ? <RulesView rules={rules} assessments={assessments} /> : null}
            {tab === 'playbooks' ? (
              <PlaybooksView
                playbooks={playbooks}
                executions={executions}
                onRecord={openRecord}
                selectedId={selectedPlaybook}
                onSelect={setSelectedPlaybook}
              />
            ) : null}
            {tab === 'executions' ? (
              <ExecutionsView executions={executions} playbooks={playbooks} onRecord={openRecord} />
            ) : null}
          </div>
        </div>

        <aside className="lg:sticky lg:top-4 lg:self-start">
          <HealthPanel env={env} assessments={assessments} />
        </aside>
      </main>

      <ExecutionDialog
        open={dialog !== null}
        onClose={() => setDialog(null)}
        onSaved={() => {
          setNotice('Execução registrada.');
          executions.reload();
          rules.reload();
          assessments.reload();
        }}
        playbooks={playbooks.data ?? []}
        initial={dialog ?? {}}
        returnFocusRef={opener}
      />
    </div>
  );
}
