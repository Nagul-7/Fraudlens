import React from 'react'

// Mock auth: a switcher, not a login. The point it demonstrates is that the
// SERVER returns different data per role - a bank response contains no crime
// intelligence at all, and a state response contains no other state's alerts.
export default function RoleSwitcher({ roles, role, setRole, note }) {
  const current = roles.find((r) => r.id === role.id)
  const opts = current?.options || []

  return (
    <div className="role-block">
      <div className="clock-label" title={note}>
        Signed in as <span className="info-dot">i</span>
      </div>
      <div className="role-row">
        <div className="role-tabs">
          {roles.map((r) => (
            <button key={r.id}
                    className={`role-tab ${role.id === r.id ? 'on' : ''}`}
                    title={r.scope}
                    onClick={() => setRole({
                      id: r.id,
                      stateName: r.id === 'STATE' ? (role.stateName || r.options?.[0] || '') : '',
                      bank: r.id === 'BANK' ? (role.bank || r.options?.[0] || '') : '',
                    })}>
              {r.label}
            </button>
          ))}
        </div>
        {role.id === 'STATE' && (
          <select value={role.stateName}
                  onChange={(e) => setRole({ ...role, stateName: e.target.value })}>
            {opts.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        )}
        {role.id === 'BANK' && (
          <select value={role.bank}
                  onChange={(e) => setRole({ ...role, bank: e.target.value })}>
            {opts.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
        )}
      </div>
      <div className="role-scope" title={note}>{current?.scope}</div>
    </div>
  )
}
