import React from 'react'

// Mock SMS/email dispatch surfaces here. The full message body is shown, not a
// "sent!" confirmation - the point is for a judge to read what an officer gets.
export default function Toast({ toasts, onDismiss }) {
  if (!toasts.length) return null
  return (
    <div className="toast-stack">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>
          <div className="toast-head">
            <span>{t.channel === 'sms' ? 'SMS dispatched (mock)' : 'Email dispatched (mock)'}</span>
            <button className="toast-x" onClick={() => onDismiss(t.id)}>&times;</button>
          </div>
          <div className="toast-to mono">To: {t.to}</div>
          <pre className="toast-body">{t.body}</pre>
          <div className="toast-note">{t.note}</div>
        </div>
      ))}
    </div>
  )
}
