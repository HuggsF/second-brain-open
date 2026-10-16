/**
 * PhaserGame.jsx — Componente React que embute o Phaser canvas.
 *
 * Inicializa o Phaser.Game dentro de um useEffect,
 * conecta ao WebSocket backend via EventBus,
 * e renderiza o HUD React em overlay.
 */
import React, { useEffect, useRef, useState, useCallback } from 'react';
import Phaser from 'phaser';
import OfficeScene from './OfficeScene.js';
import EventBus from './EventBus.js';

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://127.0.0.1:8848';

export default function PhaserGame() {
  const gameContainer = useRef(null);
  const gameRef = useRef(null);
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [activity, setActivity] = useState([]);
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [missionText, setMissionText] = useState('');
  const [showTaskInput, setShowTaskInput] = useState(false);
  const [missionActive, setMissionActive] = useState(false);
  const [missionProgress, setMissionProgress] = useState(0);
  const [agentStates, setAgentStates] = useState({});

  // ── Initialize Phaser ──────────────────────────────
  useEffect(() => {
    if (gameRef.current) return;

    const config = {
      type: Phaser.AUTO,
      parent: gameContainer.current,
      width: 960,
      height: 640,
      backgroundColor: '#06050e',
      scene: [OfficeScene],
      scale: {
        mode: Phaser.Scale.FIT,
        autoCenter: Phaser.Scale.CENTER_BOTH,
      },
      render: {
        antialias: true,
        pixelArt: false,
        transparent: false,
      },
      audio: { noAudio: true },
    };

    gameRef.current = new Phaser.Game(config);

    return () => {
      if (gameRef.current) {
        gameRef.current.destroy(true);
        gameRef.current = null;
      }
    };
  }, []);

  // ── EventBus listeners ─────────────────────────────
  useEffect(() => {
    const onAgentClicked = (agentId) => {
      setSelectedAgent(agentId);
    };

    EventBus.on('agent-clicked', onAgentClicked);
    return () => EventBus.off('agent-clicked', onAgentClicked);
  }, []);

  // ── WebSocket connection ───────────────────────────
  useEffect(() => {
    let ws;
    let reconnectTimer;
    let commandSerial = 0;
    let currentMissionId = 0;

    function connect() {
      ws = new WebSocket(WS_URL);

      ws.onopen = () => {
        setConnected(true);
        addLog('system', '🟢 Conectado ao backend', 'connection');
      };

      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          handleServerEvent(data);
        } catch (err) {
          console.warn('[ws] Invalid message:', e.data);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        addLog('system', '🔴 Desconectado', 'connection');
        reconnectTimer = setTimeout(connect, 3000);
      };

      ws.onerror = () => {};
      wsRef.current = ws;
    }

    function handleServerEvent(data) {
      if (data.type === 'ACK' || data.type === 'REJECT') return;

      const agent = data.agentId || 'system';
      const payload = data.payload || {};
      const eventType = data.type;

      // Update agent state
      if (eventType === 'status_change' && payload.status) {
        setAgentStates(prev => ({ ...prev, [agent]: payload.status }));
        EventBus.emit('agent-status', agent, payload.status);

        if (payload.progress) {
          setMissionProgress(payload.progress);
        }
      }

      // Show bubble
      if (payload.bubble) {
        EventBus.emit('agent-bubble', agent, payload.bubble);
      }

      // Activity log
      if (payload.message) {
        addLog(agent, payload.message, eventType);
      } else if (payload.bubble) {
        addLog(agent, payload.bubble, eventType);
      }

      // Collaboration events
      if (eventType === 'collaboration') {
        if (payload.subtype === 'distribute' && payload.to) {
          // Show transfers from manager to agents
          for (const toId of payload.to) {
            setTimeout(() => {
              EventBus.emit('transfer', 'manager', toId);
            }, Math.random() * 500);
          }
        }
      }

      // Approval request
      if (eventType === 'approval_request') {
        addLog(agent, '🔐 Aguardando aprovação...', 'approval');
      }

      // Completion
      if (eventType === 'completion') {
        EventBus.emit('celebration');
        setMissionActive(false);
        setMissionProgress(100);
        addLog('system', '🎉 Missão concluída!', 'celebration');
      }
    }

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      if (ws) ws.close();
    };
  }, []);

  // ── Helpers ────────────────────────────────────────
  const addLog = useCallback((agent, message, type) => {
    setActivity(prev => [...prev.slice(-30), {
      id: Date.now() + Math.random(),
      agent,
      message,
      type,
      time: new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    }]);
  }, []);

  const sendMission = useCallback((task) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    if (!task.trim()) return;

    const missionId = Date.now();
    wsRef.current.send(JSON.stringify({
      schemaVersion: 1,
      commandId: `cmd:${missionId}:1`,
      missionId,
      action: { type: 'NEW_TASK', payload: task },
    }));

    setMissionActive(true);
    setMissionProgress(0);
    setActivity([]);
    setShowTaskInput(false);
    setMissionText('');
    addLog('system', `📋 Missão: "${task}"`, 'mission');
  }, [addLog]);

  const sendApproval = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({
      schemaVersion: 1,
      commandId: `cmd:${Date.now()}:approve`,
      missionId: Date.now(),
      action: { type: 'APPROVE' },
    }));
    addLog('user', '✅ Aprovação enviada', 'approval');
  }, [addLog]);

  // ── Agent info ────────────────────────────────────
  const AGENT_INFO = {
    manager:    { name: 'Maia', role: 'Orquestrador', color: '#a78bfa', tools: ['Orquestração', 'Distribuição'] },
    researcher: { name: 'Noah', role: 'Researcher',   color: '#00f0ff', tools: ['search_knowledge_base', 'get_adr'] },
    coder:      { name: 'Theo', role: 'Coder',        color: '#39ff14', tools: ['run_command', 'queries SQL'] },
    writer:     { name: 'Lia',  role: 'Writer',       color: '#ff00ff', tools: ['read_vault_file', 'publish_note'] },
    reviewer:   { name: 'Eva',  role: 'Reviewer',     color: '#fbbf24', tools: ['list_rules', 'get_rule_evidence'] },
  };

  const selectedInfo = selectedAgent ? AGENT_INFO[selectedAgent] : null;

  // ── Quick missions ────────────────────────────────
  const quickMissions = [
    'Diagnosticar pedidos failed do hub logístico',
    'Buscar playbooks de OAuth e token Bling',
    'Verificar status do Qdrant e regras de negócio',
    'Consultar ADRs sobre arquitetura do sistema',
  ];

  // ── Render ─────────────────────────────────────────
  return (
    <div className="nexus-phaser-app">
      {/* Header */}
      <header className="nexus-header">
        <div className="nexus-brand">
          <div className="nexus-logo">⚡</div>
          <div>
            <h1>Nexus</h1>
            <span>AGENT WORKSPACE</span>
          </div>
        </div>
        <div className="nexus-header-actions">
          <span className={`nexus-status ${connected ? 'online' : 'offline'}`}>
            <i></i> {connected ? 'Conectado' : 'Desconectado'}
          </span>
          <button className="nexus-btn primary" onClick={() => setShowTaskInput(true)}>
            + Nova Missão
          </button>
        </div>
      </header>

      {/* Main layout */}
      <div className="nexus-layout">
        {/* Game canvas */}
        <div className="nexus-canvas-wrapper">
          {/* Progress bar */}
          {missionActive && (
            <div className="nexus-progress">
              <div className="nexus-progress-fill" style={{ width: `${missionProgress}%` }}></div>
            </div>
          )}
          <div ref={gameContainer} className="nexus-canvas" />

          {/* Approval overlay */}
          {activity.some(a => a.type === 'approval' && !activity.some(b => b.type === 'celebration')) && (
            <div className="nexus-approval-overlay">
              <div className="nexus-approval-card">
                <span>🔐</span>
                <p>Revisão concluída. Aprovar entrega?</p>
                <button className="nexus-btn primary" onClick={sendApproval}>Aprovar ✓</button>
              </div>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <aside className="nexus-sidebar">
          {selectedInfo ? (
            <div className="nexus-agent-detail">
              <button className="nexus-detail-back" onClick={() => setSelectedAgent(null)}>← Voltar</button>
              <div className="nexus-detail-header" style={{ borderColor: selectedInfo.color + '30' }}>
                <div className="nexus-detail-avatar" style={{ background: selectedInfo.color + '15', borderColor: selectedInfo.color + '40' }}>
                  <span style={{ color: selectedInfo.color }}>{selectedInfo.name[0]}</span>
                </div>
                <div>
                  <h3>{selectedInfo.name}</h3>
                  <p style={{ color: selectedInfo.color }}>{selectedInfo.role}</p>
                </div>
              </div>
              <div className="nexus-detail-status">
                <span className={`nexus-badge ${agentStates[selectedAgent] || 'idle'}`}>
                  ● {agentStates[selectedAgent] || 'idle'}
                </span>
              </div>
              <div className="nexus-detail-section">
                <h4>Ferramentas</h4>
                {selectedInfo.tools.map(t => (
                  <span key={t} className="nexus-tool-tag">{t}</span>
                ))}
              </div>
            </div>
          ) : (
            <>
              <div className="nexus-sidebar-header">
                <h3>⚡ Atividade</h3>
                <span className="nexus-live">● LIVE</span>
              </div>
              <div className="nexus-activity-stream">
                {activity.length === 0 && (
                  <div className="nexus-empty">
                    <p>Envie uma missão para iniciar</p>
                  </div>
                )}
                {activity.map(entry => (
                  <div key={entry.id} className={`nexus-log-entry ${entry.type}`}>
                    <div className="nexus-log-avatar" style={{
                      color: AGENT_INFO[entry.agent]?.color || '#64748b',
                      borderColor: (AGENT_INFO[entry.agent]?.color || '#64748b') + '30',
                    }}>
                      {(AGENT_INFO[entry.agent]?.name || '⚡')[0]}
                    </div>
                    <div className="nexus-log-content">
                      <div className="nexus-log-meta">
                        <strong style={{ color: AGENT_INFO[entry.agent]?.color || '#94a3b8' }}>
                          {AGENT_INFO[entry.agent]?.name || 'Sistema'}
                        </strong>
                        <time>{entry.time}</time>
                      </div>
                      <p>{entry.message}</p>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </aside>
      </div>

      {/* Task input modal */}
      {showTaskInput && (
        <div className="nexus-modal-backdrop" onClick={() => setShowTaskInput(false)}>
          <div className="nexus-modal" onClick={e => e.stopPropagation()}>
            <h2>⚡ Nova Missão</h2>
            <p>Descreva a tarefa para os agentes executarem</p>
            <textarea
              value={missionText}
              onChange={e => setMissionText(e.target.value)}
              placeholder="Ex: Diagnosticar pedidos failed do hub logístico..."
              rows={3}
              autoFocus
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMission(missionText); }}}
            />
            <div className="nexus-quick-missions">
              {quickMissions.map(m => (
                <button key={m} className="nexus-quick-btn" onClick={() => sendMission(m)}>
                  {m}
                </button>
              ))}
            </div>
            <div className="nexus-modal-actions">
              <button className="nexus-btn secondary" onClick={() => setShowTaskInput(false)}>Cancelar</button>
              <button className="nexus-btn primary" onClick={() => sendMission(missionText)} disabled={!missionText.trim()}>
                Iniciar Missão →
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
