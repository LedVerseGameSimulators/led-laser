import { useState, useEffect } from 'react'

import { API_URL } from '../config'

const CAT_LABEL = {
  casual:   { label: 'Casual',   desc: 'A001-A009' },
  level:    { label: 'Level',    desc: 'B01-B09' },
  advanced: { label: 'Advanced', desc: 'C01-C09' },
  intro:    { label: 'Intro',    desc: '02-10' },
}

const DIFFICULTIES = ['easy', 'normal', 'hard']

function pickDefaultCategory(cats, players) {
  const preferred = players === 2
    ? ['casual', 'level', 'advanced', 'intro']
    : ['casual', 'intro', 'level', 'advanced']
  for (const cat of preferred) {
    const lvls = cats[cat] || []
    const ok = players === 2
      ? lvls.some(l => l.multiplayer)
      : lvls.some(l => !l.multiplayer)
    if (ok) return cat
  }
  return Object.keys(cats)[0] || 'casual'
}

export default function GameSettingsScreen({ game, playerCount, onConfirm, onBack }) {
  const players = playerCount ?? 1
  const [categories, setCategories] = useState({})
  const [category, setCategory]     = useState('casual')
  const [level, setLevel]           = useState('')
  const [difficulty, setDifficulty] = useState('normal')
  const [loading, setLoading]       = useState(true)

  useEffect(() => {
    setLoading(true)
    fetch(`${API_URL}/levels`)
      .then(r => r.json())
      .then(d => {
        if (d.success) {
          const cats = d.categories || {}
          setCategories(cats)
          const defaultCat = pickDefaultCategory(cats, players)
          setCategory(defaultCat)
          const pool = cats[defaultCat] || []
          const first = players === 2
            ? pool.find(l => l.multiplayer)
            : pool.find(l => !l.multiplayer)
          if (first) setLevel(first.id)
          else if (pool[0]) setLevel(pool[0].id)
          else setLevel('A001')
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [players])

  const filteredLevels = (cat = category) => {
    const all = categories[cat] || []
    if (players === 2) return all.filter(l => l.multiplayer)
    return all.filter(l => !l.multiplayer)
  }

  const handleCategory = (cat) => {
    setCategory(cat)
    const lvls = filteredLevels(cat)
    if (lvls.length) setLevel(lvls[0].id)
  }

  const availableCats = Object.keys(categories).filter(cat => {
    const lvls = categories[cat] || []
    return players === 2
      ? lvls.some(l => l.multiplayer)
      : lvls.some(l => !l.multiplayer)
  })

  const levelList = filteredLevels()
  const selectedLevel = levelList.find(l => l.id === level) || levelList[0]

  const handleConfirm = () => {
    if (!selectedLevel) return
    onConfirm({
      game,
      level: selectedLevel.id,
      levelData: selectedLevel,
      playerCount: players,
      difficulty,
    })
  }

  if (loading) return (
    <div className="screen">
      <div className="card settings-card">
        <p style={{ textAlign: 'center', color: 'var(--text-muted)' }}>Loading levels…</p>
      </div>
    </div>
  )

  return (
    <div className="screen">
      <div className="card settings-card">
        <h1>Laser Trap</h1>
        <p className="settings-subtitle">
          Game Settings · {players === 2 ? '2 Players' : '1 Player'}
        </p>

        {/* Category rail */}
        <h2 className="settings-section-label">CATEGORY</h2>
        <div className="cat-rail" role="listbox" aria-label="Categories">
          {availableCats.map(cat => (
            <button
              key={cat}
              type="button"
              role="option"
              aria-selected={category === cat}
              className={`cat-chip ${category === cat ? 'selected' : ''}`}
              onClick={() => handleCategory(cat)}
            >
              <span className="cat-chip-label">{CAT_LABEL[cat]?.label || cat}</span>
              <span className="cat-chip-desc">{CAT_LABEL[cat]?.desc}</span>
            </button>
          ))}
        </div>

        {/* Level rail */}
        <h2 className="settings-section-label">
          LEVEL <span className="settings-count">({levelList.length} available)</span>
        </h2>
        <div className="level-rail" role="listbox" aria-label="Levels">
          {levelList.map(lv => (
            <button
              key={lv.id}
              type="button"
              role="option"
              aria-selected={level === lv.id}
              className={`level-chip ${level === lv.id ? 'selected' : ''}`}
              onClick={() => setLevel(lv.id)}
            >
              {lv.name}
            </button>
          ))}
          {levelList.length === 0 && (
            <p className="rail-empty">No levels for this mode</p>
          )}
        </div>

        {/* Difficulty */}
        <h2 className="settings-section-label">DIFFICULTY</h2>
        <div className="diff-row">
          {DIFFICULTIES.map(d => (
            <button
              key={d}
              type="button"
              className={`option-btn ${difficulty === d ? 'selected' : ''}`}
              style={{ flex: 1, margin: 0 }}
              onClick={() => setDifficulty(d)}
            >
              {d.charAt(0).toUpperCase() + d.slice(1)}
            </button>
          ))}
        </div>

        <button onClick={handleConfirm} style={{ marginTop: '24px' }}
                disabled={!selectedLevel}>
          Next → Login
        </button>
        <button onClick={onBack} className="btn-secondary" style={{ marginTop: '10px' }}>
          Back
        </button>
      </div>
    </div>
  )
}
