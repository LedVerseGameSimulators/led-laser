import { useState } from 'react'

// playerCount: 1 or 2 — shows one or two card ID fields.
export default function LoginScreen({ onLogin, playerCount = 1, onBack }) {
  const [card1, setCard1] = useState('')
  const [card2, setCard2] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!card1.trim()) { setError('Enter P1 card ID'); return }
    if (playerCount === 2 && !card2.trim()) { setError('Enter P2 card ID'); return }
    onLogin(card1.trim(), playerCount === 2 ? card2.trim() : null)
  }

  return (
    <div className="screen">
      <div className="card">
        <h1>🎮 LED Hex Game</h1>
        <p style={{ textAlign: 'center', color: '#888', marginTop: '-10px' }}>
          {playerCount === 2 ? '2-Player Login' : '1-Player Login'}
        </p>
        <form onSubmit={handleSubmit}>
          <div className="input-group" style={{ marginTop: '20px' }}>
            <label>Player 1 — Card ID</label>
            <input
              type="text"
              placeholder="Scan or enter card ID"
              value={card1}
              onChange={e => { setCard1(e.target.value); setError('') }}
              autoFocus
            />
          </div>

          {playerCount === 2 && (
            <div className="input-group" style={{ marginTop: '14px' }}>
              <label>Player 2 — Card ID</label>
              <input
                type="text"
                placeholder="Scan or enter card ID"
                value={card2}
                onChange={e => { setCard2(e.target.value); setError('') }}
              />
            </div>
          )}

          {error && <div className="error">{error}</div>}
          <button type="submit" style={{ marginTop: '20px' }}>Start Game</button>
          {onBack && (
            <button type="button" onClick={onBack}
                    style={{ background: '#333', marginTop: '10px' }}>
              Back
            </button>
          )}
        </form>
      </div>
    </div>
  )
}
