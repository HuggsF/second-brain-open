/* Pure presentation projection. Membership links never become knowledge relations. */
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.BrainGraphLayout = factory();
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  const CORE_ID = '@core';
  const DOMAIN_PREFIX = '@domain:';
  // Centers leave room for the renderer's 136 × 44 entity cards in either orientation.
  const ENTITY_STEP = 176;
  const ENTITY_EXTENT = Math.hypot(68, 22);
  const GROUP_GAP = 64;
  const FULL_CIRCLE = 2 * Math.PI;

  function compareId(first, second) {
    return first.id < second.id ? -1 : first.id > second.id ? 1 : 0;
  }

  function membership(source, target) {
    return {id: '@membership:' + JSON.stringify([source, target]), source, target, kind: 'membership'};
  }

  function project(data, options = {}) {
    const entities = data.nodes.slice().sort(compareId);
    const domains = [...new Set(entities.map(node => node.domain))].sort((first, second) => first < second ? -1 : first > second ? 1 : 0);
    const labels = options.domainLabels || {};
    const categories = domains.map(domain => ({
      id: DOMAIN_PREFIX + domain,
      kind: 'category',
      label: Object.prototype.hasOwnProperty.call(labels, domain) ? labels[domain] : domain,
      domain
    }));
    const nodes = [{id: CORE_ID, kind: 'core', label: 'Segundo Cérebro'}, ...categories];
    const links = categories.map(node => membership(CORE_ID, node.id));
    for (const entity of entities) {
      nodes.push({id: entity.id, kind: 'entity', label: entity.label, domain: entity.domain, entityId: entity.id});
      links.push(membership(DOMAIN_PREFIX + entity.domain, entity.id));
    }
    // The array is owned by the scene; real edge objects and all their evidence stay intact.
    return {nodes, edges: data.edges.slice().sort(compareId), links};
  }

  function groups(scene, focusDomain) {
    const categories = scene.nodes.filter(node => node.kind === 'category').sort((first, second) => {
      const firstFocused = first.domain === focusDomain, secondFocused = second.domain === focusDomain;
      return firstFocused !== secondFocused ? (firstFocused ? -1 : 1) : compareId(first, second);
    });
    const byDomain = new Map(categories.map(category => [category.domain, {category, entities: []}]));
    for (const node of scene.nodes) {
      if (node.kind === 'entity') byDomain.get(node.domain).entities.push(node);
    }
    const result = [...byDomain.values()];
    for (const group of result) group.entities.sort(compareId);
    return result;
  }

  function localRings(entities) {
    const points = new Map();
    let radius = 0, index = 0;
    while (index < entities.length) {
      let count;
      if (entities.length <= 12) {
        count = entities.length;
        radius = Math.max(164, ENTITY_STEP / (2 * Math.sin(Math.PI / Math.max(2, count))));
      } else {
        radius += ENTITY_STEP;
        // The chord between neighboring centers is at least ENTITY_STEP.
        const capacity = Math.floor(Math.PI / Math.asin(ENTITY_STEP / (2 * radius)) + 1e-9);
        count = Math.min(entities.length - index, capacity);
      }
      for (let item = 0; item < count; item++) {
        const angle = -Math.PI / 2 + FULL_CIRCLE * item / count;
        points.set(entities[index++].id, {x: radius * Math.cos(angle), y: radius * Math.sin(angle)});
      }
    }
    return {points, extent: Math.max(96, radius + ENTITY_EXTENT)};
  }

  function radial(scene) {
    const positions = new Map();
    for (const core of scene.nodes.filter(node => node.kind === 'core').sort(compareId)) positions.set(core.id, {x: 0, y: 0});
    const domains = groups(scene).map(group => ({...group, local: localRings(group.entities)}));
    if (!domains.length) return positions;

    // Each local disk reserves an angular half-sector asin(extent / radius).
    // Binary search finds a common category circle on which all sectors fit.
    const extents = domains.map(group => group.local.extent + GROUP_GAP / 2);
    let low = Math.max(...extents) + 120;
    let high = Math.max(low, extents.reduce((sum, extent) => sum + extent, 0));
    for (let step = 0; step < 48; step++) {
      const middle = (low + high) / 2;
      const needed = extents.reduce((sum, extent) => sum + 2 * Math.asin(extent / middle), 0);
      if (needed > FULL_CIRCLE) low = middle;
      else high = middle;
    }
    const radius = high;
    const halfAngles = extents.map(extent => Math.asin(extent / radius));
    const extraGap = (FULL_CIRCLE - halfAngles.reduce((sum, angle) => sum + 2 * angle, 0)) / domains.length;
    let angle = -Math.PI / 2;
    for (let index = 0; index < domains.length; index++) {
      const group = domains[index];
      const center = {x: radius * Math.cos(angle), y: radius * Math.sin(angle)};
      positions.set(group.category.id, center);
      for (const [id, point] of group.local.points) positions.set(id, {x: center.x + point.x, y: center.y + point.y});
      angle += halfAngles[index] + halfAngles[(index + 1) % domains.length] + extraGap;
    }
    return positions;
  }

  function layered(scene, options = {}) {
    const domains = groups(scene, options.focusDomain);
    let cursor = 0;
    const bands = domains.map(group => {
      // Square center spacing also prevents card collisions after transposition.
      const rows = Math.ceil(Math.sqrt(group.entities.length));
      const height = Math.max(144, (rows - 1) * ENTITY_STEP + 144);
      const band = {...group, rows, center: cursor + height / 2};
      cursor += height + GROUP_GAP;
      return band;
    });
    const positions = new Map();
    const center = domains.length ? (cursor - GROUP_GAP) / 2 : 0;
    for (const core of scene.nodes.filter(node => node.kind === 'core').sort(compareId)) positions.set(core.id, {x: 0, y: center});
    for (const band of bands) {
      positions.set(band.category.id, {x: 280, y: band.center});
      for (let index = 0; index < band.entities.length; index++) {
        const column = Math.floor(index / band.rows), row = index % band.rows;
        positions.set(band.entities[index].id, {
          x: 560 + column * ENTITY_STEP,
          y: band.center + (row - (band.rows - 1) / 2) * ENTITY_STEP
        });
      }
    }
    if (options.orientation === 'vertical') {
      for (const [id, point] of positions) positions.set(id, {x: point.y, y: point.x});
    }
    return positions;
  }

  return {project, radial, layered};
});
