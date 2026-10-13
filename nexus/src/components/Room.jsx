import React from 'react';
import { Avatar, StatusBadge, Progress, Furniture, ActivityIndicator } from './Shared.jsx';
import SpeechBubble from './SpeechBubble.jsx';
export default function Room({ room, agent, selected, onSelect, paused, bubble }) {
  const active = ['working', 'thinking'].includes(agent.status);
  return <section className={'room room-' + room.id + ' status-' + agent.status + (selected ? ' room-selected' : '')} aria-label={'Sala de ' + room.title}>
    <div className="room-heading">
      <span className="room-number">{room.number}</span>
      <div><h3 className="room-title">{room.title}</h3><p className="room-description">{room.description}</p></div>
      <room.Icon size={17} aria-hidden="true" />
    </div>
    <Furniture room={room.id} />
    <div className="agent-station">
      <button type="button" className={'agent-button' + (selected ? ' agent-selected' : '')}
        aria-label={'Ver detalhes de ' + agent.name} aria-pressed={selected} onClick={event => onSelect(agent.id, event.currentTarget)}>
        <Avatar agent={agent} />
        <span className="agent-label"><strong>{agent.name}</strong><span className="agent-role">{agent.role}</span></span>
        {active && <span className="typing-indicator" aria-label="Agente ativo"><i /><i /><i /></span>}
        <ActivityIndicator agent={agent} paused={paused} />
      </button>
      <StatusBadge status={agent.status} paused={paused} />
      {bubble && <SpeechBubble key={bubble.key} text={bubble.text} type={bubble.type} />}
    </div>
    <Progress agent={agent} />
    <p className="room-task" title={agent.task}>{agent.task}</p>
  </section>;
}
