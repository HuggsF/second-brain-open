/**
 * OfficeScene — Cena Phaser do escritório cyberpunk dos agentes.
 *
 * Renderiza o escritório isométrico com 5 agentes, mesas, monitores
 * e efeitos visuais cyberpunk (neon glow, grid, partículas).
 *
 * Recebe eventos do backend via EventBus para mover agentes e mudar estados.
 */
import Phaser from 'phaser';
import EventBus from './EventBus.js';

// ── Layout do escritório ───────────────────────────────────
const OFFICE_W = 960;
const OFFICE_H = 640;

const ROOMS = {
  research:     { x: 80,  y: 60,  w: 240, h: 200, label: '01 Pesquisa',      color: 0x00f0ff },
  development:  { x: 360, y: 60,  w: 240, h: 200, label: '02 Desenvolvimento', color: 0xa78bfa },
  writing:      { x: 640, y: 60,  w: 240, h: 200, label: '03 Redação',        color: 0xff00ff },
  meeting:      { x: 80,  y: 360, w: 400, h: 200, label: '04 Reunião & Revisão', color: 0x39ff14 },
  orchestrator: { x: 520, y: 360, w: 360, h: 200, label: '05 Orquestrador',   color: 0xa78bfa },
};

const AGENT_DEFS = [
  { id: 'manager',    name: 'Maia', role: 'Orquestrador', room: 'orchestrator', color: 0xa78bfa, emoji: '📋' },
  { id: 'researcher', name: 'Noah', role: 'Researcher',   room: 'research',     color: 0x00f0ff, emoji: '🔍' },
  { id: 'coder',      name: 'Theo', role: 'Coder',        room: 'development',  color: 0x39ff14, emoji: '💻' },
  { id: 'writer',     name: 'Lia',  role: 'Writer',       room: 'writing',      color: 0xff00ff, emoji: '✍️' },
  { id: 'reviewer',   name: 'Eva',  role: 'Reviewer',     room: 'meeting',      color: 0xfbbf24, emoji: '🔎' },
];

// Walkway Y
const WALKWAY_Y = 280;
const WALKWAY_H = 60;

export default class OfficeScene extends Phaser.Scene {
  constructor() {
    super({ key: 'OfficeScene' });
    this.agents = {};
    this.agentSprites = {};
    this.bubbles = {};
    this.particles = null;
    this.selectedAgent = null;
  }

  create() {
    this.cameras.main.setBackgroundColor(0x06050e);

    this._drawGrid();
    this._drawRooms();
    this._drawWalkway();
    this._drawFurniture();
    this._createAgents();
    this._createParticleSystem();
    this._setupEventListeners();
    this._addAmbientEffects();

    EventBus.emit('scene-ready', this);
  }

  // ── Grid cyberpunk ──────────────────────────────────
  _drawGrid() {
    const g = this.add.graphics();
    g.lineStyle(1, 0x00f0ff, 0.03);
    for (let x = 0; x < OFFICE_W; x += 40) {
      g.moveTo(x, 0);
      g.lineTo(x, OFFICE_H);
    }
    for (let y = 0; y < OFFICE_H; y += 40) {
      g.moveTo(0, y);
      g.lineTo(OFFICE_W, y);
    }
    g.strokePath();
    g.setDepth(0);
  }

  // ── Salas ───────────────────────────────────────────
  _drawRooms() {
    for (const [key, room] of Object.entries(ROOMS)) {
      const g = this.add.graphics();

      // Floor
      g.fillStyle(0x110e1f, 1);
      g.fillRoundedRect(room.x, room.y, room.w, room.h, 12);

      // Border glow
      g.lineStyle(1, room.color, 0.25);
      g.strokeRoundedRect(room.x, room.y, room.w, room.h, 12);

      // Inner glow
      g.lineStyle(1, room.color, 0.05);
      g.strokeRoundedRect(room.x + 4, room.y + 4, room.w - 8, room.h - 8, 8);

      g.setDepth(1);

      // Room label
      const label = this.add.text(room.x + 14, room.y + 10, room.label, {
        fontFamily: '"Inter", "Segoe UI", sans-serif',
        fontSize: '11px',
        fontStyle: 'bold',
        color: '#' + room.color.toString(16).padStart(6, '0'),
        alpha: 0.7,
      });
      label.setDepth(5);

      // Room light indicator
      const light = this.add.circle(room.x + room.w - 16, room.y + 14, 4, 0x334155);
      light.setDepth(5);
      room._light = light;
      room._graphics = g;
    }
  }

  // ── Walkway (corredor) ──────────────────────────────
  _drawWalkway() {
    const g = this.add.graphics();
    g.fillStyle(0x0c0919, 1);
    g.fillRect(60, WALKWAY_Y, OFFICE_W - 120, WALKWAY_H);

    // Dashed center line
    g.lineStyle(1, 0x00f0ff, 0.08);
    for (let x = 80; x < OFFICE_W - 80; x += 20) {
      g.moveTo(x, WALKWAY_Y + WALKWAY_H / 2);
      g.lineTo(x + 10, WALKWAY_Y + WALKWAY_H / 2);
    }
    g.strokePath();

    // Label
    this.add.text(OFFICE_W / 2, WALKWAY_Y + WALKWAY_H / 2, '⚡ CONTEXTO COMPARTILHADO', {
      fontFamily: '"Inter", sans-serif',
      fontSize: '9px',
      fontStyle: 'bold',
      color: '#475569',
      letterSpacing: 3,
    }).setOrigin(0.5).setDepth(5);

    g.setDepth(1);
  }

  // ── Móveis cyberpunk ────────────────────────────────
  _drawFurniture() {
    for (const [key, room] of Object.entries(ROOMS)) {
      const cx = room.x + room.w / 2;
      const cy = room.y + room.h / 2 + 10;
      const g = this.add.graphics();

      if (key !== 'meeting') {
        // Desk
        g.fillStyle(0x1a1330, 1);
        g.lineStyle(1, room.color, 0.15);
        g.fillRoundedRect(cx - 50, cy - 20, 100, 40, 6);
        g.strokeRoundedRect(cx - 50, cy - 20, 100, 40, 6);

        // Monitor
        g.fillStyle(0x0a0a1a, 1);
        g.lineStyle(1, room.color, 0.3);
        g.fillRoundedRect(cx - 20, cy - 15, 40, 22, 3);
        g.strokeRoundedRect(cx - 20, cy - 15, 40, 22, 3);

        // Monitor screen glow
        g.fillStyle(room.color, 0.08);
        g.fillRoundedRect(cx - 17, cy - 12, 34, 16, 2);

        // Monitor stand
        g.fillStyle(0x1a1330, 1);
        g.fillRect(cx - 3, cy + 7, 6, 5);

        // Keyboard
        g.fillStyle(0x151030, 1);
        g.fillRoundedRect(cx - 15, cy + 14, 30, 8, 2);

        // Chair
        g.fillStyle(0x1e1840, 1);
        g.lineStyle(1, room.color, 0.1);
        g.fillRoundedRect(cx - 16, cy + 30, 32, 22, 8);
        g.strokeRoundedRect(cx - 16, cy + 30, 32, 22, 8);
      } else {
        // Meeting table (oval)
        g.fillStyle(0x151030, 1);
        g.lineStyle(1, room.color, 0.15);
        g.fillEllipse(cx, cy, 140, 60);
        g.strokeEllipse(cx, cy, 140, 60);

        // Seats
        const seats = [
          [cx - 45, cy - 40], [cx + 45, cy - 40],
          [cx - 45, cy + 40], [cx + 45, cy + 40],
        ];
        for (const [sx, sy] of seats) {
          g.fillStyle(0x1a1540, 1);
          g.fillRoundedRect(sx - 12, sy - 8, 24, 16, 6);
        }
      }
      g.setDepth(2);
    }
  }

  // ── Agentes (sprites programáticos) ─────────────────
  _createAgents() {
    for (const def of AGENT_DEFS) {
      const room = ROOMS[def.room];
      const x = room.x + room.w / 2;
      const y = room.y + room.h - 45;

      // Agent body
      const container = this.add.container(x, y);
      container.setDepth(10);
      container.setSize(36, 48);

      // Body circle
      const body = this.add.circle(0, 8, 14, def.color, 0.15);
      body.setStrokeStyle(1.5, def.color, 0.5);
      container.add(body);

      // Head
      const head = this.add.circle(0, -8, 10, 0x1a1530, 1);
      head.setStrokeStyle(1.5, def.color, 0.6);
      container.add(head);

      // Eyes
      const eyeL = this.add.circle(-4, -9, 1.5, def.color, 0.9);
      const eyeR = this.add.circle(4, -9, 1.5, def.color, 0.9);
      container.add(eyeL);
      container.add(eyeR);

      // Name label
      const nameTag = this.add.text(0, 24, def.name, {
        fontFamily: '"Inter", sans-serif',
        fontSize: '10px',
        fontStyle: 'bold',
        color: '#' + def.color.toString(16).padStart(6, '0'),
        stroke: '#06050e',
        strokeThickness: 3,
      }).setOrigin(0.5);
      container.add(nameTag);

      // Role label
      const roleTag = this.add.text(0, 36, def.role, {
        fontFamily: '"Inter", sans-serif',
        fontSize: '8px',
        color: '#64748b',
        stroke: '#06050e',
        strokeThickness: 2,
      }).setOrigin(0.5);
      container.add(roleTag);

      // Status indicator
      const statusDot = this.add.circle(12, -16, 4, 0x334155);
      statusDot.setStrokeStyle(2, 0x06050e);
      container.add(statusDot);

      // Make interactive
      container.setInteractive(new Phaser.Geom.Circle(0, 0, 20), Phaser.Geom.Circle.Contains);
      container.on('pointerover', () => {
        this.tweens.add({ targets: container, scaleX: 1.08, scaleY: 1.08, duration: 150, ease: 'Back.easeOut' });
        body.setStrokeStyle(2, def.color, 0.8);
      });
      container.on('pointerout', () => {
        if (this.selectedAgent !== def.id) {
          this.tweens.add({ targets: container, scaleX: 1, scaleY: 1, duration: 150 });
          body.setStrokeStyle(1.5, def.color, 0.5);
        }
      });
      container.on('pointerdown', () => {
        this.selectedAgent = def.id;
        EventBus.emit('agent-clicked', def.id);
      });

      // Store references
      this.agentSprites[def.id] = {
        container,
        body,
        head,
        eyeL,
        eyeR,
        statusDot,
        nameTag,
        def,
        homeX: x,
        homeY: y,
      };
    }
  }

  // ── Partículas ──────────────────────────────────────
  _createParticleSystem() {
    // Neon dust particles
    const particles = this.add.particles(0, 0, '__WHITE', {
      x: { min: 0, max: OFFICE_W },
      y: { min: 0, max: OFFICE_H },
      scale: { min: 0.2, max: 0.8 },
      alpha: { start: 0.3, end: 0 },
      speed: { min: 5, max: 15 },
      lifespan: 6000,
      frequency: 800,
      tint: [0x00f0ff, 0xa78bfa, 0xff00ff],
      blendMode: 'ADD',
    });
    particles.setDepth(3);
  }

  // ── Ambient effects ─────────────────────────────────
  _addAmbientEffects() {
    // Subtle scanline overlay
    const scanlines = this.add.graphics();
    scanlines.fillStyle(0x000000, 0.02);
    for (let y = 0; y < OFFICE_H; y += 4) {
      scanlines.fillRect(0, y, OFFICE_W, 1);
    }
    scanlines.setDepth(100);

    // Vignette
    const vig = this.add.graphics();
    vig.fillStyle(0x000000, 1);
    vig.fillGradientStyle(0x000000, 0x000000, 0x000000, 0x000000, 0.4, 0.4, 0, 0);
    vig.fillRect(0, 0, OFFICE_W, 80);
    vig.fillGradientStyle(0x000000, 0x000000, 0x000000, 0x000000, 0, 0, 0.4, 0.4);
    vig.fillRect(0, OFFICE_H - 80, OFFICE_W, 80);
    vig.setDepth(99);

    // Ambient breathing glow on rooms
    for (const [key, room] of Object.entries(ROOMS)) {
      this.tweens.add({
        targets: room._light,
        alpha: { from: 0.5, to: 1 },
        duration: 2000 + Math.random() * 1000,
        yoyo: true,
        repeat: -1,
        ease: 'Sine.easeInOut',
      });
    }
  }

  // ── Event listeners (from backend) ──────────────────
  _setupEventListeners() {
    EventBus.on('agent-status', (agentId, status) => {
      this._updateAgentStatus(agentId, status);
    });

    EventBus.on('agent-bubble', (agentId, text) => {
      this._showBubble(agentId, text);
    });

    EventBus.on('agent-move', (agentId, targetRoom) => {
      this._moveAgent(agentId, targetRoom);
    });

    EventBus.on('celebration', () => {
      this._celebrate();
    });

    EventBus.on('transfer', (fromId, toId) => {
      this._showTransfer(fromId, toId);
    });
  }

  // ── Status update ───────────────────────────────────
  _updateAgentStatus(agentId, status) {
    const agent = this.agentSprites[agentId];
    if (!agent) return;

    const colors = {
      idle: 0x334155,
      working: 0x39ff14,
      thinking: 0xa78bfa,
      waitingApproval: 0xfbbf24,
      done: 0x00f0ff,
    };
    const color = colors[status] || 0x334155;

    // Status dot
    agent.statusDot.setFillStyle(color);

    // Room light
    const room = ROOMS[agent.def.room];
    if (room?._light) {
      room._light.setFillStyle(color);
      // Glow pulse for active states
      if (status === 'working' || status === 'thinking') {
        this.tweens.add({
          targets: room._light,
          scaleX: 1.5, scaleY: 1.5,
          duration: 300,
          yoyo: true,
          ease: 'Back.easeOut',
        });
      }
    }

    // Agent body glow
    if (status === 'working') {
      this.tweens.add({
        targets: agent.body,
        alpha: { from: 0.15, to: 0.35 },
        duration: 800,
        yoyo: true,
        repeat: -1,
        ease: 'Sine.easeInOut',
      });
    } else if (status === 'thinking') {
      // Head bob
      this.tweens.add({
        targets: agent.head,
        y: { from: -8, to: -11 },
        duration: 600,
        yoyo: true,
        repeat: 3,
        ease: 'Sine.easeInOut',
      });
    } else {
      this.tweens.killTweensOf(agent.body);
      agent.body.setAlpha(0.15);
    }
  }

  // ── Speech bubble ───────────────────────────────────
  _showBubble(agentId, text) {
    const agent = this.agentSprites[agentId];
    if (!agent) return;

    // Remove previous
    if (this.bubbles[agentId]) {
      this.bubbles[agentId].destroy();
    }

    const x = agent.container.x;
    const y = agent.container.y - 40;
    const maxW = 160;

    const bubbleText = this.add.text(x, y, text, {
      fontFamily: '"Inter", sans-serif',
      fontSize: '9px',
      color: '#e2e8f0',
      wordWrap: { width: maxW - 16 },
      padding: { x: 8, y: 6 },
      backgroundColor: '#0c0919ee',
      stroke: '#00f0ff',
      strokeThickness: 0.5,
    }).setOrigin(0.5, 1).setDepth(50);

    // Animate in
    bubbleText.setAlpha(0);
    bubbleText.setScale(0.8);
    this.tweens.add({
      targets: bubbleText,
      alpha: 1,
      scaleX: 1,
      scaleY: 1,
      duration: 200,
      ease: 'Back.easeOut',
    });

    // Fade out after delay
    this.time.delayedCall(3500, () => {
      this.tweens.add({
        targets: bubbleText,
        alpha: 0,
        y: y - 10,
        duration: 300,
        onComplete: () => bubbleText.destroy(),
      });
    });

    this.bubbles[agentId] = bubbleText;
  }

  // ── Move agent between rooms ────────────────────────
  _moveAgent(agentId, targetRoom) {
    const agent = this.agentSprites[agentId];
    const room = ROOMS[targetRoom];
    if (!agent || !room) return;

    const targetX = room.x + room.w / 2;
    const targetY = room.y + room.h - 45;

    // Walk through walkway
    const walkwayY = WALKWAY_Y + WALKWAY_H / 2;

    this.tweens.chain({
      targets: agent.container,
      tweens: [
        { y: walkwayY, duration: 400, ease: 'Sine.easeInOut' },
        { x: targetX, duration: 600, ease: 'Sine.easeInOut' },
        { y: targetY, duration: 400, ease: 'Sine.easeInOut' },
      ],
    });

    // Update home position
    agent.homeX = targetX;
    agent.homeY = targetY;
    agent.def.room = targetRoom;
  }

  // ── Transfer packet ─────────────────────────────────
  _showTransfer(fromId, toId) {
    const from = this.agentSprites[fromId];
    const to = this.agentSprites[toId];
    if (!from || !to) return;

    const packet = this.add.circle(
      from.container.x, from.container.y - 10,
      5, from.def.color, 0.8
    );
    packet.setDepth(40);

    // Trail effect
    const trail = this.add.graphics();
    trail.setDepth(39);

    this.tweens.add({
      targets: packet,
      x: to.container.x,
      y: to.container.y - 10,
      duration: 800,
      ease: 'Sine.easeInOut',
      onUpdate: () => {
        trail.clear();
        trail.lineStyle(2, from.def.color, 0.2);
        trail.moveTo(from.container.x, from.container.y - 10);
        trail.lineTo(packet.x, packet.y);
        trail.strokePath();
      },
      onComplete: () => {
        // Flash on arrival
        this.tweens.add({
          targets: packet,
          scaleX: 2, scaleY: 2, alpha: 0,
          duration: 200,
          onComplete: () => { packet.destroy(); trail.destroy(); },
        });
      },
    });
  }

  // ── Celebration ─────────────────────────────────────
  _celebrate() {
    const colors = [0x00f0ff, 0xa78bfa, 0xff00ff, 0x39ff14, 0xfbbf24];

    // Burst particles from center
    for (let i = 0; i < 50; i++) {
      const x = OFFICE_W / 2 + Phaser.Math.Between(-100, 100);
      const y = OFFICE_H / 2 + Phaser.Math.Between(-50, 50);
      const color = colors[Phaser.Math.Between(0, colors.length - 1)];
      const size = Phaser.Math.Between(2, 6);

      const p = this.add.circle(OFFICE_W / 2, OFFICE_H / 2, size, color, 0.9);
      p.setDepth(200);

      this.tweens.add({
        targets: p,
        x, y,
        alpha: 0,
        scaleX: 0.2,
        scaleY: 0.2,
        duration: 1200 + Math.random() * 800,
        ease: 'Cubic.easeOut',
        onComplete: () => p.destroy(),
      });
    }

    // Flash overlay
    const flash = this.add.rectangle(OFFICE_W / 2, OFFICE_H / 2, OFFICE_W, OFFICE_H, 0xffffff, 0.1);
    flash.setDepth(199);
    this.tweens.add({
      targets: flash,
      alpha: 0,
      duration: 500,
      onComplete: () => flash.destroy(),
    });
  }

  // ── Generate a white pixel texture ──────────────────
  preload() {
    // Create a 4x4 white texture for particles
    const canvas = document.createElement('canvas');
    canvas.width = 4;
    canvas.height = 4;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, 4, 4);
    this.textures.addCanvas('__WHITE', canvas);
  }
}
