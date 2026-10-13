import { AGENTS, COLLAB_TYPES } from '../simulation.mjs';
const ids = new Set(AGENTS.map(a => a.id));
const types = new Set(['status_change','collaboration','message','approval_request','completion']);
const statuses = new Set(['idle','thinking','working','waitingApproval','done']);
const collabTypes = new Set([...Object.values(COLLAB_TYPES),'bubble_only']);
const text = (v, limit) => typeof v === 'string' && v.length <= limit;
const integer = v => Number.isSafeInteger(v) && v >= 0;
/** Return a detached validated envelope, or null. Unknown payload keys are rejected. */
export function decodeEvent(input) {
  try {
    const e = typeof input === 'string' ? JSON.parse(input) : input;
    if (!e || e.schemaVersion !== 1 || !text(e.id,128) || !e.id || !integer(e.missionId) || !integer(e.sequence) || !ids.has(e.agentId) || !types.has(e.type) || !Number.isFinite(e.timestamp) || e.timestamp < 0) return null;
    const p = e.payload;
    if (!p || typeof p !== 'object' || Array.isArray(p) || Object.keys(p).some(k => !['subtype','from','to','bubble','status','progress','message'].includes(k))) return null;
    if (p.status !== undefined && !statuses.has(p.status)) return null;
    if (p.progress !== undefined && (!Number.isFinite(p.progress) || p.progress < 0 || p.progress > 100)) return null;
    if (p.from !== undefined && !ids.has(p.from)) return null;
    if (p.to !== undefined && (!Array.isArray(p.to) || p.to.length > 5 || p.to.some(id => !ids.has(id)))) return null;
    if (p.subtype !== undefined && !collabTypes.has(p.subtype)) return null;
    if (p.bubble !== undefined && p.bubble !== null && !text(p.bubble,240)) return null;
    if (p.message !== undefined && !text(p.message,1000)) return null;
    if (e.type === 'status_change' && p.status === undefined) return null;
    if (e.type === 'collaboration' && p.subtype === undefined) return null;
    if (e.type === 'message' && p.message === undefined) return null;
    return structuredClone(e);
  } catch { return null; }
}
export function encodeEvent(event) {
  const value = decodeEvent(event);
  if (!value) throw new TypeError('Invalid event envelope');
  return JSON.stringify(value);
}
export function createEventGate(missionId) {
  let sequence = -1;
  const seen = new Set();
  return input => {
    const e = decodeEvent(input);
    if (!e || e.missionId !== missionId || e.sequence <= sequence || seen.has(e.id)) return false;
    sequence = e.sequence; seen.add(e.id);
    if (seen.size > 512) seen.delete(seen.values().next().value);
    return true;
  };
}
export function createCommandLedger(confirmed, missionId, revision = 0) {
  return { confirmed, optimistic: confirmed, missionId, revision, pending: [] };
}
function replay(ledger, reduce) {
  return { ...ledger, optimistic: ledger.pending.reduce((s,c) => c.resolution === 'REJECT' ? s : reduce(s,c.action),ledger.confirmed) };
}
export function queueCommand(ledger, command, reduce) {
  if (!command || !text(command.commandId,128) || !command.commandId || command.missionId !== ledger.missionId || !command.action || typeof command.action.type !== 'string' || ledger.pending.length >= 128 || ledger.pending.some(c=>c.commandId === command.commandId)) return ledger;
  return replay({ ...ledger, pending: [...ledger.pending, {...structuredClone(command),queuedRevision:ledger.revision}] },reduce);
}
/** Replies may arrive out of order; drain only the settled prefix, then replay. */
export function settleCommand(ledger, reply, reduce) {
  if (!reply || !['ACK','REJECT'].includes(reply.type) || reply.missionId !== ledger.missionId || !integer(reply.revision)) return ledger;
  const index = ledger.pending.findIndex(c=>c.commandId === reply.commandId);
  if (index < 0 || ledger.pending[index].resolution || reply.revision <= ledger.pending[index].queuedRevision) return ledger;
  let pending = ledger.pending.map((c,i)=> i === index ? {...c,resolution:reply.type} : c);
  let confirmed = ledger.confirmed;
  while (pending[0]?.resolution) {
    const head = pending[0]; pending = pending.slice(1);
    if (head.resolution === 'ACK') confirmed = reduce(confirmed,head.action);
  }
  return replay({ ...ledger, confirmed, pending, revision: Math.max(ledger.revision,reply.revision) },reduce);
}
