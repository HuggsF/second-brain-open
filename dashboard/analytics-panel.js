/* Analytics panel — reads from local analytics data via serve.py proxy. */
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

  function card(title, content) {
    return el('div', { class: 'analytics-card' },
      el('h3', { class: 'analytics-card-title' }, title),
      el('div', { class: 'analytics-card-body' }, content)
    );
  }

  function metric(label, value, unit, trend) {
    const trendClass = trend === 'up' ? 'trend-up' : trend === 'down' ? 'trend-down' : 'trend-stable';
    return el('div', { class: 'metric' },
      el('span', { class: 'metric-value' }, String(value)),
      el('span', { class: 'metric-unit' }, unit || ''),
      el('span', { class: 'metric-label' }, label),
      trend ? el('span', { class: `metric-trend ${trendClass}` }, trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→') : null
    );
  }

  function barChart(data, labelKey, valueKey, maxVal) {
    const max = maxVal || Math.max(...data.map(d => d[valueKey]), 1);
    return el('div', { class: 'bar-chart' },
      ...data.map(d => {
        const pct = Math.round((d[valueKey] / max) * 100);
        return el('div', { class: 'bar-row' },
          el('span', { class: 'bar-label' }, String(d[labelKey])),
          el('div', { class: 'bar-track' },
            el('div', { class: 'bar-fill', style: `width:${pct}%` })
          ),
          el('span', { class: 'bar-value' }, String(d[valueKey]))
        );
      })
    );
  }

  function sparkline(data, key, width, height) {
    if (!data.length) return el('span', { class: 'muted' }, 'Sem dados');
    const vals = data.map(d => d[key]);
    const min = Math.min(...vals), max = Math.max(...vals);
    const range = max - min || 1;
    const step = width / Math.max(vals.length - 1, 1);
    const points = vals.map((v, i) => `${i * step},${height - ((v - min) / range) * height}`).join(' ');
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('width', width);
    svg.setAttribute('height', height);
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    svg.setAttribute('class', 'sparkline');
    const polyline = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
    polyline.setAttribute('points', points);
    polyline.setAttribute('fill', 'none');
    polyline.setAttribute('stroke', 'var(--accent, #60a5fa)');
    polyline.setAttribute('stroke-width', '2');
    svg.appendChild(polyline);
    return svg;
  }

  async function fetchAnalytics(endpoint) {
    try {
      const resp = await fetch(`/api/analytics/${endpoint}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      return { error: e.message };
    }
  }

  async function renderAnalytics(container) {
    container.innerHTML = '';
    container.appendChild(el('h1', {}, 'Hub Analytics'));
    container.appendChild(el('p', { class: 'muted' }, 'Análise preditiva e tendências do Hub Logístico. Execute ETL primeiro (etl_run) para dados atualizados.'));

    const grid = el('div', { class: 'analytics-grid' });
    container.appendChild(grid);

    // Emission Trends
    const trends = await fetchAnalytics('emission-trends?days=30');
    if (trends.error) {
      grid.appendChild(card('Tendência de Emissões', el('p', { class: 'muted' }, `Sem dados. ${trends.error}`)));
    } else {
      const s = trends.summary;
      const t = trends.trend;
      grid.appendChild(card('Tendência de Emissões',
        el('div', { class: 'metrics-row' },
          metric('Média diária', s.avg_daily_orders, 'pedidos'),
          metric('Taxa de sucesso', `${s.avg_success_rate}%`, '', s.avg_success_rate > 90 ? 'up' : 'down'),
          metric('Total reviews', s.total_reviews, ''),
          metric('Tendência', t.direction === 'increasing' ? '↑ Crescente' : t.direction === 'decreasing' ? '↓ Decrescente' : '→ Estável', `${t.daily_change}/dia`)
        ),
        trends.daily_data ? sparkline(trends.daily_data, 'total', 280, 40) : null
      ));
    }

    // Error Analysis
    const errors = await fetchAnalytics('error-analysis?days=14');
    if (errors.error) {
      grid.appendChild(card('Padrões de Erro', el('p', { class: 'muted' }, 'Sem dados.')));
    } else {
      grid.appendChild(card('Padrões de Erro',
        el('div', {},
          el('p', {}, `Problema mais frequente: `, el('strong', {}, errors.top_issue || 'nenhum')),
          errors.by_type.length ? barChart(errors.by_type, 'type', 'total') : el('p', { class: 'muted' }, 'Sem erros no período')
        )
      ));
    }

    // Throughput
    const throughput = await fetchAnalytics('throughput?days=7');
    if (throughput.error) {
      grid.appendChild(card('Throughput por Hora', el('p', { class: 'muted' }, 'Sem dados.')));
    } else {
      grid.appendChild(card('Throughput por Hora',
        el('div', {},
          el('div', { class: 'metrics-row' },
            metric('Pico', throughput.peak?.avg_emissions || 0, `h${throughput.peak?.hour ?? '?'}`, 'up'),
            metric('Vale', throughput.low?.avg_emissions || 0, `h${throughput.low?.hour ?? '?'}`, 'down'),
            metric('Janela manutenção', throughput.recommended_maintenance_window || '-', '')
          ),
          throughput.hourly_avg ? barChart(
            throughput.hourly_avg.map(h => ({ hour: `${String(h.hour).padStart(2, '0')}h`, emissions: Math.round(h.avg_started) })),
            'hour', 'emissions'
          ) : null
        )
      ));
    }

    // Logistics Health
    const logistics = await fetchAnalytics('logistics-health?days=14');
    if (logistics.error) {
      grid.appendChild(card('Saúde Logística', el('p', { class: 'muted' }, 'Sem dados.')));
    } else {
      const ls = logistics.summary;
      grid.appendChild(card('Saúde Logística',
        el('div', { class: 'metrics-row' },
          metric('Cobertura logística', `${ls.logistics_coverage_pct}%`, '', ls.logistics_coverage_pct > 90 ? 'up' : 'down'),
          metric('Missing reviews', ls.total_missing_reviews, ''),
          metric('Multi-volume reviews', ls.total_multi_volume_reviews, '')
        )
      ));
    }
  }

  window.renderAnalytics = renderAnalytics;
})();
