import React, { useLayoutEffect, useRef, useState } from 'react';
import { MessageSquare } from 'lucide-react';
import { time } from './Shared.jsx';
export function captureLogAnchor(stream) {
  const top = stream.getBoundingClientRect().top;
  const row = Array.from(stream.children).find(child => child.getBoundingClientRect().bottom > top);
  return row ? { id: row.dataset.logId, offset: row.getBoundingClientRect().top - top } : null;
}
export function restoreLogAnchor(stream, anchor) {
  if (!anchor) return;
  const row = Array.from(stream.children).find(child => child.dataset.logId === anchor.id);
  if (row) stream.scrollTop += row.getBoundingClientRect().top - stream.getBoundingClientRect().top - anchor.offset;
}
export default function ActivityPanel({ state, selectAgent, visible = true }) {
  const streamRef = useRef(null);
  const readingAnchor = useRef(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // Auto-scroll to top for new events (logs are prepended)
  useLayoutEffect(() => {
    const stream = streamRef.current;
    if (!stream || !visible) return;
    if (autoScroll) stream.scrollTop = 0;
    else restoreLogAnchor(stream, readingAnchor.current);
    readingAnchor.current = captureLogAnchor(stream);
  }, [state.logs[0]?.id, autoScroll, visible]);

  const handleScroll = () => {
    if (!streamRef.current) return;
    setAutoScroll(streamRef.current.scrollTop < 20);
    readingAnchor.current = captureLogAnchor(streamRef.current);
  };

  return <>
    <div className="panel-header"><div><span className="section-label">AO VIVO NO WORKSPACE</span><h2>Atividade</h2></div>
      <MessageSquare size={19} aria-hidden="true" /></div>
    <p className="notice">Eventos e resumos operacionais da simulação.</p>
    <div className="activity-stream" role="log" aria-label="Eventos da equipe" aria-live="polite" aria-relevant="additions"
      ref={streamRef} onScroll={handleScroll}>
      {state.logs.map(log => {
        const agent = state.agents.find(item => item.id === log.agentId);
        return <article className={'log-entry log-' + log.kind + ' log-enter'} key={log.id} data-log-id={log.id}>
          <button className={'log-avatar avatar-' + agent.id} aria-label={'Abrir agente ' + agent.name}
            type="button" onClick={event => selectAgent(agent.id, event.currentTarget)}>{agent.name.slice(0, 1)}</button>
          <div className="log-content"><div className="log-meta"><strong>{log.agentName}</strong><time>{time(log.at)}</time></div>
            <p className="log-message">{log.message}</p>
            {(log.kind === 'handoff' || log.kind === 'approval' || log.kind === 'success') &&
              <span className="phase-indicator">{log.kind === 'handoff' ? 'Passagem de contexto' : log.kind === 'approval' ? 'Decisão local' : 'Entrega registrada'}</span>}
          </div>
        </article>;
      })}
    </div>
    <div className="panel-footer"><span className="status-dot" aria-hidden="true" /> Memória local · sem serviços conectados</div>
  </>;
}
