import React, { useEffect, useId, useRef, useState } from 'react';
import { Sparkles, X, ArrowUpRight, Play } from 'lucide-react';
import { PRESETS } from './Shared.jsx';
export default function TaskDialog({ onClose, onSubmit, currentTask }) {
  const ref = useRef(null);
  const inputRef = useRef(null);
  const id = useId();
  const [task, setTask] = useState(currentTask);
  useEffect(() => {
    const dialog = ref.current;
    const returnFocus = document.activeElement;
    dialog.showModal();
    inputRef.current?.focus();
    return () => {
      if (dialog.open) dialog.close();
      if (returnFocus?.isConnected && typeof returnFocus.focus === 'function') {
        returnFocus.focus({ preventScroll: true });
      }
    };
  }, []);
  return <dialog ref={ref} className="task-dialog" aria-labelledby={id}
    onCancel={event => { event.preventDefault(); onClose(); }}>
    <div className="dialog-heading"><span className="brand-mark"><Sparkles size={20} /></span>
      <button type="button" className="btn btn-icon" aria-label="Fechar nova tarefa" onClick={onClose}><X size={19} /></button></div>
    <span className="section-label">UMA NOVA MISSÃO</span><h2 id={id}>O que vamos criar?</h2>
    <p>A orquestradora distribui a missão entre pesquisa, desenvolvimento, redação e revisão.</p>
    <form onSubmit={event => {
      event.preventDefault();
      const next = task.trim().replace(/\s+/g, ' ');
      if (next) onSubmit(next);
    }}>
      <label className="form-label" htmlFor={id + '-task'}>Descreva a tarefa</label>
      <textarea className="task-input" id={id + '-task'} ref={inputRef} value={task}
        onChange={event => setTask(event.target.value)} required minLength={3} maxLength={240} rows={3} />
      <div className="task-presets">{PRESETS.map(preset => <button type="button" className="preset" key={preset}
        onClick={() => setTask(preset)}>{preset}<ArrowUpRight size={13} /></button>)}</div>
      <p className="notice">Uma nova missão reinicia o progresso e o contexto da simulação.</p>
      <div className="dialog-actions"><button type="button" className="btn btn-secondary" onClick={onClose}>Cancelar</button>
        <button type="submit" className="btn btn-primary"><Play size={16} /> Enviar tarefa</button></div>
    </form>
  </dialog>;
}
