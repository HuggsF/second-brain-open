import React, { useMemo, useRef } from 'react';
import { Network, Play, Pause, Check, RotateCcw, Zap, ShieldCheck, Layers, Sparkles } from 'lucide-react';
import { STATUS, number, Avatar } from './Shared.jsx';
import Header from './Header.jsx';
import OfficeFloor from './OfficeFloor.jsx';
import AgentDetail from './AgentDetail.jsx';
import ActivityPanel from './ActivityPanel.jsx';
import TaskDialog from './TaskDialog.jsx';
import { TOTAL_STEPS } from '../simulation.mjs';
import { useSimulation } from '../hooks/useSimulation.js';
import { useMotionTimeline } from '../hooks/useMotionTimeline.js';
import { useBubbleQueue } from '../hooks/useBubbleQueue.js';
import { useTransfers } from '../hooks/useTransfers.js';
import { useCelebration } from '../hooks/useCelebration.js';
export default function Workspace() {
  const { workspace, simulation: state, actions, effectiveReducedMotion: reducedMotion } = useSimulation();
  const { selectedId, taskOpen, speed, missionId } = workspace;
  const returnFocus = useRef(null);
  const selectAgent = (id, control) => { if (control) returnFocus.current = control; actions.selectAgent(id); };
  const back = () => { actions.selectAgent(null); requestAnimationFrame(() => {
    const target = returnFocus.current;
    if (target?.isConnected) target.focus({preventScroll:true});
    else document.querySelector('.agent-button[aria-pressed="false"]')?.focus({preventScroll:true});
  }); };
  const paused = state.mode === 'paused';
  const running = state.mode === 'running';
  const selected = state.agents.find(agent => agent.id === selectedId);
  const activeCount = state.agents.filter(agent => ['working', 'thinking'].includes(agent.status)).length;
  const finished = state.agents.filter(agent => agent.status === 'done').length;
  const tokens = state.agents.reduce((total, agent) => total + agent.tokens, 0);
  const progress = Math.round(state.agents.reduce((total, agent) => total + agent.progress, 0) / state.agents.length);

  const collabEvents = state.collabEvents || [];
  const timeline = useMotionTimeline(collabEvents, missionId, paused);
  const bubbles = useBubbleQueue(timeline);
  const transfers = useTransfers(timeline);
  const celebrating = useCelebration(timeline);

  // Collaborators for selected agent
  const collaborators = useMemo(() => {
    if (!selectedId) return [];
    const recent = collabEvents.filter(e =>
      (e.from === selectedId && e.to.length > 0) ||
      (e.to.includes(selectedId))
    );
    const ids = new Set();
    recent.forEach(e => {
      if (e.from === selectedId) e.to.forEach(id => ids.add(id));
      else ids.add(e.from);
    });
    ids.delete(selectedId);
    return state.agents.filter(a => ids.has(a.id));
  }, [selectedId, collabEvents, state.agents]);

  const { approve, reset, newTask } = actions;
  const start = paused ? actions.resume : actions.start;
  const phase = paused ? 'Simulação pausada' : state.needsApproval ? 'Aguardando aprovação' :
    state.mode === 'completed' ? 'Missão concluída' : running ? 'Equipe em atividade' : 'Pronto para começar';

  return <div className={'office-app' + (paused ? ' sim-paused' : '') + (reducedMotion ? ' reduced-motion' : '') + (celebrating ? ' is-celebrating' : '')}>
    <div className="app-shell">
      <Header workspace={workspace} reducedMotion={reducedMotion} speed={speed} actions={actions} />
      <main id="office">
        <div className="workspace-tabs">
          <span className="tab tab-active"><Layers size={17} /> Escritório</span>
          <span className="workspace-meta">WORKSPACE / EQUIPE AUTÔNOMA</span>
          <span className="workspace-presence"><span className="live-indicator" /> 5 agentes disponíveis</span>
        </div>
        <div className="workspace-layout">
          <section className="floor-section" aria-label="Planta do escritório de agentes">
            <div className="floor-heading"><div><span className="section-label">UMA EQUIPE. MÚLTIPLAS PERSPECTIVAS.</span>
              <h1>Escritório de agentes</h1><p>Clique em um agente para acompanhar seu trabalho.</p></div>
              <div className="floor-controls"><button type="button" className="btn btn-icon reset-button" onClick={reset}
                aria-label="Reiniciar simulação" title="Reiniciar simulação"><RotateCcw size={17} /></button>
                <button type="button" className={'btn ' + (running ? 'btn-secondary' : 'btn-primary')}
                  onClick={running ? actions.pause : start}>
                  {running ? <Pause size={16} /> : <Play size={16} />}
                  {running ? 'Pausar' : paused ? 'Retomar' : state.mode === 'completed' ? 'Simular novamente' : 'Iniciar simulação'}
                </button></div>
            </div>
            <div className="mission-strip"><span className="mission-icon"><Sparkles size={17} /></span><div><span className="section-label">MISSÃO DO TIME</span>
              <p>{state.task}</p></div><span className="mission-progress">{progress}%</span></div>
            <div className="floor-meta"><span className={'phase-indicator phase-' + state.mode} role="status">
              <span className="status-dot" /> {phase}</span><span>{paused ? 'Progresso congelado' : state.needsApproval ? 'A equipe espera sua decisão' : 'Etapa ' + state.tick + ' de ' + TOTAL_STEPS}</span></div>
            <OfficeFloor simulation={state} missionId={missionId} paused={paused} reducedMotion={reducedMotion}
              bubbles={bubbles} transfers={transfers} onSelect={selectAgent} selectedId={selectedId} celebrating={celebrating} />
            <div className="status-legend" aria-label="Legenda dos estados">
              {['idle', 'working', 'thinking', 'waitingApproval', 'done'].map(status =>
                <span key={status} className={'legend-item status-' + status}><i className="status-dot" />{STATUS[status]}</span>)}
            </div>
            {state.needsApproval && <div className="approval-banner approval-global">
              <ShieldCheck size={21} /><div><strong>Uma decisão sua desbloqueia o próximo passo.</strong><p>Eva terminou a revisão preliminar. Confira o contexto ou aprove a entrega simulada.</p></div>
              <button className="btn btn-primary" type="button" onClick={approve}><Check size={16} /> Aprovar entrega</button></div>}
            <div className="bottom-summary" aria-label="Métricas da simulação">
              <div className="summary-item"><span className="summary-icon"><Network size={18} /></span><div><strong className="summary-value">{paused ? 0 : activeCount}<small> / 5</small></strong><span className="summary-label">Agentes ativos</span></div></div>
              <div className="summary-item"><span className="summary-icon"><Check size={18} /></span><div><strong className="summary-value">{finished}<small> / 5</small></strong><span className="summary-label">Entregas concluídas</span></div></div>
              <div className="summary-item"><span className="summary-icon"><Zap size={18} /></span><div><strong className="summary-value">{number(tokens)}</strong><span className="summary-label">Tokens simulados</span></div></div>
            </div>
          </section>
          <aside className="side-panel" aria-label={selected ? 'Detalhes de ' + selected.name : 'Painel de atividade'}>
            {selected && <AgentDetail agent={selected} state={state} onBack={back} onApprove={approve} collaborators={collaborators} />}
            <div className="activity-panel" hidden={Boolean(selected)}><ActivityPanel state={state} selectAgent={selectAgent} visible={!selected} /></div>
          </aside>
        </div>
        <section className="team-strip" aria-label="Equipe de agentes"><span className="section-label">SEU TIME</span>
          {state.agents.map(agent => <button type="button" className={'team-button' + (agent.id === selectedId ? ' team-selected' : '')}
            key={agent.id} onClick={event => selectAgent(agent.id, event.currentTarget)} aria-label={'Selecionar ' + agent.name} aria-pressed={agent.id === selectedId}>
            <Avatar agent={agent} small /><span className="team-info"><strong>{agent.name}</strong><small>{agent.role}</small></span>
            <span className={'status-dot status-' + agent.status} aria-label={STATUS[agent.status]} />
          </button>)}
        </section>
      </main>
      <footer className="app-footer"><span><Network size={13} /> Trabalho coordenado, contexto visível.</span><span>Protótipo local · métricas e tarefas simuladas</span></footer>
    </div>
    {taskOpen && <TaskDialog currentTask={state.task} onClose={actions.closeTask} onSubmit={newTask} />}
  </div>;
}
