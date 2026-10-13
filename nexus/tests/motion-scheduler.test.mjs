import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';

const module = existsSync('src/motion/scheduler.js') ? await import('../src/motion/scheduler.js') : {};
const factory = () => { assert.equal(typeof module.createMotionScheduler, 'function', 'Scheduler ainda ausente'); return module.createMotionScheduler(); };
const share = { id: 'share1', agentId: 'researcher', from: 'researcher', to: ['coder', 'writer'], type: 'context_share', bubble: 'Contexto' };

test('pausa conserva o restante de bubbles e transfers', () => {
  const s = factory(); s.ingest([share], 1); s.advance(1000); s.setPaused(true); s.advance(9000);
  assert.equal(s.snapshot().transfers.length, 2); assert.equal(s.snapshot().bubbles.researcher.text, 'Contexto');
  s.setPaused(false); s.advance(1399); assert.equal(s.snapshot().transfers.length, 2);
  s.advance(1); assert.equal(s.snapshot().transfers.length, 0);
  s.advance(799); assert.ok(s.snapshot().bubbles.researcher); s.advance(1); assert.deepEqual(s.snapshot().bubbles, {});
});
test('backlog e evento terminal não são reproduzidos após expirar', () => {
  const s = factory(); const final = { ...share, id: 'final', type: 'celebration', to: [] };
  s.ingest([share, final], 1); assert.equal(s.snapshot().celebrating, true); s.advance(3500);
  s.ingest([share, final, { ...final, id: 'final2' }], 1);
  assert.equal(s.snapshot().celebrating, false); assert.equal(s.snapshot().transfers.length, 0);
});
test('nova geração cancela efeitos e permite os mesmos IDs sem callbacks antigos', () => {
  const s = factory(); s.ingest([share], 1); s.advance(1500); s.ingest([], 2);
  assert.deepEqual(s.snapshot().bubbles, {}); assert.equal(s.snapshot().transfers.length, 0);
  s.ingest([share], 1); assert.equal(s.snapshot().transfers.length, 0);
  s.ingest([share], 2); s.advance(2399); assert.equal(s.snapshot().transfers.length, 2);
  s.reset(3); assert.equal(s.nextDelay(), null);
});
test('IDs antigos permanecem inertes com memória limitada e snapshot estável', () => {
  const s = factory(); s.ingest([share], 1); const before = s.snapshot(); s.ingest([share], 1);
  assert.equal(s.snapshot(), before); s.advance(3500);
  const events = Array.from({length: 600}, (_, i) => ({...share, id: 'event' + i}));
  s.ingest(events, 1); s.advance(3500); s.ingest([share], 1);
  assert.deepEqual(s.snapshot().bubbles, {}); assert.equal(s.snapshot().processedCount <= 256, true);
});
test('driver expira por deadline, conserva pausa e limpa timeout no dispose', () => {
  assert.equal(typeof module.createMotionDriver, 'function', 'Driver ainda ausente');
  const s = factory(); let now = 0; const callbacks = new Map(); let sequence = 0; let renders = 0;
  const driver = module.createMotionDriver(s, () => renders++, {now: () => now, setTimeout(fn, delay) { callbacks.set(++sequence, {fn, delay}); return sequence; }, clearTimeout(id) { callbacks.delete(id); }});
  driver.sync([share], 1, false); assert.equal([...callbacks.values()][0].delay, 2400);
  now = 1000; driver.sync([share], 1, true); assert.equal(callbacks.size, 0);
  now = 10000; driver.sync([share], 1, false); assert.equal([...callbacks.values()][0].delay, 1400);
  const callback = [...callbacks.values()][0].fn; driver.dispose(); now = 11400; callback();
  assert.equal(callbacks.size, 0); assert.equal(s.snapshot().transfers.length, 2); assert.equal(renders, 1);
});
