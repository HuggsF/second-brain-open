import React from 'react';
import { Network } from 'lucide-react';
import { ROOMS, Plant } from './Shared.jsx';
import Room from './Room.jsx';
import TransferPacket from './TransferPacket.jsx';
import CelebrationOverlay from './CelebrationOverlay.jsx';

export default function OfficeFloor({ simulation, missionId, paused, reducedMotion, bubbles, transfers, onSelect, selectedId, celebrating }) {
  return <div className="office-floor" data-mission-id={missionId}>
    {ROOMS.map(room => {
      const agent = simulation.agents.find(candidate => candidate.room === room.id);
      return <Room key={room.id} room={room} agent={agent} selected={agent.id === selectedId}
        onSelect={onSelect} paused={paused} bubble={bubbles[agent.id]} />;
    })}
    <div className="floor-walkway" aria-hidden="true">
      <span className="walkway-label"><Network size={13} /> CONTEXTO COMPARTILHADO</span><Plant />
    </div>
    <div className="floor-entry" aria-hidden="true"><span /> NEXUS STUDIO</div>
    <div className="transfer-overlay" aria-hidden="true">
      {!reducedMotion && transfers.map(transfer => <TransferPacket key={missionId + ':' + transfer.id} transfer={transfer} />)}
    </div>
    {celebrating && !reducedMotion && <CelebrationOverlay key={missionId} />}
  </div>;
}
