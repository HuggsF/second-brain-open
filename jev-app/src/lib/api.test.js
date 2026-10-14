import { describe, it, expect, vi, afterEach } from 'vitest';
import { observationUrl, assessmentUrl, fetchJson } from './api.js';

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
