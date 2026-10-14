/**
 * jev-ui.js — Joint Evidence View (JEV)
 *
 * Visão cruzada Playbooks × Execuções × Observabilidade do ambiente-alvo.
 * Detecta contradições entre resultado de execução (pass/fail) e estado
 * de observabilidade real do ambiente (métricas de BFF ou fallback local).
 *
 * Integra BrainHubTopologyUI para renderização de topologia real em Col 3.
 * Oferece indicadores de cobertura em Col 1, filtros, e timeline SVG em Col 2.
 *
 * Padrão: window.BrainJEV.render(main, api)
 *
 * Production obs endpoint: /v1/observation/production, /v1/observation/hml
 * Response shape confirmed 2026-10-13: { observation: { report: { snapshots: [...] } } }
 * BFF requires session cookie — local serve.py returns 404/403 without it
 * Fallback: show last SQLite evidence row when BFF unavailable
 */
(function () {
  'use strict';

  // ── Mapeamento de playbooks para ambientes obs ────────────────────────────

  const PLAYBOOK_ENV_MAP = {
    'PB-001': 'local',
    'PB-002': 'hml', 'PB-003': 'hml', 'PB-004': 'hml', 'PB-005': 'hml', 'PB-006': 'hml',
    'PB-007': 'production', 'PB-008': 'production', 'PB-009': 'production', 'PB-010': 'production',
  };

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

  // ── Shim U para BrainHubTopologyUI.render() ────────────────────────────────

  function createShimU() {
    return {
      el: el,
      button(text, handler, className = '') {
        return el('button', { class: 'topology-button ' + className, onclick: handler }, text);
      },
      badge(text, label) {
        return el('span', { class: 'pill topology-status-' + (label || 'unknown') }, text);
      },
      head(section, title, subtitle) {
        return el('div', { class: 'jev-topology-section-head' },
          el('div', { class: 'jev-section-eyebrow' }, section),
          el('h3', { class: 'jev-section-title' }, title),
          subtitle ? el('p', { class: 'jev-section-subtitle' }, subtitle) : null
        );
      },
    };
  }

  // ── Adaptação de payload /v1/observation/* → BrainHubTopology.project() ────

  function adaptObsPayload(rawResponse, environment) {
    if (!rawResponse) return null;
    return {
      environment: environment,
      observation: rawResponse.observation || null,
      last_attempt: rawResponse.last_attempt || { collected_at: null },
      collection_failed: rawResponse.collection_failed ?? false,
      stale: rawResponse.stale ?? false,
    };
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

  async function fetchPlaybookDetail(pbId) {
    const r = await fetch(`/api/playbooks/${encodeURIComponent(pbId)}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
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

  // ── Enriquecimento de dados ──────────────────────────────────────────────

  function getLastExecutionForEnv(executions, environment) {
    const filtered = executions.filter(e => e.environment === environment);
    if (!filtered.length) return null;
    return filtered.sort((a, b) => new Date(b.ts) - new Date(a.ts))[0];
  }

  function daysSinceExecution(exec) {
    if (!exec || !exec.ts) return Infinity;
    return (Date.now() - new Date(exec.ts).getTime()) / (24 * 60 * 60 * 1000);
  }

  function enrichPlaybooksWithCoverage(playbooks, executions, obsStates) {
    return playbooks.map(pb => {
      const env = PLAYBOOK_ENV_MAP[pb.id] || pb.environment || 'local';
      const lastExec = getLastExecutionForEnv(executions, env);
      const daysSince = daysSinceExecution(lastExec);
      const hasRecentExec = daysSince <= 7;
      const obsData = obsStates[env] || null;
      const obsAvailable = obsData && !obsData._unavailable;
      let obsStatus = null;
      if (obsAvailable && window.BrainHubTopology && window.BrainHubTopologyUI) {
        try {
          const adapted = adaptObsPayload(obsData, env);
          const model = window.BrainHubTopology.project(env, adapted, Date.now() / 1000);
          obsStatus = model.summary?.status || null;
        } catch (e) {}
      }
      return {
        ...pb,
        _enriched: {
          environment: env,
          hasRecentExec,
          daysSince,
          lastExecResult: lastExec?.result || null,
          obsAvailable,
          obsStatus,
        }
      };
    });
  }

  // ── Detecção de contradições (enriquecida) ────────────────────────────────

  function detectContradictionsEnriched(executions, model) {
    if (!model || !executions.length) return [];
    const lastPass = executions.find(e => e.result === 'pass');
    if (!lastPass) return [];
    const flags = [];
    const dbNode = model.nodes?.find(n => n.id === 'database');
    const processNode = model.nodes?.find(n => n.id === 'process');
    const internalNode = model.nodes?.find(n => n.id === 'internal');
    const externalNode = model.nodes?.find(n => n.id === 'external');
    if (dbNode?.metrics?.failed > 0) flags.push(`db.failed = ${dbNode.metrics.failed}`);
    if (dbNode?.metrics?.rateLimitsSinceDeploy > 0) flags.push(`rate limits = ${dbNode.metrics.rateLimitsSinceDeploy}`);
    if (dbNode?.metrics?.terminalErrorsSinceDeploy > 0) flags.push(`terminal errors = ${dbNode.metrics.terminalErrorsSinceDeploy}`);
    if (dbNode?.metrics?.logisticsReviewJobs > 0) flags.push(`logistics review jobs = ${dbNode.metrics.logisticsReviewJobs}`);
    if (dbNode?.metrics?.multipleVolumeReviewJobs > 0) flags.push(`multiple volume review jobs = ${dbNode.metrics.multipleVolumeReviewJobs}`);
    if (processNode?.status && processNode.status !== 'green') flags.push(`process = ${processNode.status}`);
    if (internalNode?.status && internalNode.status !== 'green') flags.push(`internal = ${internalNode.status}`);
    if (externalNode?.status && externalNode.status !== 'green') flags.push(`external = ${externalNode.status}`);
    if (model.environment === 'production' && internalNode?.metrics?.workerEnabled !== true) {
      flags.push('worker not enabled');
    }
    return flags;
  }

  // ── Timeline SVG ────────────────────────────────────────────────────────────

  function renderExecutionTimeline(executions, container) {
    container.innerHTML = '';
    if (executions.length < 2) {
      container.append(el('p', { class: 'jev-timeline-note' }, 'Timeline disponível com 2+ execuções.'));
      return;
    }
    const sorted = [...executions].sort((a, b) => new Date(a.ts) - new Date(b.ts));
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 400 60');
    svg.setAttribute('preserveAspectRatio', 'none');
    svg.setAttribute('class', 'jev-exec-timeline');
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', '0');
    line.setAttribute('y1', '30');
    line.setAttribute('x2', '400');
    line.setAttribute('y2', '30');
    line.setAttribute('stroke', '#444');
    line.setAttribute('stroke-dasharray', '2,2');
    line.setAttribute('opacity', '0.3');
    svg.append(line);
    sorted.forEach((exec, idx) => {
      const x = (idx / (sorted.length - 1)) * 400;
      let y, color;
      if (exec.result === 'pass') {
        y = 10; color = '#4ade80';
      } else if (exec.result === 'fail' || exec.result === 'error') {
        y = 50; color = '#f87171';
      } else {
        y = 30; color = '#fbbf24';
      }
      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('cx', x);
      circle.setAttribute('cy', y);
      circle.setAttribute('r', '5');
      circle.setAttribute('fill', color);
      circle.setAttribute('class', 'jev-timeline-point');
      circle.setAttribute('style', 'cursor: pointer;');
      const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      title.textContent = `${RESULT_META[exec.result]?.label || exec.result} — ${fmtDate(exec.ts)}`;
      circle.append(title);
      svg.append(circle);
    });
    container.append(svg);
  }

  // ── Filtros de Col 1 ────────────────────────────────────────────────────────

  function createFilters() {
    const state = { environment: 'todos', status: 'todos', result: 'todos' };
    const container = el('div', { class: 'jev-filters' });
    container.append(
      el('div', { class: 'jev-filter-group' },
        el('label', { class: 'jev-filter-label' }, 'Ambiente'),
        el('select', { class: 'jev-filter-select', onchange: (e) => state.environment = e.target.value },
          el('option', { value: 'todos' }, 'Todos'),
          el('option', { value: 'local' }, 'Local'),
          el('option', { value: 'hml' }, 'Homologação'),
          el('option', { value: 'production' }, 'Production'),
        )
      ),
      el('div', { class: 'jev-filter-group' },
        el('label', { class: 'jev-filter-label' }, 'Status'),
        el('select', { class: 'jev-filter-select', onchange: (e) => state.status = e.target.value },
          el('option', { value: 'todos' }, 'Todos'),
          el('option', { value: 'active' }, 'Ativo'),
          el('option', { value: 'draft' }, 'Rascunho'),
          el('option', { value: 'deprecated' }, 'Depreciado'),
        )
      ),
      el('div', { class: 'jev-filter-group' },
        el('label', { class: 'jev-filter-label' }, 'Resultado'),
        el('select', { class: 'jev-filter-select', onchange: (e) => state.result = e.target.value },
          el('option', { value: 'todos' }, 'Todos'),
          el('option', { value: 'pass' }, 'Pass'),
          el('option', { value: 'fail' }, 'Fail'),
          el('option', { value: 'sem_execucao' }, 'Sem execução'),
        )
      )
    );
    return { container, state };
  }

  function applyFilters(playbooks, filters) {
    return playbooks.filter(pb => {
      const env = pb._enriched?.environment || pb.environment;
      const status = pb.status;
      const result = pb._enriched?.lastExecResult;
      if (filters.environment !== 'todos' && env !== filters.environment) return false;
      if (filters.status !== 'todos' && status !== filters.status) return false;
      if (filters.result !== 'todos') {
        if (filters.result === 'sem_execucao' && pb._enriched?.lastExecResult !== null) return false;
        if (filters.result !== 'sem_execucao' && result !== filters.result) return false;
      }
      return true;
    });
  }

  // ── Record execution modal ──────────────────────────────────────────────────

  function openRecordModal(pb, onSaved, initialParams = null) {
    const overlay = el('div', { class: 'jev-modal-overlay' });
    const modal = el('div', { class: 'jev-modal', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'jev-modal-title' });

    const envOptions = Object.entries(ENV_META).map(([k, v]) =>
      el('option', { value: k }, v.icon + ' ' + v.label)
    );
    const resOptions = ['pass', 'fail', 'error', 'skipped'].map(r =>
      el('option', { value: r }, RESULT_META[r].label)
    );

    const selEnv = el('select', { class: 'jev-input', id: 'jev-modal-env' }, ...envOptions);
    selEnv.value = (initialParams && initialParams.environment) || pb._enriched?.environment || pb.environment || 'local';
    const selRes = el('select', { class: 'jev-input', id: 'jev-modal-result' }, ...resOptions);
    
    let defaultSummary = '';
    if (initialParams && Object.keys(initialParams).length > 0) {
      defaultSummary = `Parâmetros Liquid: ${JSON.stringify(initialParams)}`;
    }
    const inpSummary = el('textarea', { class: 'jev-input', id: 'jev-modal-summary', rows: '3', placeholder: 'Resumo da execução…' });
    if (defaultSummary) inpSummary.value = defaultSummary;

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

  // ── Column 3: Observability with topology ────────────────────────────────

  function getLastObsSnapshot(executions, environment) {
    if (!executions || !executions.length) return null;
    const filtered = executions.filter(e => e.environment === environment);
    if (!filtered.length) return null;
    const sorted = filtered.sort((a, b) => new Date(b.ts) - new Date(a.ts));
    const lastExec = sorted[0];
    if (!lastExec) return null;
    return {
      ts: lastExec.ts,
      result: lastExec.result,
      summary: lastExec.summary,
      environment: lastExec.environment,
    };
  }

  function renderObsColWithTopology(container, env, obs, fallbackExecSample) {
    container.replaceChildren();
    const envMeta = ENV_META[env] || { label: env, icon: '⬜', obsPath: null };

    if (!envMeta.obsPath) {
      container.append(el('p', { class: 'jev-obs-note' },
        envMeta.icon, ' Ambiente local — sem snapshot de observabilidade ao vivo.'
      ));
      return;
    }

    if (!obs || obs._unavailable) {
      const lastSnapshot = getLastObsSnapshot(fallbackExecSample || [], env);
      if (lastSnapshot) {
        container.append(
          el('div', { class: 'jev-obs-offline' },
            el('p', { class: 'jev-obs-unavailable' }, '⚠️ Offline — BFF não disponível (HTTP ', obs ? String(obs.status) : 'network', ')'),
            el('div', { class: 'jev-obs-last-snapshot' },
              el('div', { class: 'jev-obs-snapshot-label' }, 'Última captura:'),
              el('div', { class: 'jev-obs-snapshot-ts' }, fmtDate(lastSnapshot.ts)),
              el('div', { class: 'jev-obs-snapshot-result' }, 
                resultBadge(lastSnapshot.result)
              ),
              lastSnapshot.summary ? el('div', { class: 'jev-obs-snapshot-summary' }, lastSnapshot.summary) : null,
            ),
            el('p', { class: 'jev-obs-note' },
              'Para captura ao vivo, acesse a aba ',
              el('a', { href: '#page=observability', class: 'jev-link' }, '📡 Observabilidade'), '.'
            ),
          )
        );
      } else {
        container.append(
          el('p', { class: 'jev-obs-unavailable' }, '⚠ BFF não disponível (HTTP ', obs ? String(obs.status) : 'network', ')'),
          el('p', { class: 'jev-obs-note' },
            'Para ver dados ao vivo, acesse a aba ',
            el('a', { href: '#page=observability', class: 'jev-link' }, '📡 Observabilidade'), '.'
          )
        );
      }
      return;
    }

    if (window.BrainHubTopology && window.BrainHubTopologyUI) {
      try {
        const adapted = adaptObsPayload(obs, env);
        const model = window.BrainHubTopology.project(env, adapted, Date.now() / 1000);
        const U = createShimU();
        const topologyEl = window.BrainHubTopologyUI.render(model, U, { selectedId: 'process' });
        const execs = container._lastExecsSample || [];
        const contradictions = detectContradictionsEnriched(execs, model);
        container.append(topologyEl);
        if (contradictions.length > 0) {
          container.append(
            el('div', { class: 'jev-contradiction' },
              el('strong', {}, '⚡ Contradições detectadas:'),
              el('ul', {}, ...contradictions.map(c => el('li', {}, c)))
            )
          );
        }
      } catch (e) {
        renderObsRawMetrics(container, obs);
      }
    } else {
      renderObsRawMetrics(container, obs);
    }
  }

  function renderObsRawMetrics(container, obs) {
    const metrics = [
      ['db.failed',    obs.observation?.report?.snapshots?.[0]?.database?.failed,  'Falhas DB'],
      ['db.pending',   obs.observation?.report?.snapshots?.[0]?.database?.pending,  'Fila pendente'],
      ['process',      obs.observation?.report?.snapshots?.[0]?.process?.status,    'Processo'],
      ['internal',     obs.observation?.report?.snapshots?.[0]?.internal?.status,   'BFF interno'],
      ['external',     obs.observation?.report?.snapshots?.[0]?.external?.status,   'Serviços externos'],
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
    if (rows.length > 0) {
      container.append(el('div', { class: 'jev-obs-metrics' }, ...rows));
    } else {
      container.append(el('p', { class: 'jev-obs-note' }, 'Sem dados de obs para este ambiente.'));
    }
  }

  // ── Column 2: Executions list ────────────────────────────────────────────────

  // ── Column 2: Executions list & Liquid Procedure ─────────────────────────

  function renderProcedureView(container, pb, onRefresh) {
    container.replaceChildren();
    const loading = spinnerEl('Carregando conteúdo do playbook…');
    container.append(loading);

    fetchPlaybookDetail(pb.id).then(data => {
      loading.remove();
      const rawContent = data.content || '';
      const meta = data.meta || pb;
      const declaredParams = meta.params || pb.params || [];
      
      const extractedVars = window.LiquidEngine ? window.LiquidEngine.extractVariables(rawContent) : [];
      const paramNames = new Set(declaredParams.map(p => p.name));
      const allParams = [...declaredParams];
      for (const v of extractedVars) {
        if (!paramNames.has(v)) {
          allParams.push({ name: v, label: v, default: '' });
          paramNames.add(v);
        }
      }

      const currentValues = {};
      allParams.forEach(p => {
        currentValues[p.name] = p.default !== undefined ? p.default : '';
      });

      const paramCard = el('div', { class: 'jev-liquid-card' });
      const paramHead = el('div', { class: 'jev-liquid-head' },
        el('span', { class: 'jev-liquid-title' }, '⚡ Parâmetros Liquid'),
        el('span', { class: 'jev-liquid-badge' }, `${allParams.length} param(s)`)
      );
      paramCard.append(paramHead);

      const previewContainer = el('div', { class: 'jev-markdown-preview' });

      function updatePreview() {
        if (window.LiquidEngine) {
          const renderedMd = window.LiquidEngine.render(rawContent, currentValues);
          if (window.BrainMarkdown && typeof window.BrainMarkdown.render === 'function') {
            window.BrainMarkdown.render(renderedMd, previewContainer);
          } else {
            previewContainer.textContent = renderedMd;
          }
        } else {
          previewContainer.textContent = rawContent;
        }
      }

      if (allParams.length > 0) {
        const grid = el('div', { class: 'jev-liquid-grid' });
        allParams.forEach(p => {
          const row = el('div', { class: 'jev-liquid-row' });
          row.append(el('label', { class: 'jev-label' }, p.label || p.name, p.required ? ' *' : ''));

          let inputEl;
          if (p.type === 'select' && Array.isArray(p.options)) {
            inputEl = el('select', { class: 'jev-input' },
              ...p.options.map(opt => el('option', { value: opt }, String(opt)))
            );
            inputEl.value = currentValues[p.name] || p.options[0];
            inputEl.onchange = (e) => {
              currentValues[p.name] = e.target.value;
              updatePreview();
            };
          } else if (p.type === 'boolean') {
            inputEl = el('input', { type: 'checkbox', class: 'jev-checkbox' });
            inputEl.checked = Boolean(currentValues[p.name]);
            inputEl.onchange = (e) => {
              currentValues[p.name] = e.target.checked;
              updatePreview();
            };
          } else {
            inputEl = el('input', {
              type: 'text',
              class: 'jev-input',
              value: String(currentValues[p.name] || ''),
              placeholder: p.description || p.name
            });
            inputEl.oninput = (e) => {
              currentValues[p.name] = e.target.value;
              updatePreview();
            };
          }
          row.append(inputEl);
          grid.append(row);
        });
        paramCard.append(grid);
      } else {
        paramCard.append(el('p', { class: 'jev-obs-note', style: 'padding: 0.5rem;' }, 'Nenhum parâmetro dinâmico Liquid detectado neste playbook.'));
      }

      const actions = el('div', { class: 'jev-liquid-actions' });
      const btnCopy = el('button', { class: 'jev-btn jev-btn-small', onclick: () => {
        const codeBlocks = previewContainer.querySelectorAll('pre');
        const commands = Array.from(codeBlocks).map(c => c.textContent).join('\n\n');
        if (commands) {
          navigator.clipboard.writeText(commands);
          btnCopy.textContent = '✅ Comandos Copiados!';
          setTimeout(() => { btnCopy.textContent = '📋 Copiar Comandos'; }, 1500);
        } else {
          navigator.clipboard.writeText(previewContainer.textContent);
          btnCopy.textContent = '✅ Conteúdo Copiado!';
          setTimeout(() => { btnCopy.textContent = '📋 Copiar Comandos'; }, 1500);
        }
      }}, '📋 Copiar Comandos');

      const btnExec = el('button', { class: 'jev-btn jev-btn-small jev-btn-primary', onclick: () => {
        openRecordModal(pb, onRefresh, currentValues);
      }}, '🧪 Registrar Execução com estes Parâmetros');

      actions.append(btnCopy, btnExec);
      paramCard.append(actions);

      container.append(paramCard, previewContainer);
      updatePreview();
    }).catch(err => {
      loading.remove();
      container.append(el('p', { class: 'jev-empty' }, '⚠ Erro ao carregar procedimento: ', err.message));
    });
  }

  function renderExecutionsList(container, pb, obsColEl, onRefresh) {
    container.replaceChildren();
    const loading = spinnerEl();
    container.append(loading);

    fetchExecutions(pb.id).then(execs => {
      loading.remove();
      const timelineEl = el('div', { class: 'jev-timeline-container' });
      renderExecutionTimeline(execs, timelineEl);
      container.append(timelineEl);
      
      if (!execs.length) {
        container.append(el('p', { class: 'jev-empty' }, 'Nenhuma execução registrada.'));
        const env = pb._enriched?.environment || pb.environment || 'local';
        renderObsColWithTopology(obsColEl, env, { _unavailable: true }, execs);
        return;
      }

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

      const env = pb._enriched?.environment || pb.environment || 'local';
      if (ENV_META[env]?.obsPath) {
        const obsLoading = spinnerEl('Carregando obs…');
        obsColEl.replaceChildren(obsLoading);
        fetchObsSnapshot(env).then(obs => {
          obsColEl._lastExecsSample = execs;
          renderObsColWithTopology(obsColEl, env, obs, execs);
          if (obs && !obs._unavailable && window.BrainHubTopology && window.BrainHubTopologyUI) {
            try {
              const adapted = adaptObsPayload(obs, env);
              const model = window.BrainHubTopology.project(env, adapted, Date.now() / 1000);
              const flags = detectContradictionsEnriched(execs, model);
              if (flags.length) {
                const passItems = list.querySelectorAll('.jev-exec-item:not(.jev-exec-bad)');
                passItems.forEach(item => item.classList.add('jev-exec-contradicted'));
              }
            } catch (e) {}
          }
        }).catch(err => {
          obsColEl.replaceChildren(el('p', { class: 'jev-obs-unavailable' }, '⚠ Erro ao carregar obs: ', err.message));
        });
      } else {
        renderObsColWithTopology(obsColEl, env, null, []);
      }
    }).catch(err => {
      loading.remove();
      container.append(el('p', { class: 'jev-empty' }, '⚠ Erro ao carregar execuções: ', err.message));
    });
  }

  function renderExecutionsCol(container, pb, obsColEl, onRefresh) {
    container.replaceChildren();

    const hasParams = (pb.params && pb.params.length > 0);

    const tabBar = el('div', { class: 'jev-subtab-bar' });
    const btnTabExecs = el('button', {
      class: 'jev-subtab-btn jev-subtab-active',
      onclick: () => switchTab('execs')
    }, '🧪 Execuções');

    const btnTabProc = el('button', {
      class: 'jev-subtab-btn',
      onclick: () => switchTab('procedure')
    }, '⚡ Procedimento & Liquid', hasParams ? el('span', { class: 'jev-param-pill' }, String(pb.params.length)) : null);

    const btnRegister = el('button', {
      class: 'jev-btn jev-btn-small jev-btn-primary',
      style: 'margin-left: auto;',
      onclick: () => openRecordModal(pb, onRefresh)
    }, '+ Registrar');

    tabBar.append(btnTabExecs, btnTabProc, btnRegister);
    container.append(tabBar);

    const contentArea = el('div', { class: 'jev-subtab-content' });
    container.append(contentArea);

    function switchTab(tab) {
      btnTabExecs.classList.toggle('jev-subtab-active', tab === 'execs');
      btnTabProc.classList.toggle('jev-subtab-active', tab === 'procedure');
      if (tab === 'execs') {
        renderExecutionsList(contentArea, pb, obsColEl, onRefresh);
      } else {
        renderProcedureView(contentArea, pb, onRefresh);
      }
    }

    renderExecutionsList(contentArea, pb, obsColEl, onRefresh);
  }

  // ── Column 1: Playbook list ─────────────────────────────────────────────────

  function renderPlaybookList(listEl, playbooks, selected, onSelect, filterState) {
    listEl.replaceChildren();
    const filtered = applyFilters(playbooks, filterState);
    if (!filtered.length) {
      listEl.append(el('p', { class: 'jev-empty' }, 'Nenhum playbook encontrado com esses filtros.'));
      return;
    }
    for (const pb of filtered) {
      const sm = STATUS_META[pb.status] || STATUS_META.draft;
      const env = pb._enriched?.environment || pb.environment || 'local';
      const envMeta = ENV_META[env] || { icon: '⬜' };
      const enriched = pb._enriched || {};
      const hasCov = enriched.hasRecentExec ? '🟢 COBERT.' : '🔴 SEM EXEC';
      const obsInd = enriched.obsAvailable ? 
        (enriched.obsStatus === 'green' ? '📡 OBS OK' : '📡 OBS ⚠') : null;
      const resInd = enriched.lastExecResult ? 
        `${RESULT_META[enriched.lastExecResult]?.icon || '?'} ${RESULT_META[enriched.lastExecResult]?.label || enriched.lastExecResult}` : null;
      
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
        el('div', { class: 'jev-pb-indicators' },
          el('span', { class: 'jev-pb-indicator' }, hasCov),
          obsInd ? el('span', { class: 'jev-pb-indicator' }, obsInd) : null,
          resInd ? el('span', { class: 'jev-pb-indicator' }, resInd) : null,
        ),
      );
      listEl.append(item);
    }
  }

  // ── Main render ─────────────────────────────────────────────────────────────

  function render(main, api) {
    main.replaceChildren();

    const head = el('div', { class: 'jev-page-header' },
      el('h2', { class: 'jev-page-title' }, '📊 Joint Evidence View'),
      el('p', { class: 'jev-page-subtitle' },
        'Visão cruzada Playbooks × Execuções × Observabilidade do ambiente-alvo. ',
        'Destaca contradições entre resultado registrado e estado real do ambiente.'
      )
    );
    main.append(head);

    const layout = el('div', { class: 'jev-layout' });

    const col1 = el('div', { class: 'jev-col jev-col-playbooks' });
    col1.append(el('h3', { class: 'jev-col-title' }, '📋 Playbooks'));
    
    const { container: filterContainer, state: filterState } = createFilters();
    col1.append(filterContainer);
    
    const pbListEl = el('div', { class: 'jev-pb-list' }, spinnerEl('Carregando playbooks…'));
    col1.append(pbListEl);

    const col2 = el('div', { class: 'jev-col jev-col-executions' });
    col2.append(el('div', { class: 'jev-col-placeholder' }, el('p', {}, 'Selecione um playbook para ver as execuções.')));

    const col3 = el('div', { class: 'jev-col jev-col-obs' });
    col3.append(
      el('h3', { class: 'jev-col-title' }, '📡 Observabilidade'),
      el('div', { class: 'jev-col-placeholder' }, el('p', {}, 'Selecione um playbook para ver o snapshot do ambiente.'))
    );

    layout.append(col1, col2, col3);
    main.append(layout);

    let selectedPb = null;
    let allPlaybooksEnriched = [];
    let allExecutions = [];
    let obsStates = {};

    function selectPlaybook(pb) {
      selectedPb = pb;
      const env = pb._enriched?.environment || pb.environment || 'local';
      col3.replaceChildren(el('h3', { class: 'jev-col-title' },
        '📡 Obs — ', (ENV_META[env]?.icon || '⬜'), ' ', env
      ));
      renderExecutionsCol(col2, pb, col3, () => selectPlaybook(pb));
      renderPlaybookList(pbListEl, allPlaybooksEnriched, pb, selectPlaybook, filterState);
    }

    Promise.all([
      fetchPlaybooks(),
      fetchExecutions(null),
      Promise.all([
        fetchObsSnapshot('hml'),
        fetchObsSnapshot('production'),
      ]).then(([hmlObs, prodObs]) => ({
        hml: hmlObs,
        production: prodObs,
        local: null,
      })),
    ]).then(([playbooks, executions, obs]) => {
      allExecutions = executions;
      obsStates = obs;
      allPlaybooksEnriched = enrichPlaybooksWithCoverage(playbooks, executions, obs);
      renderPlaybookList(pbListEl, allPlaybooksEnriched, null, selectPlaybook, filterState);
      if (allPlaybooksEnriched.length) selectPlaybook(allPlaybooksEnriched[0]);
      const filterSelects = filterContainer.querySelectorAll('select');
      filterSelects.forEach(sel => {
        sel.addEventListener('change', () => {
          renderPlaybookList(pbListEl, allPlaybooksEnriched, selectedPb, selectPlaybook, filterState);
        });
      });
    }).catch(err => {
      pbListEl.replaceChildren(el('p', { class: 'jev-empty' }, '⚠ Erro: ', err.message));
    });
  }

  // ── CSS injection ───────────────────────────────────────────────────────────

  const STYLES = `
.jev-page-header { padding: 1.25rem 1.5rem 0.5rem; border-bottom: 1px solid var(--border, #222); }
.jev-page-title  { font-size: 1.25rem; font-weight: 700; margin: 0 0 0.25rem; }
.jev-page-subtitle { font-size: 0.82rem; color: var(--muted, #888); margin: 0; }
.jev-layout { display: grid; grid-template-columns: 260px 1fr 260px; gap: 0; height: calc(100vh - 140px); overflow: hidden; }
.jev-col { display: flex; flex-direction: column; overflow-y: auto; border-right: 1px solid var(--border, #222); padding: 0.75rem 0.75rem 1rem; gap: 0.5rem; }
.jev-col:last-child { border-right: none; }
.jev-col-title { font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; margin: 0 0 0.5rem; color: var(--muted, #888); }
.jev-col-header { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; margin-bottom: 0.5rem; }
.jev-col-placeholder { display: flex; align-items: center; justify-content: center; flex: 1; }
.jev-col-placeholder p { color: var(--muted, #888); font-size: 0.82rem; text-align: center; }
.jev-filters { display: flex; gap: 0.5rem; margin-bottom: 0.75rem; flex-wrap: wrap; }
.jev-filter-group { display: flex; flex-direction: column; gap: 0.2rem; flex: 1; min-width: 80px; }
.jev-filter-label { font-size: 0.65rem; color: var(--muted, #888); font-weight: 600; text-transform: uppercase; }
.jev-filter-select { padding: 0.3rem 0.4rem; background: var(--surface, #111); border: 1px solid var(--border, #333); border-radius: 3px; color: var(--text, #e0e0e0); font-size: 0.75rem; }
.jev-pb-list { display: flex; flex-direction: column; gap: 0.25rem; }
.jev-pb-item { background: var(--card, #111); border: 1px solid var(--border, #222); border-radius: 6px; padding: 0.5rem 0.6rem; text-align: left; cursor: pointer; transition: border-color 0.15s, background 0.15s; display: flex; flex-direction: column; gap: 0.15rem; }
.jev-pb-item:hover { border-color: var(--accent, #6ee7b7); background: var(--surface, #181818); }
.jev-pb-selected { border-color: var(--accent, #6ee7b7) !important; background: var(--surface2, #1a1a1a) !important; }
.jev-pb-row { display: flex; align-items: center; gap: 0.4rem; }
.jev-pb-id  { font-size: 0.72rem; font-weight: 700; font-family: monospace; color: var(--muted, #888); }
.jev-pb-env { font-size: 0.85rem; margin-left: auto; }
.jev-pb-title { font-size: 0.8rem; color: var(--text, #e0e0e0); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.jev-pb-indicators { display: flex; flex-direction: column; gap: 0.1rem; }
.jev-pb-indicator { font-size: 0.65rem; color: var(--muted, #888); white-space: nowrap; }
.jev-pb-badge { font-size: 0.65rem; font-weight: 700; padding: 0.1em 0.4em; border-radius: 3px; text-transform: uppercase; }
.jev-badge-active { background: #166534; color: #bbf7d0; }
.jev-badge-draft { background: #1e3a5f; color: #93c5fd; }
.jev-badge-deprecated { background: #333; color: #888; }
.jev-result-badge { font-size: 0.7rem; font-weight: 700; padding: 0.1em 0.5em; border-radius: 3px; font-family: monospace; }
.jev-pass { background: #166534; color: #bbf7d0; }
.jev-fail { background: #7f1d1d; color: #fca5a5; }
.jev-error { background: #78350f; color: #fcd34d; }
.jev-skipped { background: #333; color: #888; }
.jev-timeline-container { margin-bottom: 0.5rem; }
.jev-exec-timeline { display: block; width: 100%; height: 50px; margin: 0; }
.jev-timeline-note { font-size: 0.75rem; color: var(--muted, #888); margin: 0.25rem 0; }
.jev-exec-list { display: flex; flex-direction: column; gap: 0.5rem; }
.jev-exec-item { background: var(--card, #111); border: 1px solid var(--border, #222); border-radius: 6px; padding: 0.6rem 0.75rem; display: flex; flex-direction: column; gap: 0.2rem; }
.jev-exec-bad { border-color: #7f1d1d; }
.jev-exec-contradicted { border-color: #78350f !important; }
.jev-exec-top { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.jev-exec-env { font-size: 0.72rem; color: var(--muted, #888); }
.jev-exec-ts { font-size: 0.7rem; color: var(--muted, #777); margin-left: auto; }
.jev-exec-summary { font-size: 0.8rem; margin: 0.1rem 0 0; }
.jev-exec-ref, .jev-exec-trace { font-size: 0.72rem; color: var(--muted, #888); font-family: monospace; margin: 0; overflow-wrap: anywhere; }
.jev-exec-origin { font-size: 0.65rem; color: var(--muted, #666); align-self: flex-end; }
.jev-obs-metrics { display: flex; flex-direction: column; gap: 0.35rem; }
.jev-obs-metric { display: flex; justify-content: space-between; align-items: center; padding: 0.35rem 0.6rem; border-radius: 5px; font-size: 0.8rem; }
.jev-obs-ok { background: #0f2d1f; border: 1px solid #166534; }
.jev-obs-bad { background: #2d0f0f; border: 1px solid #7f1d1d; }
.jev-obs-metric-label { color: var(--muted, #888); }
.jev-obs-metric-val { font-family: monospace; font-weight: 700; }
.jev-obs-ok .jev-obs-metric-val { color: #bbf7d0; }
.jev-obs-bad .jev-obs-metric-val { color: #fca5a5; }
.jev-obs-unavailable { color: #fcd34d; font-size: 0.82rem; margin: 0 0 0.5rem; }
.jev-obs-offline { display: flex; flex-direction: column; gap: 0.6rem; }
.jev-obs-last-snapshot { background: #1a1a1a; border: 1px solid #b45309; border-radius: 6px; padding: 0.75rem; display: flex; flex-direction: column; gap: 0.3rem; }
.jev-obs-snapshot-label { font-size: 0.7rem; text-transform: uppercase; color: var(--muted, #888); font-weight: 600; letter-spacing: 0.05em; }
.jev-obs-snapshot-ts { font-size: 0.8rem; font-family: monospace; color: #fbbf24; font-weight: 600; }
.jev-obs-snapshot-result { font-size: 0.8rem; }
.jev-obs-snapshot-summary { font-size: 0.75rem; color: var(--muted, #999); white-space: pre-wrap; word-break: break-word; margin-top: 0.2rem; }
.jev-obs-note { color: var(--muted, #888); font-size: 0.8rem; margin: 0; }
.jev-link { color: var(--accent, #6ee7b7); }
.jev-topology-section-head { margin-bottom: 0.75rem; }
.jev-section-eyebrow { font-size: 0.7rem; text-transform: uppercase; color: var(--muted, #888); font-weight: 600; letter-spacing: 0.05em; }
.jev-section-title { font-size: 0.95rem; font-weight: 700; margin: 0.1rem 0 0.05rem; }
.jev-section-subtitle { font-size: 0.75rem; color: var(--muted, #777); margin: 0; }
.jev-contradiction { margin-top: 0.75rem; background: #2d1a0f; border: 1px solid #b45309; border-radius: 6px; padding: 0.6rem 0.75rem; font-size: 0.8rem; color: #fcd34d; }
.jev-contradiction ul { margin: 0.25rem 0 0 1rem; padding: 0; }
.jev-contradiction li { margin: 0.15rem 0; }
.jev-modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.7); z-index: 9999; display: flex; align-items: center; justify-content: center; }
.jev-modal { background: var(--panel, #161616); border: 1px solid var(--border, #333); border-radius: 10px; padding: 1.5rem; width: 420px; max-width: 95vw; display: flex; flex-direction: column; gap: 0.5rem; }
.jev-modal-title { font-size: 1rem; font-weight: 700; margin: 0 0 0.25rem; }
.jev-modal-pb { font-size: 0.8rem; color: var(--muted, #888); margin: 0 0 0.5rem; font-family: monospace; }
.jev-modal-error { color: #fca5a5; font-size: 0.8rem; min-height: 1.2em; margin: 0; }
.jev-modal-actions { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 0.5rem; }
.jev-label { font-size: 0.78rem; color: var(--muted, #888); font-weight: 600; }
.jev-input { width: 100%; background: var(--surface, #111); border: 1px solid var(--border, #333); border-radius: 5px; padding: 0.4rem 0.6rem; color: var(--text, #e0e0e0); font-size: 0.85rem; font-family: inherit; resize: vertical; }
.jev-input:focus { outline: none; border-color: var(--accent, #6ee7b7); }
.jev-btn { background: var(--surface, #222); border: 1px solid var(--border, #333); border-radius: 5px; padding: 0.4rem 0.9rem; font-size: 0.82rem; color: var(--text, #e0e0e0); cursor: pointer; transition: opacity 0.15s; }
.jev-btn:hover { opacity: 0.8; }
.jev-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.jev-btn-primary { background: #166534; border-color: #166534; color: #bbf7d0; font-weight: 700; }
.jev-btn-small { padding: 0.25rem 0.6rem; font-size: 0.75rem; }
.jev-empty { color: var(--muted, #888); font-size: 0.82rem; }
.jev-loading { color: var(--muted, #888); font-size: 0.82rem; display: flex; align-items: center; gap: 0.5rem; }
.jev-spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid var(--muted, #555); border-top-color: var(--accent, #6ee7b7); border-radius: 50%; animation: jev-spin 0.7s linear infinite; }
@keyframes jev-spin { to { transform: rotate(360deg); } }
.jev-subtab-bar { display: flex; align-items: center; gap: 0.4rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border, #222); margin-bottom: 0.5rem; }
.jev-subtab-btn { background: transparent; border: 1px solid transparent; color: var(--muted, #888); font-size: 0.78rem; font-weight: 600; padding: 0.3rem 0.6rem; border-radius: 4px; cursor: pointer; display: flex; align-items: center; gap: 0.4rem; }
.jev-subtab-btn:hover { color: var(--text, #e0e0e0); background: var(--surface, #181818); }
.jev-subtab-btn.jev-subtab-active { color: var(--accent, #6ee7b7); background: var(--surface2, #202020); border-color: var(--border, #333); }
.jev-param-pill { background: #1e3a5f; color: #93c5fd; font-size: 0.65rem; padding: 0.1rem 0.35rem; border-radius: 999px; }
.jev-subtab-content { display: flex; flex-direction: column; gap: 0.5rem; }
.jev-liquid-card { background: var(--card, #141414); border: 1px solid var(--border, #282828); border-radius: 6px; padding: 0.75rem; display: flex; flex-direction: column; gap: 0.6rem; }
.jev-liquid-head { display: flex; align-items: center; justify-content: space-between; }
.jev-liquid-title { font-size: 0.82rem; font-weight: 700; color: #fcd34d; }
.jev-liquid-badge { font-size: 0.68rem; color: var(--muted, #888); }
.jev-liquid-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0.5rem; }
.jev-liquid-row { display: flex; flex-direction: column; gap: 0.2rem; }
.jev-liquid-actions { display: flex; gap: 0.5rem; margin-top: 0.4rem; border-top: 1px solid var(--border, #222); padding-top: 0.5rem; }
.jev-markdown-preview { background: var(--surface, #0f0f0f); border: 1px solid var(--border, #222); border-radius: 6px; padding: 1rem; font-size: 0.85rem; line-height: 1.6; color: var(--text, #e0e0e0); }
.jev-markdown-preview h1, .jev-markdown-preview h2, .jev-markdown-preview h3 { margin-top: 1rem; margin-bottom: 0.5rem; color: #fff; }
.jev-markdown-preview pre { background: #000; border: 1px solid #333; padding: 0.6rem 0.8rem; border-radius: 5px; overflow-x: auto; font-family: monospace; font-size: 0.8rem; margin: 0.5rem 0; color: #6ee7b7; }
.jev-markdown-preview code { font-family: monospace; background: #222; padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.8rem; }
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
