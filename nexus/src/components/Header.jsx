import React from 'react';
import { Network, Plus, Zap, EyeOff, Eye } from 'lucide-react';
export default function Header({ workspace, reducedMotion, speed, actions }) {
 return (<header className="app-header">
        <a className="brand" href="#office" aria-label="Nexus — Escritório de agentes">
          <span className="brand-mark"><Network size={23} /></span><span><strong>Nexus<span className="brand-period">.</span></strong><small>AGENT WORKSPACE</small></span>
        </a>
        <div className="header-actions">
          <button className="btn btn-icon motion-toggle" type="button"
            onClick={actions.toggleMotion} aria-pressed={workspace.manualReducedMotion} aria-describedby="motion-preference"
            aria-label="Menos movimento"
            title="Menos movimento: preferência manual ou do sistema">
            {reducedMotion ? <EyeOff size={17} /> : <Eye size={17} />}
          </button>
          <span id="motion-preference" className="motion-preference">{reducedMotion ? workspace.systemReducedMotion ? "Menos movimento · sistema" : "Menos movimento · manual" : "Movimento padrão"}</span>
          <span className="simulation-badge"><span className="status-dot" /> Simulação local</span>
          <button className="btn btn-secondary speed-button" type="button" onClick={() => actions.setSpeed(speed === 1 ? 2 : 1)}
            aria-label={'Velocidade da simulação: ' + speed + ' vezes. Clique para alternar.'}><Zap size={15} /> {speed}×</button>
          <button type="button" className="btn btn-primary" onClick={actions.openTask}><Plus size={17} /> Nova tarefa</button>
        </div>
      </header> );
}
