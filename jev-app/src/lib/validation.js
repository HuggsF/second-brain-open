// Validacao do formulario de registro de execucao. Espelha core/evidence.py (validate_execution).

export const SUMMARY_MAX = 500;
export const EVIDENCE_REF_MAX = 300;

const REF_SHAPE = /^(https?:\/\/\S+|[\p{L}\p{N}_./-]+:\d+(?:-\d+)?|[A-Z][A-Z0-9]*-\d+)$/u;
const COMMIT_SHA = /^[0-9a-f]{7,40}$/;
const RUN_ID = /^[A-Za-z0-9._:/#-]{1,80}$/;

// Comprimento em pontos de codigo (como o len() do Python), nao em unidades UTF-16.
const size = (s) => [...s].length;

// Mesma limpeza do backend: tabs e quebras viram espaco, demais controles saem.
function clean(value) {
  if (typeof value !== 'string') return '';
  return value.replace(/[\r\n\t]/g, ' ').replace(/\p{Cc}/gu, '').trim();
}

export function validateExecution(form) {
  const f = form || {};
  const errors = {};
  const summary = clean(f.summary);
  const evidenceRef = clean(f.evidenceRef);
  const commitSha = clean(f.commitSha);
  const runId = clean(f.runId);

  if (size(summary) < 1 || size(summary) > SUMMARY_MAX) {
    errors.summary = `O resumo deve ter de 1 a ${SUMMARY_MAX} caracteres.`;
  }
  if (size(evidenceRef) < 1) {
    errors.evidenceRef = 'A referência de evidência é obrigatória.';
  } else if (size(evidenceRef) > EVIDENCE_REF_MAX || !REF_SHAPE.test(evidenceRef)) {
    errors.evidenceRef = `Use caminho:linha, uma URL http(s) ou um id de ticket, com até ${EVIDENCE_REF_MAX} caracteres.`;
  }
  if (commitSha && !COMMIT_SHA.test(commitSha)) {
    errors.commitSha = 'O commit deve ter de 7 a 40 caracteres hexadecimais minúsculos.';
  }
  if (runId && !RUN_ID.test(runId)) {
    errors.runId = 'O id da execução aceita de 1 a 80 caracteres entre A-Z a-z 0-9 . _ : / # -';
  }
  return { ok: Object.keys(errors).length === 0, errors };
}
