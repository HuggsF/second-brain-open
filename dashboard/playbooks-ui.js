/**
 * playbooks-ui.js — Aba de Playbooks do Second Brain Dashboard
 *
 * Lê os playbooks diretamente do vault via /api/playbooks/
 * e renderiza lista + viewer com markdown, status badge e referência a regras.
 *
 * Padrão: window.BrainPlaybooks.render(main, api)
 */
(function () {
  'use strict';

  // ── Status colors ─────────────────────────────────────────────────────────
  const STATUS_LABEL = { active: 'Ativo', draft: 'Rascunho', deprecated: 'Depreciado' };
  const STATUS_CLASS = { active: 'green', draft: 'blue', deprecated: 'muted' };

  // ── Parse YAML frontmatter ────────────────────────────────────────────────
  function parseFrontmatter(text) {
    if (!text.startsWith('---')) return { meta: {}, body: text };
    const end = text.indexOf('\n---', 3);
    if (end === -1) return { meta: {}, body: text };
    const raw = text.slice(3, end).trim();
    const meta = {};
    for (const line of raw.split('\n')) {
      const colon = line.indexOf(':');
      if (colon === -1) continue;
      const key = line.slice(0, colon).trim();
      let val = line.slice(colon + 1).trim();
      // Parse arrays: [A, B, C]
      if (val.startsWith('[') && val.endsWith(']')) {
        val = val.slice(1, -1).split(',').map(s => s.trim().replace(/^['"]|['"]$/g, ''));
      }
      meta[key] = val;
    }
    return { meta, body: text.slice(end + 4).trim() };
  }

  // ── Fetch playbook list from API ──────────────────────────────────────────
  async function fetchList() {
    try {
      const r = await fetch('/api/playbooks/', { credentials: 'same-origin' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return await r.json();
    } catch (e) {
      return { error: e.message };
    }
  }

  async function fetchPlaybook(id) {
    try {
      const r = await fetch('/api/playbooks/' + encodeURIComponent(id), { credentials: 'same-origin' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return await r.json();
    } catch (e) {
      return { error: e.message };
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  function render(main, api) {
    const { el, button, badge, empty, head, panelTitle, row, navigate, update, notify } = api;
    const route = api.route;

    main.innerHTML = '';

    // Page header
    main.append(head(
      'PLAYBOOKS',
      'Guias de teste e diagnóstico',
      'Procedimentos verificáveis que validam regras e documentam resultados no Second Brain.',
      button('Novo playbook →', () => notify('Crie o arquivo em vault/playbooks/ seguindo o template.'), 'subtle')
    ));

    const layout = el('div', { class: 'workspace-layout' });
    main.append(layout);

    // ── Sidebar: list ──────────────────────────────────────────────────────
    const sidebar = el('section', { class: 'floor-section', style: 'max-width:340px;min-width:240px;' });
    layout.append(sidebar);
    sidebar.append(panelTitle('Todos os playbooks', '10 procedimentos no vault'));

    const listEl = el('div', { class: 'entity-list', style: 'margin-top:0.5rem;' });
    sidebar.append(listEl);

    // ── Main: viewer ───────────────────────────────────────────────────────
    const viewer = el('article', {
      class: 'panel reader',
      'aria-label': 'Conteúdo do playbook',
      tabindex: -1,
      style: 'flex:1;'
    });
    layout.append(viewer);

    const selectedId = route.doc || null;

    // Load and render list
    fetchList().then(data => {
      listEl.innerHTML = '';
      if (data.error) {
        listEl.append(el('p', { class: 'callout warn' }, '⚠ ' + data.error));
        listEl.append(el('p', { class: 'small muted' }, 'Certifique-se de que serve.py está rodando com suporte a /api/playbooks/'));
        return;
      }

      const { playbooks = [] } = data;
      if (!playbooks.length) {
        listEl.append(empty('Nenhum playbook encontrado', 'Crie arquivos .md em vault/playbooks/'));
        return;
      }

      for (const pb of playbooks) {
        const isSelected = pb.id === selectedId;
        const item = el('button', {
          type: 'button',
          class: 'row-link' + (isSelected ? ' row-link--active' : ''),
          onclick: () => {
            update({ doc: pb.id });
            loadPlaybook(pb.id);
          }
        },
          el('span', {},
            el('span', { class: 'row-title' }, pb.id + ' · ' + (pb.title || pb.id)),
            el('span', { class: 'row-meta' },
              badge(STATUS_LABEL[pb.status] || pb.status || '—', STATUS_CLASS[pb.status] || ''),
              ' · ', (pb.validates || []).join(', ') || '—'
            )
          ),
          el('span', { class: 'row-arrow', 'aria-hidden': true }, '↗')
        );
        listEl.append(item);
      }

      // Auto-open first or selected
      const toOpen = selectedId
        ? playbooks.find(p => p.id === selectedId) || playbooks[0]
        : playbooks[0];
      if (toOpen) loadPlaybook(toOpen.id);
    });

    // ── Load individual playbook ───────────────────────────────────────────
    function loadPlaybook(id) {
      viewer.innerHTML = '';
      viewer.append(el('p', { class: 'small muted', style: 'padding:1rem' }, 'Carregando ' + id + '…'));

      // Highlight active in list
      for (const btn of listEl.querySelectorAll('.row-link')) {
        btn.classList.toggle('row-link--active', btn.textContent.startsWith(id));
      }

      fetchPlaybook(id).then(data => {
        viewer.innerHTML = '';

        if (data.error) {
          viewer.append(el('p', { class: 'callout warn' }, '⚠ ' + data.error));
          return;
        }

        const { meta, body } = parseFrontmatter(data.content || '');
        const status = meta.status || 'draft';
        const validates = Array.isArray(meta.validates) ? meta.validates : (meta.validates ? [meta.validates] : []);
        const targets = Array.isArray(meta.targets) ? meta.targets : (meta.targets ? [meta.targets] : []);

        // Header
        const headerEl = el('header', { class: 'reader-head' },
          el('span', { class: 'eyebrow' }, 'PLAYBOOK · ' + (meta.environment || 'local').toUpperCase()),
          el('h2', {}, meta.title || id),
          el('p', { class: 'path' }, 'vault/playbooks/' + id.toLowerCase().replace(/[^a-z0-9]+/g, '-') + '.md'),
          el('div', { class: 'action-row' },
            badge(STATUS_LABEL[status] || status, STATUS_CLASS[status] || ''),
            ...validates.map(r => badge(r, 'blue')),
            ...targets.map(t => badge(t, '')),
            button('Copiar referência', () => {
              navigator.clipboard?.writeText(id + ' · ' + (meta.title || '')).then(() => notify('Copiado.'));
            }, 'subtle')
          )
        );
        viewer.append(headerEl);

        // Metadata strip
        const metaStrip = el('dl', { class: 'provenance', style: 'display:flex;gap:1.5rem;flex-wrap:wrap;padding:0.75rem 1rem;font-size:0.8rem;' });
        const addMeta = (dt, dd) => { metaStrip.append(el('dt', { style: 'opacity:.6' }, dt), el('dd', {}, dd)); };
        addMeta('ID', meta.id || id);
        addMeta('Status', STATUS_LABEL[status] || status);
        addMeta('Valida', validates.join(', ') || '—');
        addMeta('Ambiente', meta.environment || '—');
        addMeta('Alvo', targets.join(', ') || '—');
        viewer.append(metaStrip);

        // Markdown body
        if (window.BrainMarkdown && body) {
          const contentEl = el('div', { class: 'markdown', style: 'padding:1rem 1.25rem;' });
          window.BrainMarkdown.render(contentEl, body, {
            onWikiLink: (wiki) => {
              notify('Wikilink: ' + wiki + ' — use a aba Conhecimento para navegar.');
            }
          });
          viewer.append(contentEl);
        } else if (body) {
          viewer.append(el('pre', { style: 'white-space:pre-wrap;padding:1rem;' }, body));
        } else {
          viewer.append(el('p', { class: 'small muted', style: 'padding:1rem' }, 'Playbook sem corpo de texto.'));
        }

        viewer.focus({ preventScroll: true });
      });
    }
  }

  window.BrainPlaybooks = { render };
})();
