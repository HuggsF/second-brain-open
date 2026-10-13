import React, { useEffect, useRef } from 'react';
import { ArrowLeft, ShieldCheck, Check, BrainCircuit, Clock3 } from 'lucide-react';
import { Avatar, StatusBadge, time, number } from './Shared.jsx';
export default function AgentDetail({ agent, state, onBack, onApprove, collaborators }) {
  const paused = state.mode === 'paused';
  const heading = useRef(null);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, [agent.id]);
  return <div className="agent-detail">
    <button type="button" className="detail-back" onClick={onBack}><ArrowLeft size={15} /> Voltar à atividade</button>
    <div className="detail-heading"><Avatar agent={agent} /><div><span className="section-label">{agent.role}</span>
      <h2 ref={heading} tabIndex={-1}>{agent.name}</h2><StatusBadge status={agent.status} paused={paused} /></div></div>
    <h3 className="section-label">TAREFA ATUAL</h3><p className="detail-task">{agent.task}</p>
    <div className="detail-metrics">
      <div className="metric"><strong>{agent.progress}%</strong><span>Progresso</span></div>
      <div className="metric"><strong>{number(agent.tokens)}</strong><span>Tokens simulados</span></div>
      <div className="metric"><strong>{agent.completed}</strong><span>Entregas</span></div>
    </div>
    {collaborators.length > 0 && <>
      <h3 className="section-label">🤝 COLABORANDO COM</h3>
      <div className="collab-list">
        {collaborators.map(c => <span key={c.id} className={'collab-chip avatar-' + c.id}>{c.name} · {c.role}</span>)}
      </div>
    </>}
    {agent.status === 'waitingApproval' && <div className="approval-banner">
      <ShieldCheck size={18} /><p>Revisão preliminar concluída. A equipe espera sua decisão.</p>
      <button type="button" className="btn btn-primary" onClick={onApprove}><Check size={16} /> Aprovar entrega</button>
    </div>}
    <h3 className="section-label"><BrainCircuit size={14} /> MEMÓRIA DE CURTO PRAZO</h3>
    <ul className="memory-list">{agent.memory.map((entry, index) => <li className="memory-item" key={index}>{entry}</li>)}</ul>
    <h3 className="section-label"><Clock3 size={14} /> HISTÓRICO RECENTE</h3>
    {agent.history.length ? <ol className="history-list">{agent.history.map((entry, index) =>
      <li className="history-item" key={index}><time>{time(entry.at)}</time><span>{entry.title}</span></li>)}</ol> :
      <p className="empty-state">O histórico aparece quando o agente começa a trabalhar.</p>}
    <p className="notice">Contexto, eventos e métricas fictícios desta missão.</p>
  </div>;
}
