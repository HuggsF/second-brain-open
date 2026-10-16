/**
 * EventBus — Ponte de comunicação entre Phaser (canvas) e React (HUD).
 *
 * Eventos do WebSocket backend → EventBus → Phaser Scene (move agentes, muda estado)
 * Interações do Phaser (clique em agente) → EventBus → React (mostra detalhes)
 */
import Phaser from 'phaser';

const EventBus = new Phaser.Events.EventEmitter();
export default EventBus;
