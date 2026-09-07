import { useEffect, useState, useRef } from 'react'

import { API_URL, WS_BRIDGE_URL } from '../config'

function countdownDisplay(state) {
  if (state?.phase !== 'countdown') return null
  const label = state.countdown_label
  if (label === 'GO') return 'GO!'
  return label != null ? String(label) : null
}

function isInputBlocked(state) {
  if (!state) return true
  if (state.accepting_input === false) return true
  return state.phase && state.phase !== 'playing'
}

function showPhaseOverlay(state) {
  return ['countdown', 'level_clear', 'level_fail'].includes(state?.phase)
}

export default function SimulatorScreen({ config, onGameEnd }) {
  const [gameState, setGameState] = useState(null)
  const [gameId, setGameId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [stopping, setStopping] = useState(false)
  const [phaseReady, setPhaseReady] = useState(false)
  const iframeRef = useRef(null)
  const gameIdRef = useRef(null)
  const endedRef = useRef(false)
  const stateRef = useRef(null)
  const audioCtxRef = useRef(null)
  const prevScoreRef = useRef(0)
  const prevLifeRef = useRef(null)
  const startedRef = useRef(false)
  const bootTimerRef = useRef(null)

  const beep = (freq, durMs, type = 'sine', gain = 0.15) => {
    try {
      if (!audioCtxRef.current) {
        audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)()
      }
      const ctx = audioCtxRef.current
      const osc = ctx.createOscillator()
      const g = ctx.createGain()
      osc.type = type
      osc.frequency.value = freq
      g.gain.value = gain
      osc.connect(g); g.connect(ctx.destination)
      osc.start()
      g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + durMs / 1000)
      osc.stop(ctx.currentTime + durMs / 1000)
    } catch (e) { /* audio not available */ }
  }
  const playScore = () => beep(880, 120, 'triangle', 0.18)
  const playHurt = () => beep(140, 220, 'sawtooth', 0.22)

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true

    const startGame = async () => {
      try {
        const response = await fetch(`${API_URL}/start-game`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            card_id: config.cardId,
            level: config.level || 'A001',
            difficulty: config.difficulty || 'normal',
            ...(config.playMode === 'group' ? { mode: 'group' } : {}),
          })
        })
        const data = await response.json()
        if (data.success) {
          setGameId(data.game_id)
          gameIdRef.current = data.game_id
          setLoading(false)
        } else {
          setError(data.error || 'Failed to start game')
        }
      } catch (err) {
        setError(err.message)
      }
    }

    const resumeOrStart = async () => {
      if (!config.resumeGameId) {
        await startGame()
        return
      }
      try {
        const res = await fetch(`${API_URL}/game-state/${config.resumeGameId}`)
        const data = await res.json()
        if (data.success) {
          setGameId(config.resumeGameId)
          gameIdRef.current = config.resumeGameId
          setLoading(false)
          return
        }
      } catch (err) {
        console.warn('Resume check failed, starting fresh:', err)
      }
      await startGame()
    }

    resumeOrStart()
  }, [config])

  useEffect(() => {
    if (!gameId) return
    bootTimerRef.current = setTimeout(() => setPhaseReady(true), 2000)
    return () => {
      if (bootTimerRef.current) clearTimeout(bootTimerRef.current)
    }
  }, [gameId])

  const endGame = async (reason) => {
    if (endedRef.current) return
    endedRef.current = true
    setStopping(true)
    const id = gameIdRef.current
    const st = stateRef.current || {}
    const finalScore = st.score || 0
    const finalScore2 = st.score2 || 0
    const finalMultiplayer = st.multiplayer || false
    const finalTime = st.time_elapsed || 0
    const finalLife = st.life ?? 0
    const finalReason = st.game_over_reason === 'out_of_life'
      ? 'out_of_life' : (reason || 'stopped')
    try {
      await fetch(`${API_URL}/save-score`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          card_id: config.cardId,
          card_id2: config.cardId2 || null,
          level: config.level,
          end_level: st.current_level ?? config.level,
          score: finalScore,
          score2: finalScore2,
          final_score: st.final_score ?? finalScore,
          final_score2: st.final_score2 ?? finalScore2,
          multiplayer: finalMultiplayer,
          life: finalLife,
          lives_start: st.max_life ?? 0,
          result: st.result ?? null,
          time_used: finalTime,
          levels_cleared: st.levels_cleared ?? 0,
          difficulty: config.difficulty ?? '',
          started_at: st.started_at ?? ''
        })
      })
      await fetch(`${API_URL}/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ card_id: config.cardId, game_id: id })
      })
    } catch (err) {
      console.error('Stop/save error:', err)
    }
    onGameEnd({
      score: finalScore,
      score2: finalScore2,
      multiplayer: finalMultiplayer,
      time_elapsed: finalTime,
      life: finalLife,
      level: config.level,
      game: config.game,
      difficulty: config.difficulty,
      reason: finalReason
    })
  }

  useEffect(() => {
    if (!gameId) return
    const pollState = async () => {
      try {
        const response = await fetch(`${API_URL}/game-state/${gameId}`)
        const data = await response.json()
        if (data.success) {
          const st = data.state
          const backendAudio = st.backend_audio_active === true
          const phase = st.phase || 'idle'
          const inputLive = phase === 'playing' && st.accepting_input !== false

          if (st.phase) setPhaseReady(true)

          if (!backendAudio && inputLive) {
            if (st.score > prevScoreRef.current) playScore()
            if (prevLifeRef.current !== null && st.life < prevLifeRef.current) playHurt()
          }
          prevScoreRef.current = st.score
          prevLifeRef.current = st.life

          setGameState(st)
          stateRef.current = st
          if (st.game_over && !endedRef.current) {
            endGame('timeout')
          }
        }
      } catch (err) {
        console.error('Poll error:', err)
      }
    }
    const interval = setInterval(pollState, 100)
    return () => clearInterval(interval)
  }, [gameId])

  const booting = !phaseReady && gameId && !gameState?.phase

  if (loading && !gameId) {
    return (
      <div className="screen">
        <div className="card">
          <h2>Starting Game...</h2>
          <p style={{ textAlign: 'center', marginTop: '20px' }}>
            {config.game.toUpperCase()} - Level {config.level} ({config.difficulty})
          </p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="screen">
        <div className="card">
          <h2>Error</h2>
          <p style={{ color: '#ff6b6b', marginTop: '20px' }}>{error}</p>
        </div>
      </div>
    )
  }

  const timeLeft = gameState?.time_left != null ? gameState.time_left : 300
  const life = gameState?.display_lives ?? gameState?.life ?? gameState?.max_life ?? 0
  const maxLife = gameState?.display_max ?? gameState?.max_life ?? 5
  const isOver = gameState?.game_over
  const currentLevel = gameState?.current_level ?? config.level
  const phase = gameState?.phase || (isOver ? 'session_end' : booting ? 'idle' : 'playing')
  const inputLocked = isInputBlocked(gameState)
  const overlayCountdownText = countdownDisplay(gameState)
  const phaseLabel = {
    idle: '● STARTING',
    playing: '● PLAYING',
    countdown: '● COUNTDOWN',
    level_clear: '● LEVEL CLEAR',
    level_fail: '● LEVEL FAIL',
    session_end: '● SESSION END',
  }[phase] || (isOver ? '● ENDED' : '● STARTING')

  return (
    <div className="simulator-container">
      <div className="simulator-header">
        <div>
          <h2 style={{ margin: 0 }}>
            {config.game.toUpperCase()} - Level {currentLevel}
          </h2>
          <span style={{ fontSize: '0.8rem', color: '#888' }}>
            {config.difficulty?.toUpperCase()}
          </span>
        </div>

        <div className="game-info">
          <div className="game-info-item">
            <span className="game-info-value">{gameState?.score ?? 0}</span>
            <span>Score</span>
          </div>
          <div className="game-info-item">
            <span className="game-info-value" style={{ color: timeLeft < 30 ? '#ff6b6b' : '#fff' }}>
              {Math.max(0, timeLeft).toFixed(0)}s
            </span>
            <span>Time Left</span>
          </div>
          <div className="game-info-item">
            <span className="game-info-value" style={{ color: life <= maxLife * 0.3 ? '#ff6b6b' : '#51cf66' }}>
              {life}/{maxLife}
            </span>
            <span>Life</span>
          </div>
          <div className="game-info-item">
            <span style={{ color: isOver ? '#ff6b6b' : phase === 'playing' ? '#51cf66' : '#f5a623' }}>
              {isOver ? '● ENDED' : phaseLabel}
            </span>
            <span>Status</span>
          </div>
          <button
            onClick={() => endGame('stopped')}
            disabled={stopping}
            style={{
              background: '#ff6b6b',
              padding: '10px 20px',
              fontSize: '0.9rem',
              width: 'auto',
              margin: 0
            }}
          >
            {stopping ? 'Stopping...' : '■ Stop Game'}
          </button>
        </div>
      </div>

      <div className="simulator-stage">
        {booting && (
          <div className="boot-banner">
            <h2>Starting Game...</h2>
            <p>{config.game.toUpperCase()} - Level {config.level}</p>
          </div>
        )}

        <iframe
          ref={iframeRef}
          className={`simulator-iframe${inputLocked ? ' simulator-iframe--blocked' : ''}`}
          src={gameId ? `${WS_BRIDGE_URL}?game_id=${gameId}` : WS_BRIDGE_URL}
          style={{ width: '100%', height: '100%', border: 'none', pointerEvents: inputLocked ? 'none' : 'auto' }}
          title="Game Simulator"
        />

        {showPhaseOverlay(gameState) && phase === 'countdown' && !isOver && overlayCountdownText && (
          <div className="phase-countdown-overlay" aria-live="polite">
            <div className={`countdown-num${overlayCountdownText === 'GO!' ? ' go' : ''}`}>
              {overlayCountdownText}
            </div>
            <div className="countdown-meta">Level {currentLevel}</div>
          </div>
        )}

        {(phase === 'level_clear' || phase === 'level_fail') && !isOver && (
          <div className={`phase-overlay ${phase}-overlay`} aria-live="polite">
            {phase === 'level_clear' ? 'Level clear!' : 'Try again!'}
          </div>
        )}
      </div>

      {(config.playerName || config.playerName2) && (
        <div style={{
          padding: '8px 20px', fontSize: '0.8rem', color: '#9aa0a6',
          borderTop: '1px solid #1e1e2e', background: '#0a0a12',
          display: 'flex', gap: '1.5rem',
        }}>
          {config.playerName && (
            <span>👤 {config.playerName}{config.minutesRemaining != null ? ` — ${Math.round(config.minutesRemaining)} min left` : ''}</span>
          )}
          {config.playerName2 && (
            <span style={{ color: '#ffaa44' }}>👤 {config.playerName2}{config.minutesRemaining2 != null ? ` — ${Math.round(config.minutesRemaining2)} min left` : ''}</span>
          )}
        </div>
      )}
      <div style={{
        padding: '10px 20px',
        fontSize: '0.75rem',
        color: '#666',
        borderTop: '1px solid #1e1e2e',
        background: '#06060c'
      }}>
        Game ID: {gameId} | P1: {config.cardId}{config.cardId2 ? ` | P2: ${config.cardId2}` : ''}
      </div>
    </div>
  )
}
