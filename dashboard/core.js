/* Recuperação local determinística. Nenhum modelo, serviço ou ferramenta é executado. */
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.BrainCore = factory();
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  const MAX_NODES = 5000, MAX_EDGES = 30000, MAX_NEIGHBORS = 80, MAX_LOCAL_EDGES = 240;
  const STOP_WORDS = new Set(('a ao aos as o os um uma uns umas de da das do dos e em no na nos nas para por com que qual quais como quando onde porque por que se ou sobre pelo pela pelos pelas este esta esses essas isso isto the a an of and to in on for is are what how why').split(' '));
  const TOOL_NAMES = new Set(['search', 'read_graph', 'read_sources']);
  const ROLES = new Set(['researcher', 'reviewer', 'writer', 'dev', 'devops', 'qa', 'architect']);

  function normalize(text) {
    return String(text == null ? '' : text).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR').replace(/\b([a-z])&([a-z])\b/g, '$1$2').replace(/\s+/g, ' ').trim();
  }

  function tokens(text) {
    return [...new Set((normalize(text).match(/[a-z0-9]+/g) || []).filter(token => token.length > 1 && !STOP_WORDS.has(token)))].slice(0, 32);
  }

  function bounded(value, fallback, min, max) {
    const number = Number(value);
    return Number.isFinite(number) ? Math.max(min, Math.min(max, Math.floor(number))) : fallback;
  }

  function catalog(graph) {
    const nodes = [], ids = new Set();
    for (const node of Array.isArray(graph && graph.nodes) ? graph.nodes.slice(0, MAX_NODES) : []) {
      if (!node || typeof node.id !== 'string' || ids.has(node.id)) continue;
      ids.add(node.id); nodes.push(node);
    }
    const edges = [], edgeIds = new Set();
    for (const edge of Array.isArray(graph && graph.edges) ? graph.edges.slice(0, MAX_EDGES) : []) {
      if (!edge || typeof edge.id !== 'string' || edgeIds.has(edge.id) || !ids.has(edge.source) || !ids.has(edge.target)) continue;
      edgeIds.add(edge.id); edges.push(edge);
    }
    return { nodes, edges, ids };
  }

  function documents(graph) {
    const source = graph && graph.documents;
    if (!source || typeof source !== 'object' || Array.isArray(source)) return [];
    return Object.entries(source).filter(([ref, document]) => typeof ref === 'string' && document && typeof document.text === 'string').slice(0, 2000);
  }

  function categoryOf(ref) {
    const parts = String(ref || '').replace(/\\/g, '/').split('/');
    return parts.length > 1 ? parts[0] : 'general';
  }

  // Headers dentro de cercas são conteúdo. Os offsets continuam sendo os do arquivo original.
  function sections(text) {
    const lines = text.split(/\r?\n/), result = [];
    let start = 0, title = 'Introdução', fence = null;
    for (let i = 0; i < lines.length; i++) {
      const mark = lines[i].match(/^\s{0,3}(`{3,}|~{3,})/);
      if (mark) {
        if (!fence) fence = { char: mark[1][0], length: mark[1].length };
        else if (mark[1][0] === fence.char && mark[1].length >= fence.length && lines[i].trim().replace(/[`~]/g, '') === '') fence = null;
        continue;
      }
      if (fence) continue;
      const heading = lines[i].match(/^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$/);
      if (heading) {
        if (i > start && lines.slice(start, i).some(line => line.trim())) result.push({ title, start, end: i - 1 });
        title = heading[1]; start = i;
      }
    }
    if (start < lines.length && lines.slice(start).some(line => line.trim())) result.push({ title, start, end: lines.length - 1 });
    return { lines, sections: result };
  }

  function matches(word, queryToken) {
    return word === queryToken || (queryToken.length >= 4 && word.startsWith(queryToken));
  }

  function relevance(text, queryTokens, phrase) {
    const normalized = normalize(text), words = new Set(normalized.match(/[a-z0-9]+/g) || []);
    const found = queryTokens.filter(token => [...words].some(word => matches(word, token)));
    if (!found.length) return { score: 0, found: [] };
    const score = found.length / queryTokens.length * 100 + found.length * 4 + (phrase && normalized.includes(phrase) ? 35 : 0);
    return { score, found };
  }

  function bestPassage(text, queryTokens, phrase) {
    const parsed = sections(text);
    let best = null;
    for (const section of parsed.sections) {
      const block = parsed.lines.slice(section.start, section.end + 1).join('\n');
      const bodyRank = relevance(block, queryTokens, phrase), titleRank = relevance(section.title, queryTokens, phrase);
      const score = bodyRank.score + titleRank.score * 0.55;
      if (!best || score > best.score) best = { section, score, found: bodyRank.found };
    }
    if (!best) return null;
    let center = best.section.start, lineScore = -1;
    for (let i = best.section.start; i <= best.section.end; i++) {
      const rank = relevance(parsed.lines[i], queryTokens, phrase).score;
      if (rank > lineScore) { center = i; lineScore = rank; }
    }
    const start = Math.max(best.section.start, center - 2), end = Math.min(best.section.end, start + 8);
    return { score: best.score, found: best.found, section: best.section.title, lineStart: start + 1, lineEnd: end + 1, text: parsed.lines.slice(start, end + 1).join('\n') };
  }

  function search(graph, query, options) {
    const opts = options || {}, limit = bounded(opts.limit, 12, 0, 50), category = opts.category || 'all', kind = opts.kind || 'all';
    const queryTokens = tokens(query), phrase = normalize(query);
    if (!queryTokens.length || !limit || !['all', 'entity', 'document'].includes(kind)) return [];
    const results = [], docs = new Map(documents(graph));
    if (kind !== 'document') {
      for (const node of catalog(graph).nodes) {
        if (category !== 'all' && categoryOf(node.document) !== category) continue;
        const label = String(node.label || node.id);
        const titleRank = relevance(label, queryTokens, phrase);
        const fields = [node.id, label, node.type, node.domain, ...(Array.isArray(node.aliases) ? node.aliases : []), ...(Array.isArray(node.issues) ? node.issues : [])].join(' ');
        const rank = relevance(fields, queryTokens, phrase);
        if (!rank.score) continue;
        const document = docs.get(node.document), passage = document ? bestPassage(document.text, queryTokens, phrase) : null;
        results.push({ id: node.id, kind: 'entity', label, document: node.document || null, nodeId: node.id,
          score: Math.round((rank.score + titleRank.score * 0.9) * 100) / 100,
          snippet: passage ? passage.text : 'Fonte não incluída no catálogo local.',
          lineStart: passage ? passage.lineStart : 0, lineEnd: passage ? passage.lineEnd : 0, section: passage ? passage.section : '' });
      }
    }
    if (kind !== 'entity') {
      for (const [ref, document] of docs) {
        if (category !== 'all' && categoryOf(ref) !== category) continue;
        const passage = bestPassage(document.text, queryTokens, phrase);
        if (!passage || passage.score <= 0) continue;
        const heading = document.text.match(/^\s{0,3}#\s+(.+)$/m);
        const label = heading ? heading[1].trim() : ref.split('/').pop().replace(/\.md$/i, '').replace(/-/g, ' ');
        const titleRank = relevance(label, queryTokens, phrase);
        results.push({ id: 'document:' + ref, kind: 'document', label, document: ref,
          score: Math.round((passage.score + titleRank.score * 0.7) * 100) / 100,
          snippet: passage.text, lineStart: passage.lineStart, lineEnd: passage.lineEnd, section: passage.section });
      }
    }
    return results.sort((a, b) => b.score - a.score || a.kind.localeCompare(b.kind) || a.id.localeCompare(b.id)).slice(0, limit);
  }

  function adjacency(data, directed, view) {
    const map = new Map(data.nodes.map(node => [node.id, []]));
    for (const edge of data.edges) {
      if (view && edge.view !== view) continue;
      if (view && (!data.nodes.find(node => node.id === edge.source).views?.[view] || !data.nodes.find(node => node.id === edge.target).views?.[view])) continue;
      map.get(edge.source).push({ id: edge.target, edge });
      if (!directed && edge.target !== edge.source) map.get(edge.target).push({ id: edge.source, edge });
    }
    return map;
  }

  function neighborhood(graph, id, hops) {
    const data = catalog(graph), depth = bounded(hops, 1, 0, 2);
    if (!data.ids.has(id)) return { nodes: [], edges: [] };
    const map = adjacency(data, false, null), visited = new Set([id]), queue = [{ id, depth: 0 }];
    for (let index = 0; index < queue.length; index++) {
      const current = queue[index];
      if (current.depth >= depth) continue;
      for (const next of map.get(current.id)) {
        if (visited.has(next.id) || visited.size >= MAX_NEIGHBORS) continue;
        visited.add(next.id); queue.push({ id: next.id, depth: current.depth + 1 });
      }
    }
    return { nodes: data.nodes.filter(node => visited.has(node.id)), edges: data.edges.filter(edge => visited.has(edge.source) && visited.has(edge.target)).slice(0, MAX_LOCAL_EDGES) };
  }

  function shortestPath(graph, source, target, options) {
    const opts = options || {}, data = catalog(graph), empty = { nodes: [], edges: [], found: false };
    if (!data.ids.has(source) || !data.ids.has(target)) return empty;
    if (opts.view && (!data.nodes.find(node => node.id === source).views?.[opts.view] || !data.nodes.find(node => node.id === target).views?.[opts.view])) return empty;
    if (source === target) return { nodes: [source], edges: [], found: true };
    const map = adjacency(data, Boolean(opts.directed), opts.view || null), prior = new Map([[source, null]]), queue = [source];
    for (let index = 0; index < queue.length; index++) {
      const current = queue[index];
      for (const next of map.get(current)) {
        if (prior.has(next.id)) continue;
        prior.set(next.id, { node: current, edge: next.edge.id }); queue.push(next.id);
        if (next.id === target) {
          const nodes = [target], edges = [];
          let cursor = target;
          while (cursor !== source) { const step = prior.get(cursor); edges.push(step.edge); nodes.push(step.node); cursor = step.node; }
          return { nodes: nodes.reverse(), edges: edges.reverse(), found: true };
        }
      }
    }
    return empty;
  }

  function retrieve(graph, query, options) {
    const opts = options || {}, limit = bounded(opts.limit, 6, 0, 20), hops = bounded(opts.hops, 1, 0, 2), queryTokens = tokens(query);
    const result = { mode: 'local-text-graph', query: String(query == null ? '' : query), seeds: [], nodes: [], edges: [], citations: [], gaps: [] };
    if (!queryTokens.length) { result.gaps.push('Informe termos específicos. Palavras comuns não identificam evidências.'); return result; }
    const docHits = search(graph, query, { limit, kind: 'document' }), entityHits = search(graph, query, { limit: 8, kind: 'entity' });
    const data = catalog(graph), docs = new Map(documents(graph));
    const seedIds = new Set(entityHits.map(hit => hit.nodeId));
    if (!seedIds.size) {
      const refs = new Set(docHits.map(hit => hit.document));
      for (const node of data.nodes) if (refs.has(node.document) && seedIds.size < 8) seedIds.add(node.id);
    }
    result.seeds = [...seedIds].slice(0, 8);
    const visited = new Set(), edgeIds = new Set();
    for (const id of result.seeds) {
      const neighbors = neighborhood(graph, id, hops);
      for (const node of neighbors.nodes) if (visited.size < MAX_NEIGHBORS || visited.has(node.id)) visited.add(node.id);
      for (const edge of neighbors.edges) if (visited.has(edge.source) && visited.has(edge.target) && edgeIds.size < MAX_LOCAL_EDGES) edgeIds.add(edge.id);
    }
    result.nodes = data.nodes.filter(node => visited.has(node.id)).map(node => node.id);
    result.edges = data.edges.filter(edge => edgeIds.has(edge.id)).map(edge => edge.id);
    result.citations = docHits.map(hit => ({ document: hit.document, sha256: docs.get(hit.document).sha256 || null,
      section: hit.section, lineStart: hit.lineStart, lineEnd: hit.lineEnd, text: hit.snippet }));
    if (!result.citations.length) result.gaps.push('Nenhum trecho documental corresponde aos termos. Não há evidência textual para responder à consulta.');
    else {
      const cited = normalize(result.citations.map(citation => citation.text).join(' '));
      const covered = relevance(cited, queryTokens, '').found;
      if (covered.length < queryTokens.length) result.gaps.push('Os trechos recuperados cobrem apenas parte dos termos. Revise as fontes antes de concluir.');
    }
    if (result.citations.length && !result.seeds.length) result.gaps.push('Há fontes textuais, mas nenhuma entidade do catálogo está vinculada a esses documentos.');
    if (result.seeds.length && !result.edges.length) result.gaps.push('Nenhuma relação registrada foi recuperada para as entidades encontradas.');
    if (visited.size >= MAX_NEIGHBORS || edgeIds.size >= MAX_LOCAL_EDGES) result.gaps.push('A expansão atingiu o limite local de 80 entidades ou 240 relações. Refine a consulta.');
    result.gaps.push('Busca textual e relações curadas locais; nenhuma busca vetorial, geração de resposta ou execução de agentes foi realizada.');
    return result;
  }

  function validatePlan(plan) {
    const errors = [];
    if (!plan || typeof plan !== 'object' || Array.isArray(plan)) return { ok: false, errors: ['O plano deve ser um objeto.'] };
    if (plan.version !== 1) errors.push('A versão do plano deve ser 1.');
    if (!Array.isArray(plan.steps) || !plan.steps.length || plan.steps.length > 100) errors.push('O plano deve conter entre 1 e 100 etapas.');
    const steps = Array.isArray(plan.steps) ? plan.steps.slice(0, 100) : [], byId = new Map();
    for (let index = 0; index < steps.length; index++) {
      const step = steps[index], prefix = 'Etapa ' + (index + 1) + ': ';
      if (!step || typeof step !== 'object' || Array.isArray(step)) { errors.push(prefix + 'formato inválido.'); continue; }
      if (typeof step.id !== 'string' || !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(step.id)) errors.push(prefix + 'ID inválido.');
      else if (byId.has(step.id)) errors.push(prefix + 'ID duplicado: ' + step.id + '.');
      else byId.set(step.id, step);
      if (typeof step.name !== 'string' || !step.name.trim() || step.name.length > 160) errors.push(prefix + 'nome deve conter entre 1 e 160 caracteres.');
      if (!ROLES.has(step.role)) errors.push(prefix + 'papel não permitido.');
      if (!Array.isArray(step.dependsOn) || step.dependsOn.some(id => typeof id !== 'string')) errors.push(prefix + 'dependsOn deve ser uma lista de IDs.');
      else if (new Set(step.dependsOn).size !== step.dependsOn.length) errors.push(prefix + 'dependência duplicada.');
      if (!Array.isArray(step.tools) || step.tools.some(tool => !TOOL_NAMES.has(tool))) errors.push(prefix + 'ferramenta não permitida; use search, read_graph ou read_sources.');
      else if (new Set(step.tools).size !== step.tools.length) errors.push(prefix + 'ferramenta duplicada.');
      if (typeof step.budgetSeconds !== 'number' || !Number.isFinite(step.budgetSeconds) || step.budgetSeconds <= 0 || step.budgetSeconds > 86400) errors.push(prefix + 'budgetSeconds deve ser positivo e não exceder 86400 segundos.');
    }
    for (const step of byId.values()) for (const dependency of Array.isArray(step.dependsOn) ? step.dependsOn : []) {
      if (!byId.has(dependency)) errors.push('Etapa ' + step.id + ': dependência desconhecida: ' + String(dependency) + '.');
      if (dependency === step.id) errors.push('Etapa ' + step.id + ': dependência de si mesma.');
    }
    const visited = new Set(), visiting = new Set();
    function hasCycle(id) {
      if (visiting.has(id)) return true;
      if (visited.has(id) || !byId.has(id)) return false;
      visiting.add(id);
      const dependencies = byId.get(id).dependsOn;
      for (const dependency of Array.isArray(dependencies) ? dependencies : []) if (hasCycle(dependency)) return true;
      visiting.delete(id); visited.add(id); return false;
    }
    if ([...byId.keys()].some(hasCycle)) errors.push('O plano contém um ciclo de dependências.');
    return { ok: errors.length === 0, errors };
  }

  function stripFrontmatter(text) {
    // Leading YAML block only (ADR-014); a later '---' is a Markdown rule and stays.
    return String(text).replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n/, '');
  }

  return Object.freeze({ normalize, search, neighborhood, shortestPath, retrieve, validatePlan, stripFrontmatter });
});
