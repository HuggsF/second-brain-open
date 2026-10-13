/* Teams page: team cards, communication graph, and template launcher. */
(function () {
'use strict';

const PROTOCOL_LABELS = {
  handoff: { label: 'Handoff', badge: 'warn', description: 'Transferência formal de responsabilidade entre times' },
  demand: { label: 'Demanda', badge: 'blue', description: 'Abertura de tarefa ou requisito para outro time' },
  adr: { label: 'ADR', badge: 'violet', description: 'Decisão arquitetural que impacta outro time' },
  'webhook-contract': { label: 'Contrato', badge: 'accent', description: 'Contrato de integração entre sistemas' },
  playbook: { label: 'Playbook', badge: 'accent', description: 'Procedimento operacional documentado' },
  broadcast: { label: 'Broadcast', badge: 'good', description: 'Comunicação e alertas para todos os times' },
};

function render(main, U) {
  const { el, button, badge, head, panelTitle, notify, graph: G, row } = U;
  const teams = G.teams || [];
  const protocols = G.protocols || {};
  const templates = G.templates || [];

  main.append(head(
    'TIMES / ENGENHARIA & PRODUTO',
    'Quem faz o quê, e como se comunicam.',
    'Estrutura técnica full-cycle, domínios de negócio, protocolos e templates padronizados.',
    [button('+ Novo documento', () => openTemplateDialog(), 'primary')]
  ));

  if (!teams.length) {
    main.append(el('section', { class: 'panel' },
      U.empty(
        'Nenhum time cadastrado',
        'Adicione vault/teams/teams.yaml e regenere o snapshot.',
        button('Ver templates →', () => U.navigate({ page: 'knowledge', doc: '_templates/adr.md' }), 'subtle')
      )
    ));
    return;
  }

  // --- Full-Cycle Model Banner ---
  const banner = el('section', { class: 'panel', style: 'border-left: 4px solid var(--accent); margin-bottom: 20px;' },
    el('div', { style: 'display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;' },
      el('div', { style: 'display: flex; align-items: center; gap: 10px;' },
        badge('Dev Full Cycle', 'accent'),
        badge('Equipe Enxuta: 2 Devs', 'blue'),
        el('strong', {}, 'Engenharia Unificada KIOSK Brands')
      ),
      el('span', { class: 'small muted' }, 'Desenvolvimento · DevOps · QA · Arquitetura')
    ),
    el('p', { class: 'small', style: 'margin: 10px 0 0; line-height: 1.5; color: var(--text);' },
      'A equipe técnica opera com total autonomia no ciclo completo de software: do entendimento do produto/negócio à codificação, testes, automação de CI/CD e sustentação em produção. Os domínios de negócio abrem demandas e recebem entregas por meio de protocolos explícitos, evitando sobreposição indevida de responsabilidades.'
    )
  );
  main.append(banner);

  // --- Stats ---
  const totalChannels = teams.reduce((sum, t) => sum + (t.channels || []).length, 0);
  const totalSystems = teams.reduce((sum, t) => sum + (t.systems || []).length, 0);
  const engTeams = teams.filter(t => t.category === 'engineering');
  const bizTeams = teams.filter(t => t.category !== 'engineering');

  const stats = el('div', { class: 'stats' });
  for (const [value, title, foot] of [
    [engTeams.length, 'Times Tech', 'Disciplinas full-cycle (Dev, DevOps, QA, Arq)'],
    [bizTeams.length, 'Domínios', 'Áreas de negócio & produto da holding'],
    [totalChannels, 'Canais', 'Protocolos ativos de comunicação'],
    [totalSystems, 'Sistemas', 'Sistemas catalogados sob governança'],
  ]) {
    stats.append(el('div', { class: 'panel stat' },
      el('div', { class: 'stat-value' }, value),
      el('div', { class: 'stat-title' }, title),
      el('div', { class: 'stat-foot' }, foot)
    ));
  }
  main.append(stats);

  function renderTeamCard(team) {
    const card = el('section', { class: 'panel', 'aria-label': 'Time ' + team.name });
    const systemCount = (team.systems || []).length;
    const ruleCount = (team.rules || []).length;
    const channelCount = (team.channels || []).length;
    const isEng = team.category === 'engineering';

    card.append(
      el('div', { class: 'panel-head' },
        el('div', {},
          el('div', { style: 'display: flex; align-items: center; gap: 8px; margin-bottom: 4px;' },
            el('h2', { style: 'margin: 0;' }, team.name),
            badge(isEng ? 'Engenharia' : 'Negócio', isEng ? 'accent' : 'blue')
          ),
          el('p', { class: 'small muted', style: 'margin: 0;' }, team.scope || '')
        )
      )
    );

    const tags = el('div', { class: 'tag-row', style: 'margin-top: 10px;' });
    tags.append(badge(systemCount + ' sistemas', 'blue'));
    if (ruleCount) tags.append(badge(ruleCount + ' regras', 'good'));
    tags.append(badge(channelCount + ' canais', 'accent'));
    card.append(tags);

    // Systems list
    if (team.systems && team.systems.length) {
      const systemsList = el('details', { class: 'toc', style: 'margin-top: 12px;' },
        el('summary', {}, 'Sistemas vinculados (' + systemCount + ')')
      );
      for (const sys of team.systems) {
        const docRef = 'systems/' + sys + '.md';
        if (G.documents[docRef]) {
          systemsList.append(el('a', {
            href: '#page=knowledge&doc=' + encodeURIComponent(docRef),
            onclick: e => { e.preventDefault(); U.openDoc(docRef); }
          }, U.documentTitle(docRef)));
        } else {
          systemsList.append(el('span', { class: 'small muted', style: 'display:block;padding:4px 0' }, sys));
        }
      }
      card.append(systemsList);
    }

    // Channels
    if (team.channels && team.channels.length) {
      const channelsList = el('div', { style: 'margin-top:12px; border-top: 1px solid var(--border); padding-top: 8px;' });
      for (const ch of team.channels) {
        const proto = PROTOCOL_LABELS[ch.protocol] || { label: ch.protocol, badge: '' };
        const targetTeam = teams.find(t => t.id === ch.target);
        const targetName = ch.target === 'all' ? 'Todos os times' : (targetTeam ? targetTeam.name : ch.target);
        channelsList.append(el('div', { style: 'display:flex;align-items:center;gap:8px;margin:6px 0;font-size:12px' },
          badge(proto.label, proto.badge),
          el('span', { class: 'muted' }, '→'),
          el('strong', {}, targetName),
        ));
      }
      card.append(channelsList);
    }

    // Link to team doc
    const teamDoc = 'teams/' + team.id + '.md';
    if (G.documents[teamDoc]) {
      card.append(el('div', { style: 'margin-top:14px' },
        button('Ver documentação →', () => U.openDoc(teamDoc), 'subtle')
      ));
    }

    return card;
  }

  // --- Engineering Section ---
  main.append(panelTitle('Times de Tecnologia (Engenharia Full-Cycle)', 'Disciplinas e responsabilidades técnicas operadas pela dupla de devs'));
  const engGrid = el('div', { class: 'grid-2', style: 'margin-bottom: 24px;' });
  for (const team of engTeams) {
    engGrid.append(renderTeamCard(team));
  }
  main.append(engGrid);

  // --- Business Section ---
  main.append(panelTitle('Domínios de Produto & Negócio', 'Áreas operacionais da holding KIOSK Brands e parceiros integrados'));
  const bizGrid = el('div', { class: 'grid-3', style: 'margin-bottom: 24px;' });
  for (const team of bizTeams) {
    bizGrid.append(renderTeamCard(team));
  }
  main.append(bizGrid);

  // --- Communication graph (SVG) ---
  const commSection = el('section', { class: 'panel', style: 'margin-top:22px' },
    panelTitle('Mapa de comunicação inter-times', 'Fluxo de protocolos entre engenharia e domínios de negócio')
  );
  const svg = buildCommGraph(teams);
  commSection.append(svg);

  // --- Protocols reference ---
  const protoSection = el('section', { class: 'panel', style: 'margin-top:22px' },
    panelTitle('Protocolos de comunicação', 'Como as equipes trocam demandas, decisões e handoffs')
  );
  const protoTable = el('div', { class: 'table-wrap' });
  const table = el('table', { class: 'data-table' });
  table.append(el('thead', {},
    el('tr', {},
      el('th', {}, 'Protocolo'),
      el('th', {}, 'Descrição'),
      el('th', {}, 'Artefato gerado'),
    )
  ));
  const tbody = el('tbody');
  for (const [key, proto] of Object.entries(protocols)) {
    const info = PROTOCOL_LABELS[key] || { label: key, badge: '' };
    tbody.append(el('tr', {},
      el('td', {}, badge(info.label, info.badge)),
      el('td', {}, proto.description || info.description || ''),
      el('td', { class: 'small muted' }, proto.artifact || '—'),
    ));
  }
  table.append(tbody);
  protoTable.append(table);
  protoSection.append(protoTable);

  main.append(el('div', { class: 'grid-2' }, commSection, protoSection));

  // --- Templates section ---
  const tplSection = el('section', { class: 'panel', style: 'margin-top:22px' },
    panelTitle('Templates de documentação', templates.length + ' templates padronizados disponíveis', button('+ Novo documento', () => openTemplateDialog(), 'primary'))
  );
  if (templates.length) {
    for (const tpl of templates) {
      tplSection.append(row(
        tpl.title || tpl.id,
        'vault/_templates/' + tpl.id + '.md · ' + tpl.lines + ' linhas',
        () => U.openDoc(tpl.path)
      ));
    }
  } else {
    tplSection.append(el('p', { class: 'small muted' }, 'Nenhum template encontrado em vault/_templates/.'));
  }
  main.append(tplSection);

  // --- Template dialog ---
  function openTemplateDialog() {
    const existing = document.getElementById('template-dialog');
    if (existing) existing.remove();

    const dialog = el('dialog', { id: 'template-dialog', 'aria-labelledby': 'tpl-title' });
    const head = el('div', { class: 'dialog-head' },
      el('h2', { id: 'tpl-title' }, 'Novo documento a partir de template'),
      button('×', () => dialog.close(), 'icon-button')
    );
    dialog.append(head);
    dialog.append(el('p', { class: 'small muted' }, 'Escolha um template. O arquivo será aberto na biblioteca para visualização e cópia com estrutura padronizada.'));

    for (const tpl of templates) {
      dialog.append(el('button', {
        class: 'search-result',
        onclick: () => {
          dialog.close();
          U.openDoc(tpl.path);
          notify('Template "' + tpl.id + '" aberto. Preencha conforme o padrão.');
        }
      },
        el('strong', {}, tpl.title || tpl.id),
        badge(tpl.id, 'accent'),
        el('span', { class: 'snippet' }, 'vault/_templates/' + tpl.id + '.md'),
      ));
    }

    if (!templates.length) {
      dialog.append(el('p', { class: 'callout warn' }, 'Nenhum template disponível. Adicione arquivos em vault/_templates/ e regenere o snapshot.'));
    }

    dialog.addEventListener('close', () => dialog.remove());
    document.body.append(dialog);
    dialog.showModal();
  }
}

function buildCommGraph(teams) {
  const W = 880, H = 420, CX = W / 2, CY = H / 2, R = 150;
  const n = teams.length;
  const positions = teams.map((t, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2;
    return { x: CX + R * Math.cos(angle), y: CY + R * Math.sin(angle), team: t };
  });

  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', 'Mapa de comunicação entre times');
  svg.style.width = '100%';
  svg.style.maxHeight = '420px';

  const defs = document.createElementNS(ns, 'defs');
  const marker = document.createElementNS(ns, 'marker');
  marker.setAttribute('id', 'team-arrow');
  marker.setAttribute('viewBox', '0 0 10 10');
  marker.setAttribute('refX', '10');
  marker.setAttribute('refY', '5');
  marker.setAttribute('markerWidth', '7');
  marker.setAttribute('markerHeight', '7');
  marker.setAttribute('orient', 'auto-start-reverse');
  const path = document.createElementNS(ns, 'path');
  path.setAttribute('d', 'M 0 0 L 10 5 L 0 10 z');
  path.setAttribute('fill', 'var(--muted)');
  marker.append(path);
  defs.append(marker);
  svg.append(defs);

  // Edges
  for (let i = 0; i < positions.length; i++) {
    const from = positions[i];
    const channels = from.team.channels || [];
    for (const ch of channels) {
      if (ch.target === 'all') {
        for (let j = 0; j < positions.length; j++) {
          if (j === i) continue;
          drawEdge(svg, ns, from, positions[j], ch.protocol);
        }
      } else {
        const j = positions.findIndex(p => p.team.id === ch.target);
        if (j >= 0) drawEdge(svg, ns, from, positions[j], ch.protocol);
      }
    }
  }

  // Nodes
  for (const pos of positions) {
    const isEng = pos.team.category === 'engineering';
    const g = document.createElementNS(ns, 'g');
    const circle = document.createElementNS(ns, 'circle');
    circle.setAttribute('cx', pos.x);
    circle.setAttribute('cy', pos.y);
    circle.setAttribute('r', '28');
    circle.setAttribute('fill', 'var(--panel2)');
    circle.setAttribute('stroke', isEng ? 'var(--accent)' : 'var(--blue)');
    circle.setAttribute('stroke-width', isEng ? '2.5' : '1.5');
    g.append(circle);

    const text = document.createElementNS(ns, 'text');
    text.setAttribute('x', pos.x);
    text.setAttribute('y', pos.y + 1);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('dominant-baseline', 'central');
    text.setAttribute('fill', 'var(--text)');
    text.setAttribute('font-size', '10');
    text.setAttribute('font-weight', '700');
    const abbr = pos.team.id.toUpperCase().slice(0, 4);
    text.textContent = abbr;
    g.append(text);

    const label = document.createElementNS(ns, 'text');
    label.setAttribute('x', pos.x);
    label.setAttribute('y', pos.y + 42);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('fill', isEng ? 'var(--accent)' : 'var(--muted)');
    label.setAttribute('font-size', '10');
    label.setAttribute('font-weight', isEng ? '600' : '400');
    label.textContent = pos.team.name.length > 22 ? pos.team.name.slice(0, 20) + '…' : pos.team.name;
    g.append(label);

    svg.append(g);
  }

  return svg;
}

function drawEdge(svg, ns, from, to, protocol) {
  const dx = to.x - from.x, dy = to.y - from.y;
  const dist = Math.sqrt(dx * dx + dy * dy);
  if (dist === 0) return;
  const ux = dx / dist, uy = dy / dist;
  const x1 = from.x + ux * 30, y1 = from.y + uy * 30;
  const x2 = to.x - ux * 30, y2 = to.y - uy * 30;

  const colors = {
    handoff: 'var(--warn)', demand: 'var(--blue)', adr: 'var(--violet)',
    'webhook-contract': 'var(--accent)', playbook: 'var(--accent)', broadcast: 'var(--good)',
  };

  const line = document.createElementNS(ns, 'line');
  line.setAttribute('x1', x1);
  line.setAttribute('y1', y1);
  line.setAttribute('x2', x2);
  line.setAttribute('y2', y2);
  line.setAttribute('stroke', colors[protocol] || 'var(--muted)');
  line.setAttribute('stroke-width', '1.5');
  line.setAttribute('marker-end', 'url(#team-arrow)');
  if (protocol === 'broadcast') line.setAttribute('stroke-dasharray', '5 4');
  svg.append(line);
}

window.BrainTeams = Object.freeze({ render });
})();
