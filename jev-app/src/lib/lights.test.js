import { describe, it, expect } from 'vitest';
import { LIGHTS, lightMeta, healthMeta } from './lights.js';

describe('lights', () => {
  it('lista as 4 luzes', () => {
    expect(LIGHTS).toEqual(['green', 'yellow', 'red', 'grey']);
  });

  it.each(LIGHTS)('lightMeta(%s) tem rótulo, ícone e tom', (l) => {
    const m = lightMeta(l);
    expect(m.label).toBeTruthy();
    expect(m.icon).toBeTruthy();
    expect(m.tone).toBe(l);
  });

  it('valor desconhecido devolve cinza com rótulo', () => {
    for (const v of ['purple', undefined, null]) {
      const m = lightMeta(v);
      expect(m.tone).toBe('grey');
      expect(m.label).toBeTruthy();
      expect(m.icon).toBe(lightMeta('grey').icon);
    }
  });

  it('healthMeta cobre green|yellow|red|unknown e cai em unknown', () => {
    for (const s of ['green', 'yellow', 'red']) expect(healthMeta(s).tone).toBe(s);
    expect(healthMeta('unknown').tone).toBe('grey');
    expect(healthMeta('unknown').label).toBeTruthy();
    expect(healthMeta('xyz')).toEqual(healthMeta('unknown'));
    expect(healthMeta(undefined)).toEqual(healthMeta('unknown'));
  });
});
