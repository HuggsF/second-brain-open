(function(root) {
'use strict';

const MAX_EVENTS = 200;
let currentSession = null;

function render(main, U) {
  dispose();
  const { el, head } = U;
  main.append(head('TOOL CALLS', 'Timeline de chamadas de ferramentas.', 
    'Acompanhe em tempo real as execuções, negações e timeouts de tools.'));

  const container = el('div', { class: 'tool-viz-container' });
  const timeline = el('div', { class: 'tool-viz-timeline' });
  container.append(timeline);
  main.append(container);

  const emptyMsg = el('div', { class: 'tool-viz-empty' }, 'Nenhuma tool call registrada. Aguardando eventos...');
  timeline.append(emptyMsg);

  const events = [];

  function getBadge(status) {
    return { start: '🟢', end: '✅', denied: '🔴', timeout: '⏱️' }[status] || '⚪';
  }

  function formatTime(ts) {
    if (!ts) return '';
    try {
      return new Date(ts).toLocaleTimeString('pt-BR');
    } catch (_) {
      return '';
    }
  }

  function renderTimeline() {
    timeline.replaceChildren();
    const visible = events.slice(-MAX_EVENTS);
    if (!visible.length) {
      timeline.append(emptyMsg);
      return;
    }
    for (const evt of visible) {
      const entry = el('div', { class: `tool-viz-entry tool-viz-${evt.status || 'unknown'}` },
        el('span', { class: 'tool-viz-badge' }, getBadge(evt.status)),
        el('span', { class: 'tool-viz-tool' }, evt.tool_name || 'unknown'),
        el('span', { class: 'tool-viz-duration' }, evt.duration_ms != null ? `${evt.duration_ms}ms` : '...'),
        evt.reason ? el('span', { class: 'tool-viz-reason' }, evt.reason) : null,
        el('span', { class: 'tool-viz-time' }, formatTime(evt.timestamp))
      );
      timeline.append(entry);
    }
  }

  function addEvent(event) {
    if (!event || event.channel !== 'tool') return;
    events.push(event);
    if (events.length > MAX_EVENTS * 2) {
      events.splice(0, events.length - MAX_EVENTS);
    }
    renderTimeline();
  }

  let es = null;
  const EventSourceConstructor = typeof EventSource !== 'undefined' ? EventSource : root?.EventSource;
  if (typeof EventSourceConstructor === 'function') {
    try {
      es = new EventSourceConstructor('/v1/events');
      es.onmessage = (e) => {
        try {
          const data = typeof e.data === 'string' ? JSON.parse(e.data) : e.data;
          if (data && data.channel === 'tool') {
            addEvent(data);
          }
        } catch (_) {
          // ignore malformed JSON or unparseable SSE frames
        }
      };
    } catch (_) {
      // ignore connection establishment errors
    }
  }

  const session = {
    es,
    events,
    addEvent,
    dispose: () => {
      if (es && typeof es.close === 'function') {
        es.close();
      }
    }
  };
  currentSession = session;
  return session;
}

function dispose() {
  if (currentSession) {
    currentSession.dispose();
    currentSession = null;
  }
}

const api = Object.freeze({
  render,
  dispose,
  MAX_EVENTS
});

root.BrainToolVisualizer = api;
if (typeof module !== 'undefined' && module.exports) {
  module.exports = api;
}
})(typeof window !== 'undefined' ? window : globalThis);
