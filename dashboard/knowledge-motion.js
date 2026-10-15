/* Product knowledge map. Layout and rendering share one finite SVG coordinate system. */
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.BrainKnowledgeMotion = factory();
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  const NS = 'http://www.w3.org/2000/svg';
  const DURATION = 650;
  let mountId = 0;
  const compare = (first, second) => first.id < second.id ? -1 : first.id > second.id ? 1 : 0;
  const sorted = items => (items || []).slice().sort(compare);
  const modeOf = scene => scene.mode || (scene.nodes || []).some(node => node.kind === 'core') && 'overview' || 'entity';
  const finite = (value, fallback) => Number.isFinite(value) && value > 0 ? value : fallback;
  function dimensions(scene, width = 960, height = 620) {
    return modeOf(scene) === 'overview'
      ? {width: finite(width, 960), height: finite(height, 620)}
      : {width: Math.max(1080, finite(width, 1080)), height: Math.max(680, finite(height, 680))};
  }

  function layout(scene = {}, {width = 960, height = 620} = {}) {
    const nodes = sorted(scene.nodes), positions = new Map(), mode = modeOf(scene);
    const size = dimensions(scene, width, height), cx = size.width / 2, cy = size.height / 2;
    if (mode === 'overview') {
      const categories = nodes.filter(node => node.kind === 'category');
      for (const node of nodes.filter(node => node.kind === 'core')) positions.set(node.id, {x: cx, y: cy});
      categories.forEach((node, index) => {
        const angle = -Math.PI / 2 + index * Math.PI * 2 / Math.max(1, categories.length);
        positions.set(node.id, {x: cx + (size.width / 2 - 168) * Math.cos(angle), y: cy + (size.height / 2 - 88) * Math.sin(angle)});
      });
      // Scenes normally contain only the core and five categories. An unexpected node still has a finite position.
      nodes.filter(node => !positions.has(node.id)).forEach((node, index) => positions.set(node.id, {x: 150 + index % 3 * 220, y: size.height - 70 + Math.floor(index / 3) * 90}));
    } else if (mode === 'group') {
      const categories = nodes.filter(node => node.kind !== 'entity');
      categories.forEach((node, index) => positions.set(node.id, {x: 150, y: cy + index * 100}));
      const entities = nodes.filter(node => node.kind === 'entity');
      entities.forEach((node, index) => positions.set(node.id, {x: 420 + index % 3 * (size.width - 600) / 2, y: 100 + Math.floor(index / 3) * 160}));
    } else {
      const selected = nodes.find(node => node.id === scene.selectedId) || nodes[0];
      if (selected) {
        positions.set(selected.id, {x: cx, y: cy});
        const incoming = new Set(), outgoing = new Set();
        for (const edge of scene.edges || []) {
          if (edge.source === selected.id && edge.target !== selected.id) outgoing.add(edge.target);
          if (edge.target === selected.id && edge.source !== selected.id) incoming.add(edge.source);
        }
        const left = [], right = [], extras = [];
        for (const node of nodes) {
          if (node === selected) continue;
          if (outgoing.has(node.id)) right.push(node);
          else if (incoming.has(node.id)) left.push(node);
          else extras.push(node);
        }
        for (const node of extras) (left.length <= right.length ? left : right).push(node);
        for (const [column, x, direction] of [[left, 155, 1], [right, size.width - 155, -1]]) {
          const columns = column.length > 6 ? 2 : 1, rows = Math.ceil(column.length / columns);
          column.forEach((node, index) => {
            const spacing = rows <= 1 ? 0 : Math.min(112, (size.height - 160) / (rows - 1));
            positions.set(node.id, {x: x + index % columns * 195 * direction, y: cy + (Math.floor(index / columns) - (rows - 1) / 2) * spacing});
          });
        }
      }
    }
    return new Map(nodes.map(node => [node.id, positions.get(node.id)]));
  }

  function wrapped(text, limit) {
    const words = String(text || '').trim().split(/\s+/).filter(Boolean), lines = [];
    let line = '';
    for (let word of words) {
      while (word.length > limit) {
        if (line) { lines.push(line); line = ''; }
        lines.push(word.slice(0, limit)); word = word.slice(limit);
      }
      if (!word) continue;
      if (line && line.length + word.length + 1 > limit) { lines.push(line); line = ''; }
      line += (line ? ' ' : '') + word;
    }
    if (line) lines.push(line);
    if (lines.length > 2) return [lines[0], lines[1].slice(0, limit - 1).replace(/[\s,;:.]+$/, '') + '…'];
    return lines.length ? lines : [''];
  }
  const shortened = (text, limit) => String(text || '').length > limit ? String(text).slice(0, limit - 1) + '…' : String(text || '');
  const number = value => Math.round(value * 100) / 100;
  const point = value => number(value.x) + ' ' + number(value.y);
  function boundary(node, center, toward) {
    const dx = toward.x - center.x, dy = toward.y - center.y;
    if (!dx && !dy) return {x: center.x, y: center.y};
    let ratio;
    if (node.kind === 'core') ratio = 68 / Math.hypot(dx, dy);
    else ratio = 1 / Math.max(Math.abs(dx) / (node.kind === 'category' ? 104 : 96), Math.abs(dy) / (node.kind === 'category' ? 44 : 39));
    return {x: center.x + dx * ratio, y: center.y + dy * ratio};
  }

  function mount(svg, {onNode, onEdge, onView} = {}) {
    if (!svg || !svg.ownerDocument) throw new TypeError('An SVG element is required');
    const document = svg.ownerDocument, host = document.defaultView || globalThis;
    const nodes = new Map(), edges = new Map(), memberships = new Map(), listeners = new Set();
    const markerId = 'kp-arrow-' + ++mountId;
    let scene = {mode: 'overview', nodes: [], edges: [], links: []}, positions = new Map();
    let selectedId, animation = null, disposed = false, drag = null;
    let size = dimensions(scene), viewport = {x: 0, y: 0, width: size.width, height: size.height};
    const create = (tag, attrs = {}, text) => {
      const element = document.createElementNS(NS, tag);
      for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
      if (text !== undefined) element.textContent = String(text);
      return element;
    };
    const listen = (element, type, callback, options) => {
      element.addEventListener(type, callback, options);
      const cleanup = () => { element.removeEventListener(type, callback, options); listeners.delete(cleanup); };
      listeners.add(cleanup); return cleanup;
    };
    const defs = create('defs'), marker = create('marker', {id: markerId, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse', markerUnits: 'strokeWidth'});
    marker.appendChild(create('path', {d: 'M 0 0 L 10 5 L 0 10 z', fill: 'context-stroke'}));
    defs.appendChild(marker);
    const world = create('g', {class: 'kp-world'});
    const orbit = create('ellipse', {class: 'kp-orbit', fill: 'none', 'aria-hidden': 'true', 'pointer-events': 'none'});
    const membershipLayer = create('g', {class: 'kp-memberships', 'aria-hidden': 'true'});
    const edgeLayer = create('g', {class: 'kp-edges'}), nodeLayer = create('g', {class: 'kp-nodes'});
    world.append(orbit, membershipLayer, edgeLayer, nodeLayer);
    svg.append(defs, world);
    svg.setAttribute('role', 'group');
    svg.setAttribute('aria-label', 'Mapa de conhecimento. Selecione uma categoria ou entidade para explorar.');
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    function writeViewport() {
      svg.setAttribute('viewBox', [viewport.x, viewport.y, viewport.width, viewport.height].map(number).join(' '));
      if (typeof onView === 'function') onView({...viewport, zoom: size.width / viewport.width});
    }
    function fit() {
      if (disposed) return;
      viewport = {x: 0, y: 0, width: size.width, height: size.height};
      writeViewport();
    }
    function zoom(factor) {
      if (disposed || !Number.isFinite(factor) || factor <= 0) return;
      const width = Math.max(size.width / 3, Math.min(size.width / 0.6, viewport.width / factor));
      const height = width * viewport.height / viewport.width;
      viewport = {x: viewport.x + (viewport.width - width) / 2, y: viewport.y + (viewport.height - height) / 2, width, height};
      writeViewport();
    }
    function selection() {
      for (const [id, record] of nodes) {
        record.element.setAttribute('class', 'kp-node kp-node-' + record.node.kind + ' kp-token-' + (record.node.token || 'accent') + (id === selectedId ? ' kp-selected' : ''));
        record.element.setAttribute('aria-pressed', id === selectedId ? 'true' : 'false');
      }
      for (const record of edges.values()) record.element.setAttribute('class', 'kp-link kp-edge' + (selectedId && (record.edge.source === selectedId || record.edge.target === selectedId) ? ' kp-selected' : ''));
    }
    function select(id) { if (!disposed) { selectedId = id; selection(); } }
    function activate(element, callback) {
      return [listen(element, 'click', callback), listen(element, 'keydown', event => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); callback(event); }
      })];
    }
    function reconcileNodes() {
      const ids = new Set((scene.nodes || []).map(node => node.id));
      for (const [id, record] of nodes) if (!ids.has(id)) {
        record.cleanups.forEach(cleanup => cleanup()); record.element.remove(); nodes.delete(id);
      }
      for (const node of sorted(scene.nodes)) {
        let record = nodes.get(node.id);
        if (!record) {
          const element = create('g', {'data-kp-node': node.id, role: 'button', tabindex: '0'});
          record = {node, element, cleanups: []};
          record.cleanups = activate(element, () => { if (!disposed) { select(record.node.id); if (typeof onNode === 'function') onNode(record.node); } });
          nodes.set(node.id, record); nodeLayer.appendChild(element);
        }
        record.node = node;
        const isCore = node.kind === 'core', category = node.kind === 'category';
        const label = String(node.label || node.id), subtitle = String(node.subtitle || '');
        record.element.setAttribute('aria-label', label + (subtitle ? '. ' + subtitle : ''));
        const shape = isCore ? create('circle', {class: 'kp-node-shape', r: 62}) : create('rect', {class: 'kp-node-shape', x: category ? -98 : -90, y: category ? -38 : -33, width: category ? 196 : 180, height: category ? 76 : 66, rx: category ? 14 : 10});
        const lines = wrapped(label, isCore ? 12 : 24);
        const labelText = create('text', {class: 'kp-node-label', 'text-anchor': 'middle', 'font-size': isCore ? 15 : 13, 'font-weight': 600, 'pointer-events': 'none'});
        const start = (lines.length === 1 ? 0 : -8) - (subtitle ? 5 : -4);
        lines.forEach((line, index) => labelText.appendChild(create('tspan', {x: 0, y: start + index * 17}, line)));
        const children = [create('title', {}, label + (subtitle ? ' — ' + subtitle : '')), shape, labelText];
        if (subtitle) children.push(create('text', {class: 'kp-node-subtitle', x: 0, y: isCore ? 36 : category ? 25 : 24, 'text-anchor': 'middle', 'font-size': 11, 'pointer-events': 'none'}, shortened(subtitle, isCore ? 16 : 29)));
        // Keep the interactive <g> itself: keyboard focus survives scene updates.
        record.element.replaceChildren(...children);
      }
    }
    function reconcileConnections() {
      const visible = new Set(nodes.keys());
      const real = sorted(scene.edges).filter(edge => visible.has(edge.source) && visible.has(edge.target));
      const links = sorted(scene.links).filter(edge => visible.has(edge.source) && visible.has(edge.target));
      const realIds = new Set(real.map(edge => edge.id)), linkIds = new Set(links.map(edge => edge.id));
      for (const [id, record] of edges) if (!realIds.has(id)) { record.cleanups.forEach(cleanup => cleanup()); record.element.remove(); edges.delete(id); }
      for (const [id, record] of memberships) if (!linkIds.has(id)) { record.element.remove(); memberships.delete(id); }
      const parallel = new Map();
      for (const edge of real) {
        const key = JSON.stringify([edge.source, edge.target].sort());
        if (!parallel.has(key)) parallel.set(key, []);
        parallel.get(key).push(edge);
      }
      for (const edge of real) {
        let record = edges.get(edge.id);
        if (!record) {
          const element = create('g', {'data-kp-edge': edge.id, role: 'button', tabindex: '0'});
          const path = create('path', {class: 'kp-edge-path', fill: 'none', 'marker-end': 'url(#' + markerId + ')'});
          const text = create('text', {class: 'kp-edge-label', 'text-anchor': 'middle', 'font-size': 11});
          const title = create('title');
          element.append(title, path, text);
          record = {element, path, text, title, edge, cleanups: []};
          record.cleanups = activate(element, () => { if (!disposed && typeof onEdge === 'function') onEdge(record.edge); });
          edges.set(edge.id, record); edgeLayer.appendChild(element);
        }
        record.edge = edge;
        const siblings = parallel.get(JSON.stringify([edge.source, edge.target].sort()));
        const lane = siblings.findIndex(item => item.id === edge.id);
        record.offset = edge.source === edge.target ? lane * 36 : (lane - (siblings.length - 1) / 2) * 44 * (edge.source > edge.target ? -1 : 1);
        const label = String(edge.relation || 'relação');
        record.text.textContent = shortened(label, 28);
        record.title.textContent = label + ': ' + (nodes.get(edge.source).node.label || edge.source) + ' → ' + (nodes.get(edge.target).node.label || edge.target);
        record.element.setAttribute('aria-label', record.title.textContent);
      }
      for (const edge of links) {
        let record = memberships.get(edge.id);
        if (!record) {
          const element = create('path', {class: 'kp-link kp-membership', fill: 'none', 'stroke-dasharray': '5 7', 'pointer-events': 'none'});
          record = {element, edge}; memberships.set(edge.id, record); membershipLayer.appendChild(element);
        }
        record.edge = edge;
      }
    }
    function connection(edge, offset = 0) {
      const a = positions.get(edge.source), b = positions.get(edge.target);
      if (!a || !b) return null;
      if (edge.source === edge.target) {
        const width = nodes.get(edge.source).node.kind === 'core' ? 52 : 78;
        const height = nodes.get(edge.source).node.kind === 'core' ? 40 : 33;
        const lift = 112 + Math.abs(offset);
        return {d: 'M ' + point({x: a.x + width, y: a.y - height}) + ' C ' + point({x: a.x + width + 100, y: a.y - lift}) + ' ' + point({x: a.x - width - 100, y: a.y - lift}) + ' ' + point({x: a.x - width, y: a.y - height}), label: {x: a.x, y: a.y - lift + 10}};
      }
      const dx = b.x - a.x, dy = b.y - a.y, distance = Math.hypot(dx, dy) || 1;
      const middle = {x: (a.x + b.x) / 2 - dy / distance * offset, y: (a.y + b.y) / 2 + dx / distance * offset};
      const start = boundary(nodes.get(edge.source).node, a, middle), end = boundary(nodes.get(edge.target).node, b, middle);
      return {d: 'M ' + point(start) + ' Q ' + point(middle) + ' ' + point(end), label: {x: (start.x + 2 * middle.x + end.x) / 4, y: (start.y + 2 * middle.y + end.y) / 4 - 7}};
    }
    function render() {
      for (const [id, record] of nodes) {
        const position = positions.get(id);
        if (position) record.element.setAttribute('transform', 'translate(' + point(position) + ')');
      }
      for (const record of memberships.values()) { const geometry = connection(record.edge); if (geometry) record.element.setAttribute('d', geometry.d); }
      for (const record of edges.values()) {
        const geometry = connection(record.edge, record.offset);
        if (!geometry) continue;
        record.path.setAttribute('d', geometry.d);
        record.text.setAttribute('x', number(geometry.label.x)); record.text.setAttribute('y', number(geometry.label.y));
      }
    }
    function stop() { if (animation !== null) host.cancelAnimationFrame(animation); animation = null; }
    function update(nextScene, {animate = true, motion = true, selectedId: requestedSelection} = {}) {
      if (disposed) return;
      stop();
      const previousMode = modeOf(scene);
      selectedId = requestedSelection === undefined ? nextScene.selectedId : requestedSelection;
      scene = {...nextScene, selectedId};
      size = dimensions(scene);
      const target = layout(scene), from = new Map();
      for (const [id, position] of target) from.set(id, positions.get(id) || positions.get((nodes.get(id) || {}).node?.groupId) || {x: size.width / 2, y: size.height / 2});
      positions = from;
      reconcileNodes(); reconcileConnections(); selection();
      orbit.setAttribute('cx', size.width / 2); orbit.setAttribute('cy', size.height / 2);
      orbit.setAttribute('rx', size.width / 2 - 168); orbit.setAttribute('ry', size.height / 2 - 88);
      orbit.setAttribute('display', modeOf(scene) === 'overview' ? 'inline' : 'none');
      if (previousMode !== modeOf(scene)) fit();
      const reduced = typeof host.matchMedia === 'function' && host.matchMedia('(prefers-reduced-motion: reduce)').matches;
      if (!animate || !motion || reduced || !target.size || typeof host.requestAnimationFrame !== 'function') { positions = target; render(); return; }
      render();
      const start = host.performance && typeof host.performance.now === 'function' ? host.performance.now() : Date.now();
      function frame(now) {
        if (disposed) return;
        const elapsed = Math.max(0, Math.min(1, (now - start) / DURATION));
        const eased = elapsed * elapsed * (3 - 2 * elapsed);
        positions = new Map([...target].map(([id, end]) => { const begin = from.get(id); return [id, {x: begin.x + (end.x - begin.x) * eased, y: begin.y + (end.y - begin.y) * eased}]; }));
        render();
        animation = elapsed < 1 ? host.requestAnimationFrame(frame) : null;
      }
      animation = host.requestAnimationFrame(frame);
    }
    listen(svg, 'pointerdown', event => {
      if (event.button !== undefined && event.button !== 0) return;
      for (let element = event.target; element && element !== svg; element = element.parentNode) {
        if (element.getAttribute && (element.getAttribute('data-kp-node') !== null || element.getAttribute('data-kp-edge') !== null)) return;
      }
      drag = {id: event.pointerId, x: event.clientX, y: event.clientY, viewport: {...viewport}};
      if (svg.setPointerCapture) svg.setPointerCapture(event.pointerId);
    });
    listen(svg, 'pointermove', event => {
      if (!drag || event.pointerId !== drag.id) return;
      const rect = svg.getBoundingClientRect(), scale = Math.max(drag.viewport.width / Math.max(1, rect.width), drag.viewport.height / Math.max(1, rect.height));
      viewport = {...drag.viewport, x: drag.viewport.x - (event.clientX - drag.x) * scale, y: drag.viewport.y - (event.clientY - drag.y) * scale};
      writeViewport();
    });
    function endDrag(event) {
      if (drag && event.pointerId === drag.id) { if (svg.releasePointerCapture) svg.releasePointerCapture(event.pointerId); drag = null; }
    }
    listen(svg, 'pointerup', endDrag); listen(svg, 'pointercancel', endDrag);
    const observer = typeof host.ResizeObserver === 'function' ? new host.ResizeObserver(() => { if (!disposed) writeViewport(); }) : null;
    if (observer) observer.observe(svg);
    fit();
    function dispose() {
      if (disposed) return;
      stop(); disposed = true; drag = null;
      if (observer) observer.disconnect();
      for (const cleanup of [...listeners]) cleanup();
      nodes.clear(); edges.clear(); memberships.clear(); positions.clear();
      defs.remove(); world.remove();
    }
    return {update, select, zoom, fit, dispose};
  }
  return {layout, mount};
});
