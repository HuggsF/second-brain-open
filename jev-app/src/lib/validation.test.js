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

describe('contagem por pontos de código', () => {
  it('summary de 500 emojis (1000 unidades UTF-16) é aceito; 501 não', () => {
    expect(validateExecution({ ...base, summary: '😀'.repeat(500) }).ok).toBe(true);
    expect(validateExecution({ ...base, summary: '😀'.repeat(501) }).errors.summary).toBeTruthy();
  });

  it('evidenceRef de 300 pontos de código com caracteres astrais é aceito; 301 não', () => {
    const at = (n) => 'a/' + '𝒜'.repeat(n - 4) + ':1'; // 2 + (n-4) + 2 = n pontos de código
    expect([...at(300)].length).toBe(300);
    expect(validateExecution({ ...base, evidenceRef: at(300) }).errors.evidenceRef).toBeUndefined();
    expect(validateExecution({ ...base, evidenceRef: at(301) }).errors.evidenceRef).toBeTruthy();
  });
});

describe('limpeza de caracteres de controle', () => {
  it('remove NUL, BEL, DEL e C1 do summary e do evidenceRef', () => {
    const r = validateExecution({ ...base, summary: 'ok\u0000\u0007\u007f\u0085', evidenceRef: 'vault/x.md:3\u0000' });
    expect(r.ok).toBe(true);
  });

  it('summary só com controles fica vazio e é recusado', () => {
    expect(validateExecution({ ...base, summary: '\u0000\u0007\u001b' }).errors.summary).toBeTruthy();
  });

  it('quebras e tabs viram espaço', () => {
    expect(validateExecution({ ...base, summary: 'a\tb\nc\r\nd' }).ok).toBe(true);
    expect(validateExecution({ ...base, evidenceRef: 'vault/x.md:3\tfim' }).errors.evidenceRef).toBeTruthy();
  });

  it('controles no meio são removidos antes do formato', () => {
    expect(validateExecution({ ...base, commitSha: 'abc\u00001234' }).ok).toBe(true);
    expect(validateExecution({ ...base, runId: 'run\u0007-1' }).ok).toBe(true);
  });
});
