import { describe, it, expect } from 'vitest';
import { validateExecution } from './validation.js';

const base = { summary: 'ok', evidenceRef: 'vault/x.md:3', result: 'pass', environment: 'hml' };

describe('validateExecution', () => {
  it('aceita caminho:linha, id de ticket e URL', () => {
    for (const ref of ['vault/x.md:3', 'DEM-12', 'https://exemplo.com/run/1']) {
      const r = validateExecution({ ...base, evidenceRef: ref });
      expect(r.errors).toEqual({});
      expect(r.ok).toBe(true);
    }
  });

  it('recusa evidenceRef vazio ou só espaços', () => {
    for (const ref of ['', '   ', undefined]) {
      const r = validateExecution({ ...base, evidenceRef: ref });
      expect(r.ok).toBe(false);
      expect(r.errors.evidenceRef).toBeTruthy();
    }
  });

  it('recusa evidenceRef sem forma válida ou longo demais', () => {
    expect(validateExecution({ ...base, evidenceRef: 'texto solto' }).errors.evidenceRef).toBeTruthy();
    expect(validateExecution({ ...base, evidenceRef: 'a/' + 'b'.repeat(300) + ':1' }).errors.evidenceRef).toBeTruthy();
  });

  it('summary de 1 a 500', () => {
    expect(validateExecution({ ...base, summary: '' }).errors.summary).toBeTruthy();
    expect(validateExecution({ ...base, summary: '   ' }).errors.summary).toBeTruthy();
    expect(validateExecution({ ...base, summary: 'a'.repeat(501) }).errors.summary).toBeTruthy();
    expect(validateExecution({ ...base, summary: 'a'.repeat(500) }).ok).toBe(true);
  });

  it('commitSha vazio ou hex de 7 a 40', () => {
    expect(validateExecution({ ...base, commitSha: '' }).ok).toBe(true);
    expect(validateExecution({ ...base, commitSha: 'abc1234' }).ok).toBe(true);
    expect(validateExecution({ ...base, commitSha: 'xyz' }).errors.commitSha).toBeTruthy();
    expect(validateExecution({ ...base, commitSha: 'ABC1234' }).errors.commitSha).toBeTruthy();
  });

  it('runId vazio ou padrão permitido', () => {
    expect(validateExecution({ ...base, runId: '' }).ok).toBe(true);
    expect(validateExecution({ ...base, runId: 'run-1.2:a/b#3' }).ok).toBe(true);
    expect(validateExecution({ ...base, runId: 'com espaço' }).errors.runId).toBeTruthy();
    expect(validateExecution({ ...base, runId: 'a'.repeat(81) }).errors.runId).toBeTruthy();
  });
});
