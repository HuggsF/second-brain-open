/**
 * jev-ui.js — Joint Evidence View (JEV)
 *
 * Visão cruzada Playbooks × Execuções × Observabilidade do ambiente-alvo.
 * Detecta contradições entre resultado de execução (pass/fail) e estado
 * de observabilidade real do ambiente (métricas de BFF ou fallback local).
 *
 * Padrão: window.BrainJEV.render(main, api)
 */
(function () {
  'use strict';

  // ── Constantes ─────────────────────────────────────────────────────────────

  const RESULT_META = {
    pass:    { label: 'PASS',    cls: 'jev-pass',    icon: '✓' },
    fail:    { label: 'FAIL',    cls: 'jev-fail',    icon: '✗' },
    error:   { label: 'ERROR',   cls: 'jev-error',   icon: '⚠' },
    skipped: { label: 'SKIP',    cls: 'jev-skipped', icon: '—' },
  };

  const ENV_META = {
    production: { label: 'Production', icon: '🔴', obsPath: '/v1/observation/production' },
    hml:        { label: 'Homologação', icon: '🟡', obsPath: '/v1/observation/hml' },
    local:      { label: 'Local',       icon: '🟢', obsPath: null },
  };

  const STATUS_META = {
    active:     { label: 'Ativo',       cls: 'jev-badge-active' },
    draft:      { label: 'Rascunho',    cls: 'jev-badge-draft' },
    deprecated: { label: 'Depreciado',  cls: 'jev-badge-deprecated' },
  };

  // ── DOM helpers ─────────────────────────────────────────────────────────────

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
      else if (k === 'class') node.className = v;
      else node.setAttribute(k, v);
    }
    for (const child of children) {
      if (child == null) continue;
      node.append(typeof child === 'string' ? document.createTextNode(child) : child);
    }
    return node;
  }

  function fmtDate(iso) {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
    } catch { return iso; }
  }

  function resultBadge(result) {
    const m = RESULT_META[result] || { label: result || '?', cls: 'jev-skipped', icon: '?' };
    return el('span', { class: `jev-result-badge ${m.cls}` }, m.icon, ' ', m.label);
  }

  function spinnerEl(text = 'Carregando…') {
    return el('div', { class: 'jev-loading' }, el('span', { class: 'jev-spinner' }), ' ', text);
  }

  // ── API calls ───────────────────────────────────────────────────────────────

  async function fetchPlaybooks() {
    const r = await fetch('/api/playbooks/');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    return d.playbooks || [];
  }

  async function fetchExecutions(pbId) {
    const url = pbId ? `/api/playbooks/${encodeURIComponent(pbId)}/executions` : '/api/playbooks/executions';
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const d = await r.json();
    return d.executions || [];
  }

  async function postExecution(payload) {
    const r = await fetch('/api/playbooks/executions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
    return d;
  }

  async function fetchObsSnapshot(env) {
    const meta = ENV_META[env];
    if (!meta || !meta.obsPath) return null;
    try {
      const r = await fetch(meta.obsPath);
      if (!r.ok) return { _unavailable: true, status: r.status };
      return await r.json();
    } catch {
      return { _unavailable: true, status: 'network' };
    }
  }

  // ── Contradiction detection ──────────────────────────────────────────────────

  function detectContradictions(executions, obs) {
    if (!obs || obs._unavailable) return [];
    const flags = [];
    const lastPass = executions.find(e => e.result === 'pass');
    if (!lastPass) return [];
    // Check critical obs metrics
    if (obs.db?.failed > 0) flags.push(`db.failed = ${obs.db.failed} ≠ 0`);
    if (obs.external?.status && obs.external.status !== 'ok') flags.push(`external.status = ${obs.external.status}`);
    if (obs.process?.status && obs.process.status !== 'ok') flags.push(`process.status = ${obs.process.status}`);
    if (obs.internal?.status && obs.internal.status !== 'ok') flags.push(`internal.status = ${obs.internal.status}`);
    return flags;
  }

  // ── Record execution modal ──────────────────────────────────────────────────

  function openRecordModal(pb, onSaved) {
    const overlay = el('div', { class: 'jev-modal-overlay' });
    const modal = el('div', { class: 'jev-modal', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'jev-modal-title' });

    const envOptions = Object.entries(ENV_META).map(([k, v]) =>
      el('option', { value: k }, v.icon + ' ' + v.label)
    );
    const resOptions = ['pass', 'fail', 'error', 'skipped'].map(r =>
      el('option', { value: r }, RESULT_META[r].label)
    );

    const selEnv = el('select', { class: 'jev-input', id: 'jev-modal-env' }, ...envOptions);
    selEnv.value = pb.environment || 'local';
    const selRes = el('select', { class: 'jev-input', id: 'jev-modal-result' }, ...resOptions);
    const inpSummary = el('textarea', { class: 'jev-input', id: 'jev-modal-summary', rows: '3', placeholder: 'Resumo da execução…' });
    const inpRef = el('input', { class: 'jev-input', id: 'jev-modal-ref', type: 'text', placeholder: 'vault/sistemas/…:57 (opcional)' });
    const inpTrace = el('input', { class: 'jev-input', id: 'jev-modal-trace', type: 'text', placeholder: 'trace-id (opcional)' });
    const errMsg = el('p', { class: 'jev-modal-error' });

    const btnSave = el('button', { class: 'jev-btn jev-btn-primary', onclick: async () => {
      errMsg.textContent = '';
      const summary = inpSummary.value.trim();
      if (!summary) { errMsg.textContent = 'Resumo é obrigatório.'; return; }
      btnSave.disabled = true;
      btnSave.textContent = 'Registrando…';
      try {
        await postExecution({
          playbook_id: pb.id,
          result: selRes.value,
          environment: selEnv.value,
          summary,
          evidence_ref: inpRef.value.trim(),
          trace_id: inpTrace.value.trim(),
        });
        overlay.remove();
        onSaved();
      } catch (e) {
        errMsg.textContent = e.message;
        btnSave.disabled = false;
        btnSave.textContent = 'Registrar';
      }
    }}, 'Registrar');

    const btnCancel = el('button', { class: 'jev-btn', onclick: () => overlay.remove() }, 'Cancelar');

    modal.append(
      el('h3', { id: 'jev-modal-title', class: 'jev-modal-title' }, '📋 Registrar Execução'),
      el('p', { class: 'jev-modal-pb' }, pb.id, ' — ', pb.title || pb.id),
      el('label', { class: 'jev-label', for: 'jev-modal-env' }, 'Ambiente'),
      selEnv,
      el('label', { class: 'jev-label', for: 'jev-modal-result' }, 'Resultado'),
      selRes,
      el('label', { class: 'jev-label', for: 'jev-modal-summary' }, 'Resumo *'),
      inpSummary,
      el('label', { class: 'jev-label', for: 'jev-modal-ref' }, 'Referência de evidência'),
      inpRef,
      el('label', { class: 'jev-label', for: 'jev-modal-trace' }, 'Trace ID'),
      inpTrace,
      errMsg,
      el('div', { class: 'jev-modal-actions' }, btnCancel, btnSave),
    );
    overlay.append(modal);
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
    document.body.append(overlay);
    inpSummary.focus();
  }

  // ── Column 3: Observability snapshot ────────────────────────────────────────

  function renderObsCol(container, env, contradictions) {
    container.replaceChildren();
    const envMeta = ENV_META[env] || { label: env, icon: '⬜', obsPath: null };

    if (!envMeta.obsPath) {
      container.append(el('p', { class: 'jev-obs-note' },
        envMeta.icon, ' Ambiente local — sem snapshot de observabilidade ao vivo.'
      ));
      return;
    }

    const loading = spinnerEl('Buscando snapshot…');
    container.append(loading);

    fetchObsSnapshot(env).then(obs => {
      loading.remove();
      if (!obs) {
        container.append(el('p', { class: 'jev-obs-note' }, 'Sem dados de obs para este ambiente.'));
        return;
      }
      if (obs._unavailable) {
        container.append(
          el('p', { class: 'jev-obs-unavailable' }, '⚠ BFF não disponível (HTTP ', String(obs.status), ')'),
          el('p', { class: 'jev-obs-note' },
            'Para ver dados ao vivo, acesse a aba ',
            el('a', { href: '#page=observability', class: 'jev-link' }, '📡 Observabilidade'), '.'
          )
        );
        return;
      }

      // Render key metrics
      const metrics = [
        ['db.pending',   obs.db?.pending,  'Fila pendente'],
        ['db.failed',    obs.db?.failed,   'Falhas DB'],
        ['process',      obs.process?.status, 'Processo'],
        ['internal',     obs.internal?.status, 'BFF interno'],
        ['external',     obs.external?.status, 'Serviços externos'],
      ];

      const rows = metrics.map(([key, val, label]) => {
        if (val == null) return null;
        const bad = (key === 'db.failed' && Number(val) > 0) ||
                    (['process', 'internal', 'external'].includes(key) && val !== 'ok');
        return el('div', { class: `jev-obs-metric ${bad ? 'jev-obs-bad' : 'jev-obs-ok'}` },
          el('span', { class: 'jev-obs-metric-label' }, label),
          el('span', { class: 'jev-obs-metric-val' }, String(val))
        );
      }).filter(Boolean);

      container.append(el('div', { class: 'jev-obs-metrics' }, ...rows));

      if (contradictions && contradictions.length > 0) {
        container.append(
          el('div', { class: 'jev-contradiction' },
            el('strong', {}, '⚡ Contradições detectadas:'),
            el('ul', {}, ...contradictions.map(c => el('li', {}, c)))
          )
        );
      }
    }).catch(err => {
      loading.remove();
      container.append(el('p', { class: 'jev-obs-unavailable' }, '⚠ Erro: ', err.message));
    });
  }

  // ── Column 2: Executions list ────────────────────────────────────────────────

  function renderExecutionsCol(container, pb, obsColEl, onRefresh) {
    container.replaceChildren();

    const header = el('div', { class: 'jev-col-header' },
      el('h3', { class: 'jev-col-title' }, '🧪 Execuções'),
      el('button', { class: 'jev-btn jev-btn-small', onclick: () => openRecordModal(pb, onRefresh) }, '+ Registrar')
    );
    container.append(header);

    const loading = spinnerEl();
    container.append(loading);

    fetchExecutions(pb.id).then(execs => {
      loading.remove();
      if (!execs.length) {
        container.append(el('p', { class: 'jev-empty' }, 'Nenhuma execução registrada.'));
        // Still render obs col
        renderObsCol(obsColEl, pb.environment, []);
        return;
      }

      const contradictions = [];
      // We'll detect contradictions after obs loads — store latest pass
      const envMeta = ENV_META[pb.environment];

      const list = el('div', { class: 'jev-exec-list' });
      for (const ex of execs) {
        const item = el('div', { class: `jev-exec-item ${ex.result === 'fail' || ex.result === 'error' ? 'jev-exec-bad' : ''}` },
          el('div', { class: 'jev-exec-top' },
            resultBadge(ex.result),
            el('span', { class: 'jev-exec-env' }, (ENV_META[ex.environment]?.icon || '⬜'), ' ', ex.environment || '—'),
            el('span', { class: 'jev-exec-ts' }, fmtDate(ex.ts)),
          ),
          ex.summary ? el('p', { class: 'jev-exec-summary' }, ex.summary) : null,
          ex.evidence_ref ? el('p', { class: 'jev-exec-ref' }, '📎 ', ex.evidence_ref) : null,
          ex.trace_id    ? el('p', { class: 'jev-exec-trace' }, '🔍 trace: ', ex.trace_id) : null,
          el('span', { class: 'jev-exec-origin' }, '_origin: ', ex._origin || '?'),
        );
        list.append(item);
      }
      container.append(list);

      // Render obs column, then detect contradictions
      if (envMeta?.obsPath) {
        fetchObsSnapshot(pb.environment).then(obs => {
          const flags = detectContradictions(execs, obs);
          renderObsColWithData(obsColEl, pb.environment, obs, flags);
          // Mark exec items that have contradictions
          if (flags.length) {
            const passItems = list.querySelectorAll('.jev-exec-item:not(.jev-exec-bad)');
            passItems.forEach(item => item.classList.add('jev-exec-contradicted'));
          }
        });
      } else {
        renderObsCol(obsColEl, pb.environment, []);
      }
    }).catch(err => {
      loading.remove();
      container.append(el('p', { class: 'jev-empty' }, '⚠ Erro ao carregar execuções: ', err.message));
    });
  }

  function renderObsColWithData(container, env, obs, contradictions) {
    container.replaceChildren();
    const envMeta = ENV_META[env] || { label: env, icon: '⬜', obsPath: null };

    if (!envMeta.obsPath) {
      container.append(el('p', { class: 'jev-obs-note' },
        envMeta.icon, ' Ambiente local — sem snapshot de observabilidade ao vivo.'
      ));
      return;
    }

    if (!obs || obs._unavailable) {
      container.append(
        el('p', { class: 'jev-obs-unavailable' }, '⚠ BFF não disponível (HTTP ', obs ? String(obs.status) : 'network', ')'),
        el('p', { class: 'jev-obs-note' },
          'Para ver dados ao vivo, acesse a aba ',
          el('a', { href: '#page=observability', class: 'jev-link' }, '📡 Observabilidade'), '.'
        )
      );
      return;
    }

    const metrics = [
      ['db.failed',    obs.db?.failed,           'Falhas DB'],
      ['db.pending',   obs.db?.pending,           'Fila pendente'],
      ['process',      obs.process?.status,       'Processo'],
      ['internal',     obs.internal?.status,      'BFF interno'],
      ['external',     obs.external?.status,      'Serviços externos'],
      ['workerEnabled',obs.internal?.workerEnabled, 'Worker'],
    ];

    const rows = metrics.map(([key, val, label]) => {
      if (val == null) return null;
      const bad = (key === 'db.failed' && Number(val) > 0) ||
                  (['process', 'internal', 'external'].includes(key) && val !== 'ok');
      return el('div', { class: `jev-obs-metric ${bad ? 'jev-obs-bad' : 'jev-obs-ok'}` },
        el('span', { class: 'jev-obs-metric-label' }, label),
        el('span', { class: 'jev-obs-metric-val' }, String(val))
      );
    }).filter(Boolean);

    container.append(el('div', { class: 'jev-obs-metrics' }, ...rows));

    if (contradictions && contradictions.length > 0) {
      container.append(
        el('div', { class: 'jev-contradiction' },
          el('strong', {}, '⚡ Contradições detectadas:'),
          el('ul', {}, ...contradictions.map(c => el('li', {}, c)))
        )
      );
    } else {
      container.append(el('p', { class: 'jev-obs-ok-msg' }, '✓ Sem contradições detectadas.'));
    }
  }

  // ── Column 1: Playbook list ─────────────────────────────────────────────────

  function renderPlaybookList(listEl, execCol, obsCol, playbooks, selected, onSelect) {
    listEl.replaceChildren();
    for (const pb of playbooks) {
      const sm = STATUS_META[pb.status] || STATUS_META.draft;
      const envMeta = ENV_META[pb.environment] || { icon: '⬜' };
      const item = el('button', {
        class: `jev-pb-item ${selected?.id === pb.id ? 'jev-pb-selected' : ''}`,
        onclick: () => onSelect(pb),
      },
        el('div', { class: 'jev-pb-row' },
          el('span', { class: 'jev-pb-id' }, pb.id),
          el('span', { class: `jev-pb-badge ${sm.cls}` }, sm.label),
          el('span', { class: 'jev-pb-env' }, envMeta.icon),
        ),
        el('span', { class: 'jev-pb-title' }, pb.title || pb.id),
      );
      listEl.append(item);
    }
  }

  // ── Main render ─────────────────────────────────────────────────────────────

  function render(main, api) {
    main.replaceChildren();

    // Page header
    const head = el('div', { class: 'jev-page-header' },
      el('h2', { class: 'jev-page-title' }, '📊 Joint Evidence View'),
      el('p', { class: 'jev-page-subtitle' },
        'Visão cruzada Playbooks × Execuções × Observabilidade do ambiente-alvo. ',
        'Destaca contradições entre resultado registrado e estado real do ambiente.'
      )
    );
    main.append(head);

    // Three-column layout
    const layout = el('div', { class: 'jev-layout' });

    // Col 1 — Playbook list
    const col1 = el('div', { class: 'jev-col jev-col-playbooks' });
    col1.append(el('h3', { class: 'jev-col-title' }, '📋 Playbooks'));
    const pbListEl = el('div', { class: 'jev-pb-list' }, spinnerEl('Carregando playbooks…'));
    col1.append(pbListEl);

    // Col 2 — Executions
    const col2 = el('div', { class: 'jev-col jev-col-executions' });
    col2.append(el('div', { class: 'jev-col-placeholder' }, el('p', {}, 'Selecione um playbook para ver as execuções.')));

    // Col 3 — Observability
    const col3 = el('div', { class: 'jev-col jev-col-obs' });
    col3.append(
      el('h3', { class: 'jev-col-title' }, '📡 Observabilidade'),
      el('div', { class: 'jev-col-placeholder' }, el('p', {}, 'Selecione um playbook para ver o snapshot do ambiente.'))
    );

    layout.append(col1, col2, col3);
    main.append(layout);

    let selectedPb = null;

    function selectPlaybook(pb) {
      selectedPb = pb;
      // Update col3 header with env
      col3.replaceChildren(el('h3', { class: 'jev-col-title' },
        '📡 Obs — ', (ENV_META[pb.environment]?.icon || '⬜'), ' ', pb.environment || 'local'
      ));
      // Render executions col2 (which will also drive obs col3)
      renderExecutionsCol(col2, pb, col3, () => selectPlaybook(pb));
      // Re-render playbook list to update selected highlight
      renderPlaybookList(pbListEl, col2, col3, cachedPlaybooks, pb, selectPlaybook);
    }

    let cachedPlaybooks = [];

    fetchPlaybooks().then(playbooks => {
      cachedPlaybooks = playbooks;
      renderPlaybookList(pbListEl, col2, col3, playbooks, null, selectPlaybook);
      // Auto-select first
      if (playbooks.length) selectPlaybook(playbooks[0]);
    }).catch(err => {
      pbListEl.replaceChildren(el('p', { class: 'jev-empty' }, '⚠ Erro: ', err.message));
    });
  }

  // ── CSS injection ───────────────────────────────────────────────────────────

  const STYLES = `
.jev-page-header { padding: 1.25rem 1.5rem 0.5rem; border-bottom: 1px solid var(--border, #222); }
.jev-page-title  { font-size: 1.25rem; font-weight: 700; margin: 0 0 0.25rem; }
.jev-page-subtitle { font-size: 0.82rem; color: var(--muted, #888); margin: 0; }

.jev-layout {
  display: grid;
  grid-template-columns: 260px 1fr 260px;
  gap: 0;
  height: calc(100vh - 140px);
  overflow: hidden;
}

.jev-col {
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  border-right: 1px solid var(--border, #222);
  padding: 0.75rem 0.75rem 1rem;
  gap: 0.5rem;
}
.jev-col:last-child { border-right: none; }
.jev-col-title { font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; margin: 0 0 0.5rem; color: var(--muted, #888); }
.jev-col-header { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; margin-bottom: 0.5rem; }
.jev-col-placeholder { display: flex; align-items: center; justify-content: center; flex: 1; }
.jev-col-placeholder p { color: var(--muted, #888); font-size: 0.82rem; text-align: center; }

/* Playbook list */
.jev-pb-list { display: flex; flex-direction: column; gap: 0.25rem; }
.jev-pb-item {
  background: var(--card, #111);
  border: 1px solid var(--border, #222);
  border-radius: 6px;
  padding: 0.5rem 0.6rem;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  display: flex; flex-direction: column; gap: 0.15rem;
}
.jev-pb-item:hover { border-color: var(--accent, #6ee7b7); background: var(--surface, #181818); }
.jev-pb-selected { border-color: var(--accent, #6ee7b7) !important; background: var(--surface2, #1a1a1a) !important; }
.jev-pb-row { display: flex; align-items: center; gap: 0.4rem; }
.jev-pb-id  { font-size: 0.72rem; font-weight: 700; font-family: monospace; color: var(--muted, #888); }
.jev-pb-env { font-size: 0.85rem; margin-left: auto; }
.jev-pb-title { font-size: 0.8rem; color: var(--text, #e0e0e0); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }

/* Status badges */
.jev-pb-badge { font-size: 0.65rem; font-weight: 700; padding: 0.1em 0.4em; border-radius: 3px; text-transform: uppercase; }
.jev-badge-active     { background: #166534; color: #bbf7d0; }
.jev-badge-draft      { background: #1e3a5f; color: #93c5fd; }
.jev-badge-deprecated { background: #333; color: #888; }

/* Result badges */
.jev-result-badge { font-size: 0.7rem; font-weight: 700; padding: 0.1em 0.5em; border-radius: 3px; font-family: monospace; }
.jev-pass    { background: #166534; color: #bbf7d0; }
.jev-fail    { background: #7f1d1d; color: #fca5a5; }
.jev-error   { background: #78350f; color: #fcd34d; }
.jev-skipped { background: #333;    color: #888; }

/* Execution list */
.jev-exec-list { display: flex; flex-direction: column; gap: 0.5rem; }
.jev-exec-item {
  background: var(--card, #111);
  border: 1px solid var(--border, #222);
  border-radius: 6px;
  padding: 0.6rem 0.75rem;
  display: flex; flex-direction: column; gap: 0.2rem;
}
.jev-exec-bad         { border-color: #7f1d1d; }
.jev-exec-contradicted { border-color: #78350f !important; }
.jev-exec-top  { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.jev-exec-env  { font-size: 0.72rem; color: var(--muted, #888); }
.jev-exec-ts   { font-size: 0.7rem; color: var(--muted, #777); margin-left: auto; }
.jev-exec-summary { font-size: 0.8rem; margin: 0.1rem 0 0; }
.jev-exec-ref, .jev-exec-trace { font-size: 0.72rem; color: var(--muted, #888); font-family: monospace; margin: 0; overflow-wrap: anywhere; }
.jev-exec-origin { font-size: 0.65rem; color: var(--muted, #666); align-self: flex-end; }

/* Obs column */
.jev-obs-metrics { display: flex; flex-direction: column; gap: 0.35rem; }
.jev-obs-metric { display: flex; justify-content: space-between; align-items: center; padding: 0.35rem 0.6rem; border-radius: 5px; font-size: 0.8rem; }
.jev-obs-ok  { background: #0f2d1f; border: 1px solid #166534; }
.jev-obs-bad { background: #2d0f0f; border: 1px solid #7f1d1d; }
.jev-obs-metric-label { color: var(--muted, #888); }
.jev-obs-metric-val   { font-family: monospace; font-weight: 700; }
.jev-obs-ok  .jev-obs-metric-val { color: #bbf7d0; }
.jev-obs-bad .jev-obs-metric-val { color: #fca5a5; }
.jev-obs-unavailable { color: #fcd34d; font-size: 0.82rem; margin: 0 0 0.5rem; }
.jev-obs-note        { color: var(--muted, #888); font-size: 0.8rem; margin: 0; }
.jev-obs-ok-msg      { color: #bbf7d0; font-size: 0.8rem; margin: 0.5rem 0 0; }
.jev-link { color: var(--accent, #6ee7b7); }

/* Contradiction banner */
.jev-contradiction {
  margin-top: 0.75rem;
  background: #2d1a0f;
  border: 1px solid #b45309;
  border-radius: 6px;
  padding: 0.6rem 0.75rem;
  font-size: 0.8rem;
  color: #fcd34d;
}
.jev-contradiction ul { margin: 0.25rem 0 0 1rem; padding: 0; }
.jev-contradiction li { margin: 0.15rem 0; }

/* Modal */
.jev-modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 9999;
  display: flex; align-items: center; justify-content: center;
}
.jev-modal {
  background: var(--panel, #161616);
  border: 1px solid var(--border, #333);
  border-radius: 10px;
  padding: 1.5rem;
  width: 420px; max-width: 95vw;
  display: flex; flex-direction: column; gap: 0.5rem;
}
.jev-modal-title { font-size: 1rem; font-weight: 700; margin: 0 0 0.25rem; }
.jev-modal-pb    { font-size: 0.8rem; color: var(--muted, #888); margin: 0 0 0.5rem; font-family: monospace; }
.jev-modal-error { color: #fca5a5; font-size: 0.8rem; min-height: 1.2em; margin: 0; }
.jev-modal-actions { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 0.5rem; }
.jev-label { font-size: 0.78rem; color: var(--muted, #888); font-weight: 600; }
.jev-input {
  width: 100%; background: var(--surface, #111); border: 1px solid var(--border, #333);
  border-radius: 5px; padding: 0.4rem 0.6rem; color: var(--text, #e0e0e0);
  font-size: 0.85rem; font-family: inherit; resize: vertical;
}
.jev-input:focus { outline: none; border-color: var(--accent, #6ee7b7); }

/* Buttons */
.jev-btn {
  background: var(--surface, #222); border: 1px solid var(--border, #333);
  border-radius: 5px; padding: 0.4rem 0.9rem; font-size: 0.82rem;
  color: var(--text, #e0e0e0); cursor: pointer; transition: opacity 0.15s;
}
.jev-btn:hover { opacity: 0.8; }
.jev-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.jev-btn-primary { background: #166534; border-color: #166534; color: #bbf7d0; font-weight: 700; }
.jev-btn-small { padding: 0.25rem 0.6rem; font-size: 0.75rem; }

/* Misc */
.jev-empty { color: var(--muted, #888); font-size: 0.82rem; }
.jev-loading { color: var(--muted, #888); font-size: 0.82rem; display: flex; align-items: center; gap: 0.5rem; }
.jev-spinner {
  display: inline-block; width: 14px; height: 14px;
  border: 2px solid var(--muted, #555); border-top-color: var(--accent, #6ee7b7);
  border-radius: 50%; animation: jev-spin 0.7s linear infinite;
}
@keyframes jev-spin { to { transform: rotate(360deg); } }

@media (max-width: 900px) {
  .jev-layout { grid-template-columns: 1fr; height: auto; overflow: visible; }
  .jev-col { border-right: none; border-bottom: 1px solid var(--border, #222); }
}
`;

  function injectStyles() {
    if (document.getElementById('jev-styles')) return;
    const s = document.createElement('style');
    s.id = 'jev-styles';
    s.textContent = STYLES;
    document.head.append(s);
  }

  // ── Export ──────────────────────────────────────────────────────────────────

  window.BrainJEV = {
    render(main, api) {
      injectStyles();
      render(main, api);
    },
  };
})();
