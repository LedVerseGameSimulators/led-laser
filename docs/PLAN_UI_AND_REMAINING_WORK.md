# Laser — UI redesign + remaining work

**Date:** 2026-09-16  
**Repo:** `led-laser`  
**Parent:** `docs/PLAN_FE_REDESIGN_AND_WORK_INDEX.md`

---

## Locked FE decisions

| Topic | Decision |
|-------|----------|
| Journey | **Mode → Settings\* → Login → Play** (*Tournament skips Settings) |
| Modes | **Quick Play** + **Tournament only** (no Team Battle) |
| Levels | QP: **20** placeholders, Medium; Tournament: existing **~10**, **no level select** |
| Login | **Always** — RFID **or** play without RFID → **random names**; **no** name-typing form |
| Tournament names | UI **1, 2, 3…** on HUD + results/leaderboards (never file names) |
| Orientation | **Landscape only** |
| Video | **One** bg loop per game (reuse across Mode / Login / Results) |
| How-to-play | **We write** short copy; client can edit later |
| Countdown | **Both** — TV overlay on play **and** floor `countdown.led` |
| Screen order | **Locked = today’s order** (mock Login→Setup→Countdown is visual ref only) |

---

## Implementation status

- [x] Decisions locked (2026-09-16)
- [x] Score/RFID logical level labels (Hex contract): `levelPlaylists.js`, guest skip save, `level_file` columns
- [ ] **After Hex FE shell** is the template — apply same shell here (2 mode cards)
- [ ] Wire Quick Play + Tournament; QP 20 placeholders; Tournament skip Settings
- [ ] Login: RFID path + guest random names
- [ ] Copy `laser_background.mp4` → `frontend/public/media/` + wire bg
- [ ] Restyle Play HUD + Results; Tournament labels 1, 2, 3…

---

## Non-FE leftovers

- [ ] No multiplayer / Team Battle for Laser — by design
- [ ] Effects on HW — treated done onsite; reopen only on regression
- [ ] Optional: delete dead FE screens

---

## Assets

| Asset | Path (not in repo yet) |
|-------|------------------------|
| Loop | `~/Downloads/activerse_redesign/laser_background.mp4` |
| Still | `~/Downloads/activerse_redesign/laser.jpeg` |
