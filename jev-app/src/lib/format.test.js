import { describe, it, expect } from 'vitest';
import { relativeTime, parseTs, resultMeta, statusMeta, envLabel, sortByTsDesc } from './format.js';

const NOW = Date.parse('2026-10-14T12:00:00Z');

describe('relativeTime', () => {
  it('segundos, minutos, horas, dias', () => {
    expect(relativeTime('2026-10-14T11:59:40Z', NOW)).toBe('agora há pouco');
    expect(relativeTime('2026-10-14T11:30:00Z', NOW)).toBe('há 30 min');
    expect(relativeTime('2026-10-14T09:00:00Z', NOW)).toBe('há 3 h');
    expect(relativeTime('2026-10-11T12:00:00Z', NOW)).toBe('há 3 d');
  });
  it('meses e anos', () => {
    expect(relativeTime('2026-07-14T12:00:00Z', NOW)).toBe('há 3 meses');
    expect(relativeTime('2024-10-14T12:00:00Z', NOW)).toBe('há 2 anos');
  });
  it('nunca imprime 0 anos e vira ano só em 365 dias', () => {
    const ago = (days) => new Date(NOW - days * 86400000).toISOString();
    expect(relativeTime(ago(359), NOW)).toBe('há 11 meses');
    expect(relativeTime(ago(360), NOW)).toBe('há 1 ano');
    expect(relativeTime(ago(364), NOW)).toBe('há 1 ano');
    expect(relativeTime(ago(365), NOW)).toBe('há 1 ano');
    expect(relativeTime(ago(400), NOW)).toBe('há 1 ano');
    expect(relativeTime(ago(730), NOW)).toBe('há 2 anos');
  });
  it('futuro e inválido', () => {
    expect(relativeTime('2026-10-14T13:00:00Z', NOW)).toBe('no futuro');
    expect(relativeTime('lixo', NOW)).toBe('data inválida');
    expect(relativeTime(undefined, NOW)).toBe('data inválida');
  });
  it('aceita offset -03:00 como o backend', () => {
    expect(relativeTime('2026-10-14T08:59:50-03:00', NOW)).toBe('agora há pouco');
  });
});

describe('metas', () => {
  it('resultMeta cobre os 4 resultados e cai em desconhecido', () => {
    expect(resultMeta('pass').label).toBe('Aprovada');
    expect(resultMeta('fail').label).toBe('Falhou');
    expect(resultMeta('error').label).toBe('Erro');
    expect(resultMeta('skipped').label).toBe('Ignorada');
    expect(resultMeta('x').label).toBe('Desconhecido');
    expect(resultMeta('__proto__').label).toBe('Desconhecido');
  });
  it('statusMeta: active, draft, retired; nunca deprecated', () => {
    expect(statusMeta('active').label).toBe('Ativo');
    expect(statusMeta('draft').label).toBe('Rascunho');
    expect(statusMeta('retired').label).toBe('Aposentado');
    expect(statusMeta('deprecated').label).toBe('Desconhecido');
  });
  it('envLabel', () => {
    expect(envLabel('production')).toBe('Produção');
    expect(envLabel('hml')).toBe('Homologação');
    expect(envLabel('local')).toBe('Local');
    expect(envLabel('zzz')).toBe('zzz');
  });
});

describe('ordenação', () => {
  it('parseTs devolve NaN para inválidos', () => {
    expect(Number.isNaN(parseTs('x'))).toBe(true);
  });
  it('sortByTsDesc: mais novo primeiro, inválidos por último, sem mutar', () => {
    const rows = [{ ts: '2026-01-01T00:00:00Z' }, { ts: 'x' }, { ts: '2026-03-01T00:00:00Z' }];
    const out = sortByTsDesc(rows);
    expect(out.map((r) => r.ts)).toEqual(['2026-03-01T00:00:00Z', '2026-01-01T00:00:00Z', 'x']);
    expect(rows[0].ts).toBe('2026-01-01T00:00:00Z');
  });
});
