# Laser Escape — effect `.led` files

Regenerate production assets:

```bash
python scripts/build_effect_led.py
```

Fast pytest fixtures:

```bash
python scripts/build_effect_led.py --fast --test-levels
```

| File | Duration (prod) | Pattern |
|------|-----------------|---------|
| `countdown.led` | ~5 s | 3→2→1→GO green digits, cols 0–11 |
| `level_clear.led` | ~3 s | Expand from (3,6) to full 6×12 |
| `level_fail.led` | ~2 s | Full ON → flicker → collapse → off |

Audio: `games/audio/transition_stinger.mp3` (shared clear+fail).
