const LIMIT = 256;
export const EMPTY_MOTION = Object.freeze({ missionId: null, bubbles: {}, transfers: [], celebrating: false, processedCount: 0 });

// Logical time only. Once the mission ledger fills, additional visual events
// are ignored until reset rather than evicting IDs and replaying old effects.
export function createMotionScheduler() {
  let missionId = null, time = 0, paused = false, celebrated = false;
  let bubbles = {}, transfers = [], celebrationEnd = null, snapshot = EMPTY_MOTION;
  const processed = new Set();
  const publish = () => {
    snapshot = { missionId, bubbles: Object.fromEntries(Object.entries(bubbles).map(([id, b]) => [id, { text: b.text, key: b.key, type: b.type }])),
      transfers: transfers.map(({ expires, ...transfer }) => transfer), celebrating: celebrationEnd !== null, processedCount: processed.size };
  };
  function reset(nextMission = null) {
    missionId = nextMission; time = 0; paused = false; celebrated = false;
    processed.clear(); bubbles = {}; transfers = []; celebrationEnd = null; publish();
    return snapshot;
  }
  function ingest(events, nextMission) {
    if (missionId !== null && nextMission < missionId) return snapshot;
    if (missionId !== nextMission) reset(nextMission);
    let changed = false;
    for (const event of events || []) {
      if (!event || typeof event.id !== 'string' || processed.has(event.id) || processed.size >= LIMIT) continue;
      processed.add(event.id); changed = true;
      if (event.bubble && event.agentId && (bubbles[event.agentId] || Object.keys(bubbles).length < 32)) {
        bubbles[event.agentId] = { text: event.bubble, key: event.id, type: event.type, expires: time + 3200 };
      }
      if (['context_share', 'handoff_review'].includes(event.type)) {
        for (const [index, to] of (event.to || []).entries()) {
          if (transfers.length >= 64) break;
          transfers.push({ id: event.id + ':' + to, from: event.from, to, delay: index * 200, type: event.type, expires: time + 2400 });
        }
      }
      if (event.type === 'celebration' && !celebrated) { celebrated = true; celebrationEnd = time + 3500; }
    }
    if (changed) publish();
    return snapshot;
  }
  function advance(delta) {
    if (paused || !Number.isFinite(delta) || delta <= 0) return snapshot;
    time += delta; let changed = false;
    for (const [id, bubble] of Object.entries(bubbles)) if (bubble.expires <= time) { delete bubbles[id]; changed = true; }
    const next = transfers.filter(t => t.expires > time);
    if (next.length !== transfers.length) { transfers = next; changed = true; }
    if (celebrationEnd !== null && celebrationEnd <= time) { celebrationEnd = null; changed = true; }
    if (changed) publish();
    return snapshot;
  }
  function nextDelay() {
    if (paused) return null;
    const ends = [...Object.values(bubbles).map(b => b.expires), ...transfers.map(t => t.expires)];
    if (celebrationEnd !== null) ends.push(celebrationEnd);
    return ends.length ? Math.max(0, Math.min(...ends) - time) : null;
  }
  return { ingest, advance, reset, setPaused(value) { paused = Boolean(value); }, snapshot: () => snapshot, nextDelay };
}

// One timeout at the next expiry, never a frame loop. sync settles elapsed time
// before freezing, and dispose makes even an already queued callback inert.
export function createMotionDriver(scheduler, onSnapshot, clock = {}) {
  const now = clock.now || (() => performance.now());
  const schedule = clock.setTimeout || globalThis.setTimeout;
  const cancel = clock.clearTimeout || globalThis.clearTimeout;
  let last = now(), timer = null, active = true, published = scheduler.snapshot();
  function settle() { const current = now(); scheduler.advance(Math.max(0, current - last)); last = current; }
  function publish() { const next = scheduler.snapshot(); if (next !== published) { published = next; onSnapshot(next); } }
  function arm() {
    if (timer !== null) cancel(timer);
    timer = null;
    const delay = scheduler.nextDelay();
    if (delay !== null) timer = schedule(() => { if (!active) return; timer = null; settle(); publish(); arm(); }, delay);
  }
  return {
    sync(events, missionId, paused) { if (!active) return; settle(); scheduler.ingest(events, missionId); scheduler.setPaused(paused); publish(); arm(); },
    dispose() { active = false; if (timer !== null) cancel(timer); timer = null; }
  };
}
