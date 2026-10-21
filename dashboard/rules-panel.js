/* Operational Rules panel — displays the 74 Codex-cataloged invariants. */
(function () {
  'use strict';

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') node.className = v;
      else if (k === 'text') node.textContent = v;
      else if (k === 'style') node.style.cssText = String(v);
      else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? '' : String(v));
    }
    for (const child of children.flat(Infinity)) if (child != null && child !== false) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    return node;
  }

  const CATEGORY_LABELS = {
    emission: { label: 'Emissão e Segurança', color: '#ef4444' },
    preflight: { label: 'Preflight Logístico', color: '#f59e0b' },
    nfe: { label: 'Admissão NF-e', color: '#10b981' },
    recovery: { label: 'Recuperação Logística', color: '#3b82f6' },
    weight: { label: 'Cache de Peso', color: '#8b5cf6' },
    monitor: { label: 'Monitor de Fila', color: '#06b6d4' },
    logging: { label: 'Logging', color: '#64748b' },
    deploy: { label: 'Deploy e Rollback', color: '#ec4899' },
  };

  async function fetchRules(category) {
    try {
      const url = category ? `/api/operational-rules?category=${category}` : '/api/operational-rules';
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      return [];
    }
  }

  function renderRuleRow(rule) {
    const cat = CATEGORY_LABELS[rule.category] || { label: rule.category, color: '#888' };
    return el('tr', { class: 'rule-row' },
      el('td', { class: 'rule-id' }, el('code', {}, rule.id)),
      el('td', {},
        el('span', { class: 'rule-badge', style: `background:${cat.color}22;color:${cat.color};border:1px solid ${cat.color}44` }, cat.label)
      ),
      el('td', { class: 'rule-desc' }, rule.description),
      el('td', { class: 'rule-source muted' }, rule.source_doc || '-')
    );
  }

  async function renderRules(container) {
    container.innerHTML = '';
    container.appendChild(el('h1', {}, 'Regras Operacionais do Hub'));
    container.appendChild(el('p', { class: 'muted' }, '74 invariantes catalogados pelo agente Codex — fonte de verdade para validações e playbooks.'));

    // Category filter
    const filterRow = el('div', { class: 'rules-filter' });
    const allBtn = el('button', { class: 'filter-btn active', onclick: () => loadRules(null) }, 'Todas');
    filterRow.appendChild(allBtn);
    for (const [key, meta] of Object.entries(CATEGORY_LABELS)) {
      const btn = el('button', { class: 'filter-btn', style: `--cat-color:${meta.color}`, onclick: () => loadRules(key) }, meta.label);
      btn.dataset.category = key;
      filterRow.appendChild(btn);
    }
    container.appendChild(filterRow);

    const table = el('table', { class: 'rules-table' });
    const thead = el('thead', {},
      el('tr', {},
        el('th', {}, 'ID'),
        el('th', {}, 'Categoria'),
        el('th', {}, 'Descrição'),
        el('th', {}, 'Fonte')
      )
    );
    const tbody = el('tbody', { id: 'rules-tbody' });
    table.appendChild(thead);
    table.appendChild(tbody);
    container.appendChild(table);

    const countLabel = el('p', { class: 'muted rules-count', id: 'rules-count' });
    container.appendChild(countLabel);

    async function loadRules(category) {
      filterRow.querySelectorAll('.filter-btn').forEach(b => b.classList.toggle('active', category ? b.dataset.category === category : !b.dataset.category));
      tbody.innerHTML = '';
      const rules = await fetchRules(category);
      if (!rules.length) {
        tbody.appendChild(el('tr', {}, el('td', { colspan: '4', class: 'muted' }, 'Nenhuma regra encontrada. Verifique se o documento hub-regras-operacionais-codex.md existe no vault.')));
      } else {
        rules.forEach(r => tbody.appendChild(renderRuleRow(r)));
      }
      document.getElementById('rules-count').textContent = `${rules.length} regra(s) exibida(s)`;
    }

    await loadRules(null);
  }

  window.renderRules = renderRules;
})();
