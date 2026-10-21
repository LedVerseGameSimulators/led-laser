import { useState, useEffect } from 'react'
import SetupScreen     from './screens/SetupScreen'
import LoginScreen     from './screens/LoginScreen'
import CountdownScreen from './screens/CountdownScreen'
import SimulatorScreen from './screens/SimulatorScreen'
import ResultScreen    from './screens/ResultScreen'

import { API_URL } from './config'
import { loadRfidResumeContext } from './rfidResumeContext'
import VideoBackground from './components/VideoBackground'

const S = {
  SETUP:     'setup',      // Mode + Level (one screen)
  LOGIN:     'login',
  COUNTDOWN: 'countdown',
  SIMULATOR: 'simulator',
  RESULT:    'result',
}

const DEFAULT_CONFIG = {
  game: 'laser',
  playMode: 'single',
  level: 'B04',
  playerCount: 1,
  difficulty: 'normal',
  cardId: '',
  cardId2: '',
  playerName: '',
  playerName2: '',
  minutesRemaining: null,
  minutesRemaining2: null,
  rfidValidate: null,
  rfidValidate2: null,
}

export default function App() {
  const [screen, setScreen] = useState(S.SETUP)
  const [gameConfig, setGameConfig] = useState(DEFAULT_CONFIG)
  const [result, setResult] = useState(null)
  const [booting, setBooting] = useState(true)
  const [playlists, setPlaylists] = useState(null)

  useEffect(() => {
    fetch(`${API_URL}/playlists`)
      .then((r) => r.json())
      .then((data) => setPlaylists(data))
      .catch((err) => console.warn('playlists fetch failed:', err))
  }, [])

  useEffect(() => {
    fetch(`${API_URL}/active-game`)
      .then((r) => r.json())
      .then((d) => {
        if (d.success) {
          const saved = loadRfidResumeContext(d.game_id)
          setGameConfig((prev) => ({
            ...prev,
            cardId: saved?.cardId ?? d.card_id,
            level: saved?.level ?? d.level,
            difficulty: saved?.difficulty ?? d.difficulty,
            resumeGameId: d.game_id,
            ...(saved
              ? {
                  playMode: saved.playMode ?? prev.playMode,
                  playerCount: saved.playerCount ?? prev.playerCount,
                  cardId2: saved.cardId2 ?? prev.cardId2,
                  rfidValidate: saved.rfidValidate ?? prev.rfidValidate,
                  rfidValidate2: saved.rfidValidate2 ?? prev.rfidValidate2,
                  playerName: saved.playerName ?? prev.playerName,
                  playerName2: saved.playerName2 ?? prev.playerName2,
                  minutesRemaining: saved.minutesRemaining ?? prev.minutesRemaining,
                  minutesRemaining2: saved.minutesRemaining2 ?? prev.minutesRemaining2,
                  game: saved.game ?? prev.game,
                }
              : {}),
          }))
          setScreen(S.SIMULATOR)
        }
      })
      .catch(() => {})
      .finally(() => setBooting(false))
  }, [])

  // Setup confirmed (mode + level together)
  const handleSetup = ({ game, level, playerCount, difficulty, playMode }) => {
    setGameConfig((prev) => ({
      ...prev,
      game,
      level,
      playerCount,
      difficulty,
      playMode: playMode || prev.playMode,
      resumeGameId: undefined,
    }))
    setScreen(S.LOGIN)
  }

  const handleLogin = (
    cardId,
    cardId2,
    playerName = '',
    playerName2 = '',
    minutesRemaining = null,
    minutesRemaining2 = null,
    rfidValidate = null,
    rfidValidate2 = null
  ) => {
    setGameConfig((prev) => ({
      ...prev,
      cardId: cardId || '',
      cardId2: cardId2 || '',
      playerName: playerName || '',
      playerName2: playerName2 || '',
      minutesRemaining,
      minutesRemaining2,
      rfidValidate,
      rfidValidate2,
    }))
    setScreen(S.COUNTDOWN)
  }

  const handleCountdownDone = () => setScreen(S.SIMULATOR)

  const handleGameEnd = (finalResult) => {
    setResult(finalResult)
    setScreen(S.RESULT)
  }

  const handlePlayAgain = () => {
    setResult(null)
    setScreen(S.SETUP)
  }

  const handleLogout = () => {
    setResult(null)
    setGameConfig({ ...DEFAULT_CONFIG })
    setScreen(S.SETUP)
  }

  if (booting) {
    return (
      <div className="screen screen-with-video">
        <VideoBackground />
        <div className="card">
          <h2 style={{ textAlign: 'center' }}>Loading…</h2>
        </div>
      </div>
    )
  }

  return (
    <>
      {screen === S.SETUP && (
        <SetupScreen
          game={gameConfig.game}
          playlists={playlists}
          onConfirm={handleSetup}
        />
      )}
      {screen === S.LOGIN && (
        <LoginScreen
          gameTitle="Laser Escape"
          playerCount={gameConfig.playerCount}
          onLogin={handleLogin}
          onBack={() => setScreen(S.SETUP)}
        />
      )}
      {screen === S.COUNTDOWN && (
        <CountdownScreen onDone={handleCountdownDone} />
      )}
      {screen === S.SIMULATOR && (
        <SimulatorScreen
          config={gameConfig}
          playlists={playlists}
          onGameEnd={handleGameEnd}
        />
      )}
      {screen === S.RESULT && (
        <ResultScreen
          result={result}
          config={gameConfig}
          playlists={playlists}
          onPlayAgain={handlePlayAgain}
          onLogout={handleLogout}
        />
      )}
    </>
  )
}
