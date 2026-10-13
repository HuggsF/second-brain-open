import React from 'react';
export default function SpeechBubble({ text, type }) {
  if (!text) return null;
  const typeClass = type === 'celebration' ? ' bubble-celebration' :
    type === 'approval_request' ? ' bubble-approval' :
    type === 'context_share' || type === 'handoff_review' ? ' bubble-handoff' : '';
  return <div className={`speech-bubble${typeClass}`} aria-live="polite">
    <span className="bubble-text">{text}</span>
    <span className="bubble-tail" aria-hidden="true" />
  </div>;
}
