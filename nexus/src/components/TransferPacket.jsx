import React from 'react';
import { DESK_POSITIONS, fromRoom } from './Shared.jsx';
export default function TransferPacket({ transfer }) {
  const from = DESK_POSITIONS[fromRoom(transfer.from)] || DESK_POSITIONS.corridor;
  const to = DESK_POSITIONS[fromRoom(transfer.to)] || DESK_POSITIONS.corridor;
  const style = {
    '--from-x': from.x + '%',
    '--from-y': from.y + '%',
    '--to-x': to.x + '%',
    '--to-y': to.y + '%',
    animationDelay: transfer.delay + 'ms',
  };
  return <div className={`transfer-packet transfer-${transfer.type}`} style={style} aria-hidden="true">
    <span className="packet-icon">📄</span>
  </div>;
}
