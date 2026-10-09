/* Projeção local dos indicadores agregados existentes; nenhuma coleta ou IO. */
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.BrainHubTopology = factory();
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  const ASPECTS = [
    ['process', 'Hub / processo PM2'], ['internal', 'HTTP interno'],
    ['external', 'HTTP público'], ['database', 'SQLite / fila']
  ];
  const RELATIONS = [
    {source: 'internal', target: 'process', relation: 'atendido pelo Hub', sourceRef: 'hub-logistico/health.js:19'},
    {source: 'external', target: 'process', relation: 'atendido pelo Hub', sourceRef: 'hub-logistico/server.js:25'},
    {source: 'process', target: 'database', relation: 'usa SQLite', sourceRef: 'hub-logistico/scripts/post-deploy-check.js:61'}
  ];
  const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const text = value => typeof value === 'string' && value.length > 0 && value.length <= 160;
  const boolean = value => typeof value === 'boolean';
  const count = value => Number.isSafeInteger(value) && value >= 0;
  const sha = value => typeof value === 'string' && /^[0-9a-f]{40}$/.test(value);
  const seconds = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;

  function sampleTime(value) {
    if (seconds(value)) return value;
    if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(value)) return null;
    const parsed = Date.parse(value);
    if (!Number.isFinite(parsed) || parsed < 0) return null;
    // Date.parse normaliza datas inexistentes (por exemplo, 30 de fevereiro).
    const normalized = value.replace(/(?:\.(\d{1,3}))?Z$/, (_, fraction) => '.' + (fraction || '').padEnd(3, '0') + 'Z');
    return new Date(parsed).toISOString() === normalized ? parsed / 1000 : null;
  }

  function assessment() {
    return {checks: [], failures: [], warnings: [], missing: false};
  }

  function check(result, label, value, expected, valid, normal, failure, warning) {
    result.checks.push({label, value: valid ? value : null, expected, ok: valid ? normal : null});
    if (!valid) result.missing = true;
    else if (!normal) {
      if (warning) result.warnings.push(warning);
      else result.failures.push(failure);
    }
  }

  function evaluateProcess(snapshots) {
    const result = assessment();
    snapshots.forEach((sample, index) => {
      const process = record(sample.process) ? sample.process : {};
      const prefix = 'Amostra ' + (index + 1) + ' · ';
      check(result, prefix + 'Estado PM2', process.status, 'online', text(process.status), process.status === 'online', 'Processo PM2 observado fora de online.');
      check(result, prefix + 'Reinícios acumulados', process.restarts, 'contador disponível', count(process.restarts), true, '');
    });
    const before = snapshots[0].process?.restarts, after = snapshots[1].process?.restarts;
    check(result, 'Reinícios entre amostras', after, count(before) ? before : null,
      count(before) && count(after), before === after, 'Reinício durante a observação.');
    return result;
  }

  function evaluateEndpoint(snapshots, id, environment, expectedSha) {
    const result = assessment(), enabled = environment === 'production';
    snapshots.forEach((sample, index) => {
      const health = record(sample[id]) ? sample[id] : {};
      const prefix = 'Amostra ' + (index + 1) + ' · ';
      check(result, prefix + 'Saúde HTTP', health.status, 'ok', text(health.status), health.status === 'ok', 'HTTP indisponível ou resposta incompatível.');
      check(result, prefix + 'Ambiente', health.environment, environment, text(health.environment), health.environment === environment, 'Ambiente do endpoint divergente.');
      check(result, prefix + 'Revisão', health.revision, sha(expectedSha) ? expectedSha : null,
        sha(expectedSha) && sha(health.revision), health.revision === expectedSha, 'Revisão do endpoint divergente da revisão esperada.');
      check(result, prefix + 'Worker ativo', health.workerEnabled, enabled, boolean(health.workerEnabled), health.workerEnabled === enabled, 'Política do worker divergente para o ambiente.');
      check(result, prefix + 'Emissão ativa', health.emissionEnabled, enabled, boolean(health.emissionEnabled), health.emissionEnabled === enabled, 'Política de emissão divergente para o ambiente.');
      if (Object.hasOwn(health, 'httpStatus')) {
        check(result, prefix + 'Código HTTP', health.httpStatus, 200,
          Number.isInteger(health.httpStatus) && health.httpStatus >= 100 && health.httpStatus <= 599,
          health.httpStatus === 200, 'Código HTTP indica resposta indisponível ou incompatível.');
      }
    });
    return result;
  }

  function evaluateDatabase(snapshots, environment) {
    const result = assessment();
    snapshots.forEach((sample, index) => {
      const db = record(sample.database) ? sample.database : {};
      const prefix = 'Amostra ' + (index + 1) + ' · ';
      check(result, prefix + 'Banco legível', db.ok, true, boolean(db.ok), db.ok === true, 'Banco indisponível para leitura.');
      check(result, prefix + 'Fila pendente', db.pending, 'contador disponível', count(db.pending), true, '');
      check(result, prefix + 'Fila processando', db.processing, environment === 'hml' ? 0 : 'contador disponível',
        count(db.processing), environment !== 'hml' || db.processing === 0, '', 'Jobs processing em homologação precisam de conferência.');
      check(result, prefix + 'Fila com falha', db.failed, 'contador disponível', count(db.failed), true, '');
      const terminal = Object.hasOwn(db, 'terminalErrorsSinceDeploy');
      const errors = terminal ? db.terminalErrorsSinceDeploy : db.errorsSinceDeploy;
      check(result, prefix + (terminal ? 'Erros terminais na janela' : 'Erros agregados na janela'), errors, 0,
        count(errors), errors === 0, 'Erros terminais ou agregados registrados na janela de observação.');
      check(result, prefix + 'Rate limits na janela', db.rateLimitsSinceDeploy, 0,
        count(db.rateLimitsSinceDeploy), db.rateLimitsSinceDeploy === 0, '', 'Rate limiting na janela; acompanhar progresso.');
      check(result, prefix + 'Jobs sem objeto logístico', db.logisticsReviewJobs, 0,
        count(db.logisticsReviewJobs), db.logisticsReviewJobs === 0, 'Objeto logístico ausente; jobs aguardam revisão.');
      check(result, prefix + 'Jobs com múltiplos volumes', db.multipleVolumeReviewJobs, 0,
        count(db.multipleVolumeReviewJobs), db.multipleVolumeReviewJobs === 0, 'Múltiplos volumes; contrato pendente.');
      check(result, prefix + 'Lojas automáticas', db.automaticShops, environment === 'hml' ? 0 : 'contador disponível',
        count(db.automaticShops), environment !== 'hml' || db.automaticShops === 0, '', 'Lojas automáticas ligadas em homologação; bloqueio do ambiente continua obrigatório.');
    });
    const before = snapshots[0].database?.failed, after = snapshots[1].database?.failed;
    check(result, 'Crescimento das falhas de fila', after, count(before) ? '≤ ' + before : null,
      count(before) && count(after), after <= before, 'Falhas de fila cresceram entre as amostras.');
    return result;
  }

  function stateOf(result) {
    if (result.failures.length) return {status: 'red', reason: [...new Set(result.failures)].join(' ')};
    if (result.warnings.length) return {status: 'yellow', reason: [...new Set(result.warnings)].join(' ')};
    if (result.missing) return {status: 'unknown', reason: 'Evidência insuficiente: indicadores ausentes ou inválidos em uma das amostras.'};
    return {status: 'green', reason: 'Indicadores presentes e normais nas duas amostras.'};
  }

  function collectionOf(latest, nowSeconds) {
    const attempt = record(latest?.last_attempt) ? latest.last_attempt : null;
    const failed = latest?.collection_failed === true || (attempt && text(attempt.error));
    const validTime = attempt && seconds(nowSeconds) && seconds(attempt.collected_at) && attempt.collected_at <= nowSeconds;
    return {
      status: failed ? 'failed' : validTime ? 'ok' : 'missing',
      lastAttemptAt: validTime ? attempt.collected_at : null
    };
  }

  function project(environment, latest, nowSeconds = Date.now() / 1000) {
    if (environment !== 'production' && environment !== 'hml') throw new RangeError('Ambiente inválido.');
    const model = {
      environment,
      nodes: ASPECTS.map(([id, label]) => ({id, label, status: 'unknown', reason: 'Sem observação válida para este ambiente.', checks: [], observedAt: null, ageSeconds: null})),
      edges: RELATIONS.map(edge => ({...edge})),
      observation: null,
      collection: collectionOf(latest, nowSeconds),
      summary: {status: 'unknown', reason: 'Sem observação válida para este ambiente.'}
    };
    if (record(latest)) {
      if (['stale', 'collection_failed'].some(key => Object.hasOwn(latest, key) && !boolean(latest[key]))) return model;
      if (latest.last_attempt != null && (!record(latest.last_attempt) || !seconds(nowSeconds) ||
          !seconds(latest.last_attempt.collected_at) || latest.last_attempt.collected_at > nowSeconds)) return model;
    }
    const observed = record(latest?.observation) ? latest.observation : null;
    const report = record(observed?.report) ? observed.report : null;
    if (!record(latest) || latest.environment !== environment || !report || report.environment !== environment ||
        !seconds(nowSeconds) || !seconds(observed.collected_at) || observed.collected_at > nowSeconds) return model;

    model.observation = {id: count(observed.id) ? observed.id : null, collectedAt: observed.collected_at,
      source: report.source === 'hub/post-deploy-check' ? report.source : null};
    const snapshots = report.snapshots;
    if (!boolean(report.ok) || !Array.isArray(snapshots) || snapshots.length !== 2 ||
        !snapshots.every(item => record(item) && boolean(item.ok))) return model;

    let observedAt = observed.collected_at;
    for (const sample of snapshots) {
      // normalize usa null quando a origem não informou at; nesse caso vale a coleta.
      if (sample.at == null) continue;
      const at = sampleTime(sample.at);
      if (at === null || at > nowSeconds) {
        model.nodes.forEach(item => {item.reason = 'Data da amostra inválida; saúde atual não comprovada.';});
        model.summary.reason = 'Data da amostra inválida; saúde atual não comprovada.';
        return model;
      }
      observedAt = Math.min(observedAt, at);
    }
    const ageSeconds = nowSeconds - observedAt;
    const stale = ageSeconds > 180 || latest.stale === true;
    const unavailable = model.collection.status === 'failed';
    const assessments = {
      process: evaluateProcess(snapshots),
      internal: evaluateEndpoint(snapshots, 'internal', environment, report.expected_sha),
      external: evaluateEndpoint(snapshots, 'external', environment, report.expected_sha),
      database: evaluateDatabase(snapshots, environment)
    };
    model.nodes.forEach(item => {
      const result = assessments[item.id], state = stateOf(result);
      item.status = state.status; item.reason = state.reason; item.checks = result.checks;
      item.observedAt = observedAt; item.ageSeconds = ageSeconds;
      if ((stale || unavailable) && item.status !== 'unknown') {
        item.status = 'yellow';
        item.reason = 'Observação anterior preservada como histórico; ' + (unavailable ? 'coleta atual indisponível' : 'dados vencidos') +
          ', sem comprovação de saúde atual. Última verificação: ' + state.reason;
      }
    });

    if (stale || unavailable) {
      model.summary = model.nodes.some(item => item.status !== 'unknown')
        ? {status: 'yellow', reason: 'Observação anterior preservada como histórico; saúde atual não comprovada.'}
        : {status: 'unknown', reason: 'Evidência anterior insuficiente; saúde atual não comprovada.'};
    } else if (model.nodes.some(item => item.status === 'red')) {
      model.summary = {status: 'red', reason: 'Verificação diretamente falhou na janela observada; consulte os aspectos.'};
    } else if (model.nodes.some(item => item.status === 'yellow')) {
      model.summary = {status: 'yellow', reason: 'Alertas identificados na janela observada; consulte os aspectos.'};
    } else if (report.ok === false || snapshots.some(item => item.ok === false || count(item.failure_count) && item.failure_count > 0 || count(item.warning_count) && item.warning_count > 0)) {
      model.summary = {status: 'yellow', reason: 'Avaliação agregada com alerta ou causa insuficiente para atribuir falha a um aspecto.'};
    } else if (model.nodes.some(item => item.status === 'unknown') || snapshots.some(item => !count(item.failure_count) || !count(item.warning_count))) {
      model.summary = {status: 'unknown', reason: 'Evidência insuficiente para comprovar todos os aspectos e a avaliação agregada.'};
    } else {
      model.summary = {status: 'green', reason: 'Indicadores presentes e normais nas duas amostras da janela observada.'};
    }
    return model;
  }

  function dependencies(model, nodeId) {
    const nodes = Array.isArray(model?.nodes) ? model.nodes : [];
    const edges = Array.isArray(model?.edges) ? model.edges : [];
    if (!nodes.some(item => item.id === nodeId)) return {dependsOn: [], dependents: []};
    const outgoing = new Set(edges.filter(edge => edge.source === nodeId).map(edge => edge.target));
    const incoming = new Set(edges.filter(edge => edge.target === nodeId).map(edge => edge.source));
    return {dependsOn: nodes.filter(item => outgoing.has(item.id)), dependents: nodes.filter(item => incoming.has(item.id))};
  }

  return {project, dependencies};
});
