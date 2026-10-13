import React from 'react';
import { Search, Code2, PenLine, ShieldCheck, BrainCircuit } from 'lucide-react';
export const DEFAULT_TASK = 'Criar um plano de implantação do portal logístico';
export const STATUS = {
  idle: 'Ocioso', working: 'Trabalhando', thinking: 'Pensando',
  waitingApproval: 'Aguardando aprovação', done: 'Concluído'
};
export const ROOMS = [
  { id: 'research', number: '01', title: 'Pesquisa', description: 'Contexto antes de tudo', Icon: Search },
  { id: 'development', number: '02', title: 'Desenvolvimento', description: 'Ideias viram soluções', Icon: Code2 },
  { id: 'writing', number: '03', title: 'Redação', description: 'Clareza em cada entrega', Icon: PenLine },
  { id: 'meeting', number: '04', title: 'Reunião & revisão', description: 'Uma segunda perspectiva', Icon: ShieldCheck },
  { id: 'orchestrator', number: '05', title: 'Orquestrador', description: 'Conecta o trabalho do time', Icon: BrainCircuit }
];
export const PRESETS = [
  'Criar uma landing page para uma marca de cafés',
  'Pesquisar e escrever um relatório de mercado',
  'Planejar o lançamento de um portal logístico'
];

// Agent desk positions (percentage-based for responsive layout)
export const DESK_POSITIONS = {
  research: { x: 16, y: 28 },
  development: { x: 50, y: 28 },
  writing: { x: 84, y: 28 },
  meeting: { x: 25, y: 75 },
  orchestrator: { x: 75, y: 75 },
  corridor: { x: 50, y: 52 },
  entry: { x: 50, y: 95 },
};

export const time = value => new Intl.DateTimeFormat('pt-BR', {
  hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'America/Sao_Paulo'
}).format(new Date(value));
export const number = value => new Intl.NumberFormat('pt-BR').format(value);


export function Avatar({ agent, small = false }) {
  return <span className={small ? 'team-avatar avatar-' + agent.id : 'agent-avatar avatar-' + agent.id} aria-hidden="true">
    <span className="agent-hair" /><span className="agent-face" /><span className="agent-body" />
  </span>;
}

export function StatusBadge({ status, paused = false }) {
  const active = status === 'working' || status === 'thinking';
  return <span className={'status-badge status-' + status}>
    <span className="status-dot" aria-hidden="true" />
    {paused && active ? 'Pausado' : STATUS[status]}
  </span>;
}

export function Progress({ agent }) {
  return <div className="room-agent-progress">
    <div className="progress-track" role="progressbar" aria-label={'Progresso de ' + agent.name}
      aria-valuenow={agent.progress} aria-valuemin={0} aria-valuemax={100}>
      <span className="progress-fill" style={{ width: agent.progress + '%' }} />
    </div>
    <span>{agent.progress}%</span>
  </div>;
}

export function Plant({ className = '' }) {
  return <div className={'plant ' + className} aria-hidden="true">
    <span className="plant-leaf" /><span className="plant-leaf" /><span className="plant-leaf" />
    <span className="plant-pot" />
  </div>;
}

export function Furniture({ room }) {
  return <div className="room-decor" aria-hidden="true">
    <div className="window-strip"><i /><i /><i /></div>
    {room === 'meeting' ? <>
      <div className="meeting-table">
        {[0, 1, 2, 3].map(index => <i key={index} className="meeting-seat" />)}
        <span className="desk-item" />
      </div>
    </> : <>
      <div className="desk"><span className="desk-monitor"><span className="room-light" /></span>
        <span className="desk-keyboard" /><span className="desk-item" />
      </div>
      <div className="desk-chair" />
    </>}
    {room === 'research' && <div className="bookshelf">{[0, 1, 2, 3, 4].map(index => <i key={index} className="shelf-book" />)}</div>}
    <Plant />
  </div>;
}

export function ActivityIndicator({ agent, paused }) {
  if (agent.status === 'idle') return null;
  const cls = agent.status === 'working' ? 'activity-working' :
    agent.status === 'thinking' ? 'activity-thinking' :
    agent.status === 'waitingApproval' ? 'activity-waiting' :
    agent.status === 'done' ? 'activity-done' : '';
  return <div className={`activity-indicator ${cls}`} aria-hidden="true">
    {agent.status === 'working' && <><i /><i /><i /></>}
    {agent.status === 'thinking' && <span className="think-dots">…</span>}
    {agent.status === 'waitingApproval' && <span className="wait-icon">⏳</span>}
    {agent.status === 'done' && <span className="done-icon">✓</span>}
  </div>;
}

export function fromRoom(agentId) {
  const map = { manager: 'orchestrator', researcher: 'research', coder: 'development', writer: 'writing', reviewer: 'meeting' };
  return map[agentId] || 'corridor';
}
