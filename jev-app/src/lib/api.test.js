import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  observationUrl,
  assessmentUrl,
  fetchJson,
  getExecutions,
  getPlaybookDetail,
  renderPlaybook,
  pick,
  describeFailure,
} from './api.js';

afterEach(() => vi.unstubAllGlobals());

describe('urls', () => {
  it('observationUrl usa /v1/observability e nunca /v1/observation/', () => {
    expect(observationUrl('production')).toBe('/v1/observability?environment=production');
    expect(observationUrl('hml')).not.toContain('/v1/observation/');
  });
  it('assessmentUrl', () => {
    expect(assessmentUrl('hml')).toBe('/v1/observability/assessment?environment=hml');
  });
});

describe('fetchJson', () => {
  it('erro de rede não lança', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('down')));
    await expect(fetchJson('/x')).resolves.toEqual({ ok: false, status: 0, data: null });
  });

  it('HTTP 400 devolve ok:false e o corpo JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'ruim' }), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        }),
      ),
    );
    expect(await fetchJson('/x')).toEqual({ ok: false, status: 400, data: { detail: 'ruim' } });
  });

  it('200 devolve ok:true e dados', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"a":1}', { status: 200 })));
    expect(await fetchJson('/x')).toEqual({ ok: true, status: 200, data: { a: 1 } });
  });

  it('corpo não JSON vira data null', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('boom', { status: 502 })));
    expect(await fetchJson('/x')).toEqual({ ok: false, status: 502, data: null });
  });
});

describe('rotas por playbook', () => {
  const stub = () => {
    const fn = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fn);
    return fn;
  };

  it('getPlaybookDetail codifica o id', async () => {
    const fn = stub();
    await getPlaybookDetail('PB 1/x?');
    expect(fn.mock.calls[0][0]).toBe(`/api/playbooks/${encodeURIComponent('PB 1/x?')}`);
    expect(fn.mock.calls[0][0]).toBe('/api/playbooks/PB%201%2Fx%3F');
  });

  it('getPlaybookDetail de id simples', async () => {
    const fn = stub();
    await getPlaybookDetail('PB-001');
    expect(fn.mock.calls[0][0]).toBe('/api/playbooks/PB-001');
  });

  it('renderPlaybook faz POST com {params} e codifica o id', async () => {
    const fn = stub();
    await renderPlaybook('PB/9', { env: 'hml' });
    const [url, init] = fn.mock.calls[0];
    expect(url).toBe('/api/playbooks/PB%2F9/render');
    expect(init.method).toBe('POST');
    expect(init.headers['Content-Type']).toBe('application/json');
    expect(JSON.parse(init.body)).toEqual({ params: { env: 'hml' } });
  });

  it('renderPlaybook sem params envia objeto vazio', async () => {
    const fn = stub();
    await renderPlaybook('PB-001');
    expect(JSON.parse(fn.mock.calls[0][1].body)).toEqual({ params: {} });
  });

  it('getExecutions por playbook codifica o id; sem id usa a rota global', async () => {
    const fn = stub();
    await getExecutions('PB 1');
    await getExecutions();
    expect(fn.mock.calls[0][0]).toBe('/api/playbooks/PB%201/executions');
    expect(fn.mock.calls[1][0]).toBe('/api/playbooks/executions');
  });

  it('erro de rede em renderPlaybook não lança', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('down')));
    await expect(renderPlaybook('PB-001', {})).resolves.toEqual({ ok: false, status: 0, data: null });
  });
});

describe('pick', () => {
  it('extrai a chave do corpo em respostas ok, com [] como padrão', () => {
    expect(pick({ ok: true, status: 200, data: { rules: [1] } }, 'rules').data).toEqual([1]);
    expect(pick({ ok: true, status: 200, data: {} }, 'rules').data).toEqual([]);
    expect(pick({ ok: true, status: 200, data: null }, 'rules').data).toEqual([]);
  });
  it('deixa respostas de erro como estão', () => {
    const bad = { ok: false, status: 0, data: null };
    expect(pick(bad, 'rules')).toBe(bad);
  });
});

describe('describeFailure', () => {
  it('mensagens por status', () => {
    expect(describeFailure(0)).toMatch(/sem conexão/i);
    expect(describeFailure(401)).toMatch(/sessão/i);
    expect(describeFailure(503)).toMatch(/indisponível/i);
    expect(describeFailure(500)).toContain('HTTP 500');
  });
});
