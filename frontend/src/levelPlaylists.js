/**
 * Mode playlist helpers — ordered lists come from GET /playlists at runtime.
 * Laser: Quick Play + Tournament only (no Team Battle).
 */

export const HOW_TO = {
  single:
    'Dodge the lasers and hit the lit targets. Clear each wave to advance.',
  multi:
    'Team Battle is not offered on Laser Escape.',
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

export function playlistModeKey(playMode) {
  if (playMode === 'multi') return 'multi'
  if (playMode === 'group') return 'group'
  return 'single'
}

/** Entries for a play mode from API payload { single, multi, group }. */
export function entriesForPlayMode(playlists, playMode) {
  if (!playlists) return []
  const key = playlistModeKey(playMode)
  return playlists[key] || []
}

export function idsForPlayMode(playlists, playMode) {
  return entriesForPlayMode(playlists, playMode).map((e) => e.id)
}

/** Map backend level stem → UI number (1-based) within the full mode playlist. */
export function displayLevelNumber(playMode, levelId, playlists) {
  const stem = String(levelId ?? '')
    .replace(/\.(led|ledb)$/i, '')
    .trim()
  if (!stem || stem === 'auto') return null
  const ids = idsForPlayMode(playlists, playMode)
  const idx = ids.findIndex((id) => id === stem)
  if (idx >= 0) return idx + 1
  return null
}

export function formatLevelLabel(playMode, levelId, playlists) {
  const n = displayLevelNumber(playMode, levelId, playlists)
  if (n != null) return String(n)
  return String(levelId ?? '—')
}

export function firstPlaylistId(playlists, playMode) {
  const entries = entriesForPlayMode(playlists, playMode)
  return entries.length ? entries[0].id : null
}
