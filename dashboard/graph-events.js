/* Real-time event bus for agent activity on the knowledge graph.
   Connects to the BFF SSE endpoint or a WebSocket for live agent events.
   Emits visual pulses on graph nodes when agents access them. */
(function(root) {
'use strict';

const MAX_EVENTS = 200;
const PULSE_DURATION_MS = 2400;
const RECONNECT_DELAY_MS = 5000;
const SSE_ENDPOINT = '/v1/graph-events';
const WS_ENDPOINT = 'ws://127.0.0.1:8848';

const eventLog = [];
const listeners = new Set();
const activePulses = new Map(); // nodeId → {timer, agent, action, timestamp}
let source = null;
let ws = null;
let reconnectTimer = null;
let disposed = false;
let connected = false;
let connectionMode = 'disconnected'; // 'sse' | 'ws' | 'disconnected' | 'simulated'

function emit(event) {
  eventLog.unshift(event);
  if (eventLog.length > MAX_EVENTS) eventLog.length = MAX_EVENTS;

  // Create pulse on affected nodes
  const nodeIds = event.nodes || [];
  for (const nodeId of nodeIds) {
    if (activePulses.has(nodeId)) clearTimeout(activePulses.get(nodeId).timer);
    const timer = setTimeout(() => activePulses.delete(nodeId), PULSE_DURATION_MS);
    activePulses.set(nodeId, {
      timer,
      agent: event.agent || 'unknown',
      action: event.action || 'query',
      timestamp: event.timestamp || Date.now(),
      color: agentColor(event.agent),
    });
  }

  // Notify all listeners
  for (const fn of listeners) {
    try { fn(event); } catch (_) { /* swallow */ }
  }
}

function agentColor(agent) {
  const colors = {
    maia: '#b8f37b',    // accent green
    noah: '#9bc8fa',    // blue
    theo: '#cbb3ef',    // violet
    lia: '#f4c583',     // warm
    eva: '#9bdeb3',     // good green
    'persona-dev': '#cbb3ef',
    'persona-devops': '#9bc8fa',
    'persona-qa': '#f4c583',
    'persona-arch': '#ec4899',
    system: '#aab9ae',  // muted
  };
  return colors[agent] || '#b8f37b';
}

function agentEmoji(agent) {
  const emojis = {
    maia: '👩‍💼', noah: '🔍', theo: '💻', lia: '✍️', eva: '🔎',
    'persona-dev': '🧑‍💻', 'persona-devops': '🔧', 'persona-qa': '🧪',
    'persona-arch': '🏛️', system: '⚙️',
  };
  return emojis[agent] || '🤖';
}

// ── SSE Connection ──
function connectSSE() {
  if (disposed) return;
  try {
    source = new EventSource(SSE_ENDPOINT);
    source.onopen = () => { connected = true; connectionMode = 'sse'; notifyConnectionChange(); };
    source.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        emit(normalizeEvent(data));
      } catch (_) { /* bad JSON */ }
    };
    source.onerror = () => {
      source.close(); source = null;
      connected = false; connectionMode = 'disconnected';
      notifyConnectionChange();
      // Fall back to WebSocket
      scheduleReconnect(connectWS);
    };
  } catch (_) {
    scheduleReconnect(connectWS);
  }
}

// ── WebSocket Connection ──
function connectWS() {
  if (disposed) return;
  try {
    ws = new WebSocket(WS_ENDPOINT);
    ws.onopen = () => { connected = true; connectionMode = 'ws'; notifyConnectionChange(); };
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        // Filter for graph-related events
        if (data.type === 'graph.query' || data.type === 'tool.call' ||
            data.type === 'agent.action' || data.kind === 'task.event') {
          emit(normalizeEvent(data));
        }
      } catch (_) { /* bad JSON */ }
    };
    ws.onerror = () => {};
    ws.onclose = () => {
      ws = null; connected = false; connectionMode = 'disconnected';
      notifyConnectionChange();
      scheduleReconnect(connectSSE);
    };
  } catch (_) {
    connectionMode = 'disconnected';
    notifyConnectionChange();
  }
}

function scheduleReconnect(fn) {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(fn, RECONNECT_DELAY_MS);
}

function normalizeEvent(raw) {
  return {
    id: raw.id || raw.trace_id || crypto.randomUUID?.() || String(Date.now()),
    timestamp: raw.timestamp || raw.ts || Date.now(),
    agent: raw.agent || raw.identity?.name || raw.source || 'system',
    action: raw.action || raw.type || raw.tool || 'query',
    nodes: raw.nodes || raw.affected_nodes || extractNodes(raw),
    edges: raw.edges || [],
    detail: raw.detail || raw.message || raw.result || '',
    tool: raw.tool || raw.tool_name || null,
    duration_ms: raw.duration_ms || raw.ms || null,
    tokens: raw.tokens_in || raw.tokens || null,
  };
}

function extractNodes(raw) {
  // Try to infer which nodes were affected from various event shapes
  const nodes = [];
  if (raw.node_id) nodes.push(raw.node_id);
  if (raw.source_node) nodes.push(raw.source_node);
  if (raw.target_node) nodes.push(raw.target_node);
  if (raw.query && typeof raw.query === 'string') {
    // Could try to match query to known node IDs but that's expensive
  }
  return nodes;
}

function notifyConnectionChange() {
  for (const fn of listeners) {
    try { fn({ type: 'connection', connected, mode: connectionMode }); } catch (_) {}
  }
}

// ── Simulation mode (for when no backend is connected) ──
let simTimer = null;
const SIM_AGENTS = ['maia', 'noah', 'theo', 'lia', 'eva', 'persona-qa', 'persona-devops'];
const SIM_ACTIONS = [
  { action: 'busca semântica', tool: 'search_knowledge_base', nodes: ['qdrant', 'mcp_brain', 'noah'] },
  { action: 'code review', tool: 'github_search_code', nodes: ['mcp_github', 'theo', 'github_api'] },
  { action: 'health check', tool: 'srv_api_health_check', nodes: ['mcp_srv', 'srv', 'prod'] },
  { action: 'registra evidência', tool: 'record_test_execution', nodes: ['evidence_store', 'sqlite_evidence', 'eva'] },
  { action: 'orquestra missão', tool: 'internal', nodes: ['maia', 'orchestrator', 'policy_broker'] },
  { action: 'gera ADR', tool: 'internal', nodes: ['lia', 'tpl_adr', 'secondbrain'] },
  { action: 'valida plano', tool: 'internal', nodes: ['gate_pipeline', 'grounding_gate', 'dag_gate'] },
  { action: 'monitora hub', tool: 'observe_hub', nodes: ['mcp_hub_obs', 'hub', 'dbprod'] },
  { action: 'delega pesquisa', tool: 'internal', nodes: ['maia', 'noah', 'skill_qa'] },
  { action: 'inferência local', tool: 'classify', nodes: ['mcp_local', 'ollama', 'persona_qa'] },
  { action: 'deploy check', tool: 'srv_api_list_services', nodes: ['mcp_srv', 'deploy_auto', 'actions'] },
  { action: 'busca vault', tool: 'get_adr', nodes: ['mcp_brain', 'secondbrain', 'evidence_tree'] },
  { action: 'hub status', tool: 'observe_hub', nodes: ['hub', 'hub_monitor', 'dbprod'] },
  { action: 'policy check', tool: 'internal', nodes: ['policy_broker', 'policy_commands', 'policy_decide'] },
  { action: 'WebSocket msg', tool: 'internal', nodes: ['nexus', 'nexus_office', 'proto_ws'] },
];

function startSimulation() {
  connectionMode = 'simulated';
  notifyConnectionChange();
  function tick() {
    if (disposed) return;
    const template = SIM_ACTIONS[Math.floor(Math.random() * SIM_ACTIONS.length)];
    const agent = SIM_AGENTS[Math.floor(Math.random() * SIM_AGENTS.length)];
    emit({
      id: crypto.randomUUID?.() || String(Date.now()),
      timestamp: Date.now(),
      agent,
      action: template.action,
      nodes: template.nodes,
      edges: [],
      detail: agent + ' executou ' + template.action,
      tool: template.tool,
      duration_ms: Math.floor(Math.random() * 2000) + 100,
      tokens: Math.floor(Math.random() * 800) + 50,
    });
    simTimer = setTimeout(tick, 2000 + Math.random() * 6000);
  }
  tick();
}

function stopSimulation() {
  clearTimeout(simTimer); simTimer = null;
}

// ── Public API ──
function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }
function getLog() { return eventLog.slice(); }
function getPulses() { return new Map(activePulses); }
function isConnected() { return connected; }
function getMode() { return connectionMode; }

function connect() {
  disposed = false;
  connectSSE();
  // If after 3 seconds no connection, start simulation
  setTimeout(() => {
    if (!connected && !disposed) startSimulation();
  }, 3000);
}

function disconnect() {
  disposed = true;
  clearTimeout(reconnectTimer);
  if (source) { source.close(); source = null; }
  if (ws) { ws.close(); ws = null; }
  stopSimulation();
  connected = false;
  connectionMode = 'disconnected';
}

// Inject a manual event (for CLI or testing)
function injectEvent(event) { emit(normalizeEvent(event)); }

root.BrainGraphEvents = Object.freeze({
  subscribe, getLog, getPulses, isConnected, getMode,
  connect, disconnect, injectEvent,
  agentColor, agentEmoji,
});

})(typeof window !== 'undefined' ? window : globalThis);
