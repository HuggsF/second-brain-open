'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const core = require('../core.js');

const guide = '# Produção logística\n\n## Segurança\nA emissão de etiquetas exige aprovação.\nO banco de produção preserva o histórico.\n\n```js\n## isto não é uma seção\nconst etiqueta = "<img src=x onerror=alert(1)>";\n```\n\n## Retomada\nO rollback pausa a produção e preserva o banco.\n';
function fixture() {
  return {
    nodes: [
      { id: 'hub', label: 'Hub logístico', type: 'Sistema', domain: 'hub', document: 'systems/producao.md', views: { flow: [0, 0] } },
      { id: 'erp', label: 'ERP', type: 'Sistema', domain: 'erp', document: 'systems/producao.md', views: { flow: [100, 0] } },
      { id: 'etiqueta', label: 'Etiqueta', type: 'Entidade', domain: 'logistics', document: 'systems/producao.md', views: { flow: [200, 0] } },
      { id: 'hml', label: 'Homologação', type: 'Ambiente', domain: 'infra', document: 'systems/hml.md', views: { infra: [0, 0] } }
    ],
    edges: [
      { id: 'e1', source: 'hub', target: 'erp', relation: 'consulta', view: 'flow' },
      { id: 'e2', source: 'erp', target: 'etiqueta', relation: 'registra', view: 'flow' }
    ],
    documents: {
      'systems/producao.md': { text: guide, sha256: 'a'.repeat(64) },
      'systems/hml.md': { text: '# Homologação\n\n## Política\nA emissão está bloqueada neste ambiente.\n', sha256: 'b'.repeat(64) },
      'adrs/vector.md': { text: '# Busca vetorial\n\n## Consulta\nQdrant oferece recuperação vetorial por embeddings.\n', sha256: 'c'.repeat(64) }
    }
  };
}
function validPlan() {
  return { version: 1, steps: [
    { id: 'research', name: 'Pesquisar fontes', role: 'researcher', dependsOn: [], tools: ['search', 'read_sources'], budgetSeconds: 30 },
    { id: 'review', name: 'Revisar evidências', role: 'reviewer', dependsOn: ['research'], tools: ['read_graph'], budgetSeconds: 20 },
    { id: 'write', name: 'Documentar', role: 'writer', dependsOn: ['review'], tools: ['read_sources'], budgetSeconds: 15 }
  ] };
}

test('normalização remove acentos, preserva dados e normaliza espaços', () => {
  assert.equal(core.normalize('  EMISSÃO\n Produção  '), 'emissao producao');
  assert.equal(core.normalize(null), '');
  assert.equal(core.normalize('<script>alert(1)</script>'), '<script>alert(1)</script>');
});

test('busca global inclui documentos sem entidade e respeita categoria/kind', () => {
  const graph = fixture();
  const hits = core.search(graph, 'embeddings');
  assert.equal(hits[0].kind, 'document');
  assert.equal(hits[0].document, 'adrs/vector.md');
  assert.equal(core.search(graph, 'embeddings', { category: 'systems' }).length, 0);
  assert.equal(core.search(graph, 'embeddings', { kind: 'entity' }).length, 0);
  assert.equal(core.search(graph, 'homologacao', { kind: 'entity' })[0].nodeId, 'hml');
});

test('ranking prioriza correspondência completa em vez de documento de um termo', () => {
  const graph = fixture();
  graph.documents['systems/partial.md'] = { text: '# Política\nEmissão simples.\n', sha256: 'd'.repeat(64) };
  const hits = core.search(graph, 'emissao aprovacao', { kind: 'document' });
  assert.equal(hits[0].document, 'systems/producao.md');
  assert.ok(hits[0].score > hits.find(hit => hit.document === 'systems/partial.md').score);
});

test('citações reproduzem exatamente linhas1-based e hash da fonte', () => {
  const graph = fixture(), result = core.retrieve(graph, 'rollback banco');
  const citation = result.citations.find(item => item.document === 'systems/producao.md');
  assert.ok(citation);
  assert.equal(citation.section, 'Retomada');
  assert.equal(citation.lineStart, 12);
  assert.equal(citation.lineEnd, 14);
  assert.equal(citation.sha256, 'a'.repeat(64));
  assert.equal(citation.text, guide.split('\n').slice(citation.lineStart - 1, citation.lineEnd).join('\n'));
  assert.equal(result.mode, 'local-text-graph');
  assert.ok(result.gaps.some(gap => gap.includes('nenhuma busca vetorial')));
});

test('headers de código não criam seção; XSS permanece somente texto recuperado', () => {
  const result = core.retrieve(fixture(), 'etiqueta alert');
  const citation = result.citations[0];
  assert.equal(citation.section, 'Segurança');
  assert.ok(citation.text.includes('<img src=x onerror=alert(1)>'));
  assert.equal(globalThis.alert, undefined);
});

test('consulta desconhecida e consulta de stopwords não recuperam todas as fontes', () => {
  assert.deepEqual(core.search(fixture(), 'abracadabra desconhecidissimo'), []);
  assert.deepEqual(core.search(fixture(), 'como o e a de'), []);
  for (const query of ['abracadabra desconhecidissimo', 'como o e a de', '']) {
    const result = core.retrieve(fixture(), query);
    assert.deepEqual(result.citations, []);
    assert.deepEqual(result.seeds, []);
    assert.ok(result.gaps.length > 0);
  }
});

test('busca e recuperação não mutam catálogo nem plano', () => {
  const graph = fixture(), before = JSON.stringify(graph), plan = validPlan(), planBefore = JSON.stringify(plan);
  core.search(graph, 'producao'); core.retrieve(graph, 'producao'); core.neighborhood(graph, 'hub'); core.shortestPath(graph, 'hub', 'etiqueta');
  core.validatePlan(plan);
  assert.equal(JSON.stringify(graph), before); assert.equal(JSON.stringify(plan), planBefore);
});

test('vizinhança se limita a saltos existentes e limita expansão', () => {
  const graph = fixture();
  assert.deepEqual(core.neighborhood(graph, 'hub', 0).nodes.map(node => node.id), ['hub']);
  assert.deepEqual(core.neighborhood(graph, 'hub', 1).nodes.map(node => node.id), ['hub', 'erp']);
  assert.deepEqual(core.neighborhood(graph, 'hub', 999).nodes.map(node => node.id), ['hub', 'erp', 'etiqueta']);
  assert.deepEqual(core.neighborhood(graph, 'missing'), { nodes: [], edges: [] });
  for (let i = 0; i < 120; i++) { graph.nodes.push({ id: 'n' + i }); graph.edges.push({ id: 'x' + i, source: 'hub', target: 'n' + i }); }
  assert.equal(core.neighborhood(graph, 'hub', 1).nodes.length, 80);
});

test('caminhos respeitam direção, vista e desconexão', () => {
  const graph = fixture();
  assert.deepEqual(core.shortestPath(graph, 'hub', 'etiqueta', { directed: true, view: 'flow' }), { nodes: ['hub', 'erp', 'etiqueta'], edges: ['e1', 'e2'], found: true });
  assert.equal(core.shortestPath(graph, 'etiqueta', 'hub', { directed: true }).found, false);
  assert.equal(core.shortestPath(graph, 'etiqueta', 'hub').found, true);
  assert.equal(core.shortestPath(graph, 'hub', 'hml').found, false);
  assert.equal(core.shortestPath(graph, 'hub', 'erp', { view: 'infra' }).found, false);
  assert.deepEqual(core.shortestPath(graph, 'hub', 'hub'), { nodes: ['hub'], edges: [], found: true });
  graph.edges.push({ id: 'orphan', source: 'hub', target: 'missing', view: 'flow' });
  assert.equal(core.shortestPath(graph, 'hub', 'missing').found, false);
});

test('recuperação usa apenas relações do catálogo e sinaliza fonte sem entidade', () => {
  const graph = fixture(), result = core.retrieve(graph, 'Hub', { hops: 1 });
  assert.deepEqual(result.seeds, ['hub']);
  assert.deepEqual(result.nodes, ['hub', 'erp']);
  assert.deepEqual(result.edges, ['e1']);
  const noEntity = core.retrieve(graph, 'embeddings');
  assert.deepEqual(noEntity.nodes, []);
  assert.ok(noEntity.gaps.some(gap => gap.includes('nenhuma entidade')));
});

test('DAG válido aceita ferramentas locais; ações externas são rejeitadas', () => {
  assert.deepEqual(core.validatePlan(validPlan()), { ok: true, errors: [] });
  const plan = validPlan(); plan.steps[0].tools.push('ssh');
  assert.equal(core.validatePlan(plan).ok, false);
  assert.ok(core.validatePlan(plan).errors.some(error => error.includes('ferramenta não permitida')));
});

test('validação rejeita ciclo, autorreferência, dependência desconhecida e IDs repetidos', () => {
  const cycle = validPlan(); cycle.steps[0].dependsOn = ['write'];
  assert.ok(core.validatePlan(cycle).errors.some(error => error.includes('ciclo')));
  const self = validPlan(); self.steps[0].dependsOn = ['research'];
  assert.ok(core.validatePlan(self).errors.some(error => error.includes('si mesma')));
  const unknown = validPlan(); unknown.steps[1].dependsOn = ['missing'];
  assert.ok(core.validatePlan(unknown).errors.some(error => error.includes('desconhecida')));
  const duplicate = validPlan(); duplicate.steps[1].id = 'research';
  assert.ok(core.validatePlan(duplicate).errors.some(error => error.includes('duplicado')));
});

test('validação rejeita schema, orçamento e formatos inválidos sem lançar exceção', () => {
  for (const bad of [null, [], { version: 2, steps: [] }, { version: 1, steps: [null] }]) assert.equal(core.validatePlan(bad).ok, false);
  for (const budget of [0, -1, NaN, Infinity, '10']) { const plan = validPlan(); plan.steps[0].budgetSeconds = budget; assert.equal(core.validatePlan(plan).ok, false); }
  const plan = validPlan(); plan.steps[0].dependsOn = 'bad'; plan.steps[1].tools = null; plan.steps[2].role = 'administrator';
  assert.equal(core.validatePlan(plan).ok, false);
});

test('UMD funciona no browser sem rede/eval e strings não confiáveis permanecem dados', () => {
  const context = vm.createContext({ window: {}, fetch() { throw Error('network prohibited'); }, alert() { throw Error('code execution prohibited'); } });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../core.js'), 'utf8'), context);
  assert.equal(typeof context.window.BrainCore.retrieve, 'function');
  const graph = fixture(); graph.nodes[0].label = '<script>alert(1)</script>';
  const hits = context.window.BrainCore.search(graph, 'alert', { kind: 'entity' });
  assert.equal(hits[0].label, '<script>alert(1)</script>');
  assert.equal(core.search(null, 'test').length, 0);
});
test('stripFrontmatter removes only a leading YAML block, so snippets start at the note body', () => {
    assert.equal(core.stripFrontmatter('---\r\ntype: adr\r\n# scope: x\r\n---\r\n# Title\r\nBody'), '# Title\r\nBody');
    assert.equal(core.stripFrontmatter('# Title\n\n---\nnot: frontmatter\n---\n'), '# Title\n\n---\nnot: frontmatter\n---\n');
    assert.equal(core.stripFrontmatter('---\nunterminated: yes\n'), '---\nunterminated: yes\n');
});
