"""T9 — AudioManager must not block the caller."""
import time

from api.audio_manager import AudioManager


def test_audio_manager_methods_return_immediately():
    am = AudioManager(enabled=False)
    t0 = time.time()
    am.start_bgm("games/audio/bgm_laser.mp3")
    am.stop_bgm()
    am.play_sfx("games/audio/score_positive.mp3")
    am.play_stinger("games/audio/transition_stinger.mp3")
    am.tick_on_second(3)
    elapsed = time.time() - t0
    assert elapsed < 0.5
