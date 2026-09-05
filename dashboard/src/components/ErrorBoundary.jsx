import React from 'react'

// Any render error anywhere below this shows a readable panel instead of the
// blank white page React gives you by default.
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error) { return { error } }
  componentDidCatch(error, info) { console.error('FraudLens UI error:', error, info) }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="center-msg">
        <h2>The dashboard hit an unexpected error</h2>
        <p>The rest of the system is unaffected. Reload the page to try again; if it
           persists, the message below identifies where it broke.</p>
        <div className="err-box mono">{String(this.state.error?.message || this.state.error)}</div>
        <button className="btn" onClick={() => window.location.reload()}>Reload dashboard</button>
      </div>
    )
  }
}
