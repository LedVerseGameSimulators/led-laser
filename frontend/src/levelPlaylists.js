/**
 * Placeholder playlists for Laser FE redesign.
 * Real 20-level lists will replace these when the team delivers them.
 * Backend still receives real file ids (stems); UI may show 1..N.
 *
 * Modes: Quick Play + Tournament only (no Team Battle product).
 * Prefer clean A/B/C stems — no Chinese test files; Challenge only in tournament.
 */

/** Quick Play (1P) — 20 medium-ish placeholders from A / B / C. */
export const QUICK_PLAY_LEVELS = [
  'A001', 'A002', 'A003', 'A004', 'A005', 'A007', 'A008', 'A009',
  'B01', 'B02', 'B03', 'B04', 'B05', 'B06', 'B07', 'B08', 'B09',
  'C02', 'C03', 'C04',
]

/**
 * Multi / Team Battle playlist — unused product-wise; mirrors QP so helpers stay safe.
 */
export const TEAM_BATTLE_LEVELS = [...QUICK_PLAY_LEVELS]

/**
 * Tournament playlist order (matches games/source_group/--- /
 * _GROUP_CORPORATE_ORDER). Last slot is the onsite stand-in for missing C10.
 */
export const TOURNAMENT_LEVEL_ORDER = [
  'C02', 'C03', 'C04', 'C05', 'C06', 'C07', 'C08', 'C09',
  'C01 Challenge - 240 Pts',
]

export const HOW_TO = {
  single:
    'Dodge the lasers and hit the lit targets. Clear each wave to advance.',
  multi:
    'Same as Quick Play — Team Battle is not offered on Laser.',
  group:
    'A fixed Extreme set runs in order. No level pick — play through 1, 2, 3… as a group session.',
}

/** Bullet copy for Setup screen (mock-style how-to). */
export const HOW_TO_BULLETS = {
  single: [
    'Dodge moving lasers and stay in the safe lanes.',
    'Hit lit targets before they expire.',
    'Clear each wave to advance to the next level.',
  ],
  multi: [
    'Team Battle is not offered on Laser Escape.',
  ],
  group: [
    'A fixed tournament set runs in order — no level pick.',
    'Play through levels 1, 2, 3… as a group session.',
    'Clear each stage to keep moving.',
  ],
}

export function playlistForMode(playMode) {
  if (playMode === 'multi') return TEAM_BATTLE_LEVELS
  if (playMode === 'group') return TOURNAMENT_LEVEL_ORDER
  return QUICK_PLAY_LEVELS
}

/** Map backend level stem → UI number (1-based) within the active playlist. */
export function displayLevelNumber(playMode, levelId) {
  const stem = String(levelId ?? '')
    .replace(/\.(led|ledb)$/i, '')
    .trim()
  if (!stem || stem === 'auto') return null
  const list = playlistForMode(playMode)
  const idx = list.findIndex(
    (id) => id === stem || stem.startsWith(id) || id.startsWith(stem)
  )
  if (idx >= 0) return idx + 1
  if (/^\d+$/.test(stem)) return Number(stem)
  return null
}

export function formatLevelLabel(playMode, levelId) {
  const n = displayLevelNumber(playMode, levelId)
  if (n != null) return String(n)
  return String(levelId ?? '—')
}
