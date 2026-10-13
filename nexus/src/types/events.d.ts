export type AgentId = 'manager' | 'researcher' | 'coder' | 'writer' | 'reviewer';
export type AgentStatus = 'idle' | 'thinking' | 'working' | 'waitingApproval' | 'done';
export type CollaborationType = 'mission_received' | 'distribute' | 'context_share' | 'parallel_work' | 'handoff_review' | 'brief_meeting' | 'approval_request' | 'approval_granted' | 'celebration' | 'agent_enter' | 'bubble_only';
export interface EventPayload {
  subtype?: CollaborationType;
  from?: AgentId;
  to?: AgentId[];
  bubble?: string | null;
  status?: AgentStatus;
  progress?: number;
  message?: string;
}
export interface SimulationEvent {
  schemaVersion: 1;
  id: string;
  missionId: number;
  sequence: number;
  agentId: AgentId;
  type: 'status_change' | 'collaboration' | 'message' | 'approval_request' | 'completion';
  payload: EventPayload;
  timestamp: number;
}
export interface AgentState {
  id: AgentId; name: string; role: string; room: string; emoji: string;
  status: AgentStatus; progress: number; task: string; memory: string[];
  history: { title: string; at: number }[]; completed: number; tokens: number;
}
export interface CollaborationEvent {
  id: string; type: CollaborationType; agentId: AgentId; from: AgentId;
  to: AgentId[]; bubble: string | null; at: number; tick?: number; consumed: boolean;
}
export interface Simulation {
  mode: 'idle' | 'running' | 'paused' | 'completed'; tick: number; task: string;
  runId: number; needsApproval: boolean; agents: AgentState[];
  collabEvents: CollaborationEvent[];
  logs: { id: string; agentId: AgentId; agentName: string; message: string; at: number; kind: string }[];
}
export type WorkspaceAction =
  | { type: 'START' | 'PAUSE' | 'RESUME' | 'TICK' | 'RESET' | 'APPROVE'; now: number; missionId?: number }
  | { type: 'NEW_TASK'; payload: string; now: number; missionId?: number }
  | { type: 'SELECT_AGENT'; payload: AgentId | null }
  | { type: 'SET_SPEED'; payload: 1 | 2 }
  | { type: 'SET_SYSTEM_MOTION'; payload: boolean }
  | { type: 'TOGGLE_MOTION' | 'OPEN_TASK' | 'CLOSE_TASK' }
  | { type: 'REMOTE_EVENT'; payload: SimulationEvent }
  | { type: 'PROTOCOL_STATE'; payload: Workspace };
export interface Command {
  schemaVersion: 1; commandId: string; missionId: number; action: WorkspaceAction;
  queuedRevision?: number; resolution?: 'ACK' | 'REJECT';
}
export interface CommandReply {
  type: 'ACK' | 'REJECT'; commandId: string; missionId: number; revision: number;
}
export interface Workspace {
  simulation: Simulation; missionId: number; selectedId: AgentId | null; speed: 1 | 2;
  manualReducedMotion: boolean; systemReducedMotion: boolean; taskOpen: boolean;
  connection: { mode: 'local' | 'ws' | 'sse'; status: string; error: string | null };
  pendingCommands: Command[];
}
/** subscribe returns unsubscribe; SSE must separately supply send. */
export interface InjectedTransport {
  send(command: Command): void;
  subscribe(callback: (message: SimulationEvent | CommandReply) => void): () => void;
}
export interface AdapterBindings {
  dispatch(action: WorkspaceAction): void;
  getState(): Workspace;
  subscribe(callback: (workspace: Workspace) => void): () => void;
  now?: () => number;
  transport?: InjectedTransport;
}
