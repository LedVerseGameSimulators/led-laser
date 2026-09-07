import { useState, useEffect } from 'react'
import LoginScreen        from './screens/LoginScreen'
import GameSelectionScreen from './screens/GameSelectionScreen'
import GameSettingsScreen  from './screens/GameSettingsScreen'
import SimulatorScreen     from './screens/SimulatorScreen'
import ResultScreen        from './screens/ResultScreen'

import { API_URL } from './config'

const S = {
  GAME_SELECT: 'game_select',  // pick play mode (single / group)
  SETTINGS:    'settings',     // pick category + level + difficulty
  LOGIN:       'login',        // enter card ID
  SIMULATOR:   'simulator',
  RESULT:      'result',
}

const DEFAULT_CONFIG = {
  game: 'laser',
  playMode: 'single',
  level: 'A001',
  playerCount: 1,
  difficulty: 'normal',
  cardId: '',
  cardId2: '',
  playerName: '',
  playerName2: '',
  minutesRemaining: null,
  minutesRemaining2: null,
}

export default function App() {
  const [screen, setScreen] = useState(S.GAME_SELECT)
  const [gameConfig, setGameConfig] = useState(DEFAULT_CONFIG)
  const [result, setResult] = useState(null)
  const [booting, setBooting] = useState(true)

  // Resume running game on reload
  useEffect(() => {
    fetch(`${API_URL}/active-game`)
      .then(r => r.json())
      .then(d => {
        if (d.success) {
          setGameConfig(prev => ({
            ...prev,
            cardId: d.card_id,
            level: d.level,
            difficulty: d.difficulty,
            resumeGameId: d.game_id,
          }))
          setScreen(S.SIMULATOR)
        }
      })
      .catch(() => {})
      .finally(() => setBooting(false))
  }, [])

  // Step 1: play mode (single | group)
  const handleModeSelect = (mode) => {
    if (mode === 'group') {
      setGameConfig(prev => ({
        ...prev,
        game: 'laser',
        playMode: 'group',
        playerCount: 1,
        level: 'auto',
        difficulty: 'normal',
        resumeGameId: undefined,
      }))
      setScreen(S.LOGIN)
      return
    }

    setGameConfig(prev => ({
      ...prev,
      game: 'laser',
      playMode: 'single',
      playerCount: 1,
    }))
    setScreen(S.SETTINGS)
  }

  // Step 2: settings confirmed
  const handleSettings = ({ game, level, playerCount, difficulty }) => {
    setGameConfig(prev => ({
      ...prev,
      game: game || prev.game || 'laser',
      level,
      playerCount,
      difficulty,
      resumeGameId: undefined,
    }))
    setScreen(S.LOGIN)
  }

  // Step 3: login
  const handleLogin = (cardId, cardId2, playerName = '', playerName2 = '',
                       minutesRemaining = null, minutesRemaining2 = null) => {
    setGameConfig(prev => ({
      ...prev,
      cardId: cardId || '',
      cardId2: cardId2 || '',
      playerName: playerName || '',
      playerName2: playerName2 || '',
      minutesRemaining,
      minutesRemaining2,
    }))
    setScreen(S.SIMULATOR)
  }

  const handleGameEnd = (finalResult) => {
    setResult(finalResult)
    setScreen(S.RESULT)
  }

  const handlePlayAgain = () => {
    setResult(null)
    setScreen(gameConfig.playMode === 'group' ? S.GAME_SELECT : S.SETTINGS)
  }

  const handleLogout = () => {
    setResult(null)
    setGameConfig({ ...DEFAULT_CONFIG })
    setScreen(S.GAME_SELECT)
  }

  if (booting) return (
    <div className="screen">
      <div className="card"><h2 style={{ textAlign: 'center' }}>Loading…</h2></div>
    </div>
  )

  return (
    <>
      {screen === S.GAME_SELECT && (
        <GameSelectionScreen onSelect={handleModeSelect} />
      )}
      {screen === S.SETTINGS && (
        <GameSettingsScreen
          game={gameConfig.game}
          onConfirm={handleSettings}
          onBack={() => setScreen(S.GAME_SELECT)}
        />
      )}
      {screen === S.LOGIN && (
        <LoginScreen
          gameTitle="🔴 Laser Trap"
          playerCount={gameConfig.playerCount}
          onLogin={handleLogin}
          onBack={() => setScreen(
            gameConfig.playMode === 'group' ? S.GAME_SELECT : S.SETTINGS
          )}
        />
      )}
      {screen === S.SIMULATOR && (
        <SimulatorScreen config={gameConfig} onGameEnd={handleGameEnd} />
      )}
      {screen === S.RESULT && (
        <ResultScreen
          result={result}
          config={gameConfig}
          onPlayAgain={handlePlayAgain}
          onLogout={handleLogout}
        />
      )}
    </>
  )
}
