const GAMES = [
  { id: 'led_hex',       name: 'LED Hex',      emoji: '🔷' },
  { id: 'hoops',         name: 'Hoops',         emoji: '🏀' },
  { id: 'climb',         name: 'Climb',         emoji: '⛰️' },
  { id: 'laser',         name: 'Laser',         emoji: '🔴' },
  { id: 'battle_arena',  name: 'Battle Arena',  emoji: '⚔️' },
]

export default function GameSelectionScreen({ onSelect }) {
  return (
    <div className="screen">
      <div className="card">
        <h1>Select Game</h1>
        <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', marginTop: '20px' }}>
          {GAMES.map(g => (
            <button
              key={g.id}
              className="option-btn"
              onClick={() => onSelect(g.id)}
            >
              <div style={{ fontSize: '2rem', marginBottom: '8px' }}>{g.emoji}</div>
              <div>{g.name}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
