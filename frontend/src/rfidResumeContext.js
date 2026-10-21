/** Client-side RFID/play context for reload resume (Step 0 Round 2). */

const PREFIX = 'laser_rfid_resume:'

export function pickResumeFields(config) {
  return {
    playMode: config.playMode,
    playerCount: config.playerCount,
    cardId: config.cardId,
    cardId2: config.cardId2,
    rfidValidate: config.rfidValidate,
    rfidValidate2: config.rfidValidate2,
    playerName: config.playerName,
    playerName2: config.playerName2,
    minutesRemaining: config.minutesRemaining,
    minutesRemaining2: config.minutesRemaining2,
    level: config.level,
    difficulty: config.difficulty,
    game: config.game,
  }
}

export function saveRfidResumeContext(gameId, ctx) {
  if (!gameId || !ctx) return
  try {
    sessionStorage.setItem(`${PREFIX}${gameId}`, JSON.stringify(ctx))
  } catch {
    /* storage blocked */
  }
}

export function loadRfidResumeContext(gameId) {
  if (!gameId) return null
  try {
    const raw = sessionStorage.getItem(`${PREFIX}${gameId}`)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function clearRfidResumeContext(gameId) {
  if (!gameId) return
  try {
    sessionStorage.removeItem(`${PREFIX}${gameId}`)
  } catch {
    /* ignore */
  }
}
