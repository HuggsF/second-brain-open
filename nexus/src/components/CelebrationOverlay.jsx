import React from 'react';
export default function CelebrationOverlay() {
  return <div className="celebration-overlay" aria-hidden="true">
    {Array.from({ length: 24 }, (_, i) => (
      <span key={i} className="confetti-piece" style={{
        '--x': ((i * 37) % 100) + '%',
        '--delay': ((i % 5) / 10) + 's',
        '--hue': (i * 47) % 360,
        '--size': (4 + (i % 6)) + 'px',
      }} />
    ))}
  </div>;
}
