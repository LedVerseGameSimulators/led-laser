"""Non-blocking audio for Laser Escape effects + gameplay."""
from __future__ import annotations

import os
import queue
import threading
from pathlib import Path
from loguru import logger

GAMES_ROOT = Path(__file__).resolve().parent.parent / "games"
AUDIO_DIR = GAMES_ROOT / "audio"

# Commands for the worker thread
_CMD_STOP_BGM = "stop_bgm"
_CMD_START_BGM = "start_bgm"
_CMD_PLAY_SFX = "play_sfx"
_CMD_PLAY_STINGER = "play_stinger"
_CMD_SHUTDOWN = "shutdown"


class AudioManager:
    """Fire-and-forget pygame audio on a daemon worker thread."""

    def __init__(self, enabled: bool | None = None):
        self._enabled = enabled
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._mixer = None
        self._started = False
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def _ensure_worker(self):
        if self._started:
            return
        self._started = True
        if self._enabled is False:
            return
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
            self._mixer = pygame.mixer
            self._active = True
        except Exception as e:
            logger.debug(f"AudioManager disabled (pygame unavailable): {e}")
            self._active = False
            return
        self._thread = threading.Thread(target=self._worker, daemon=True, name="laser-audio")
        self._thread.start()

    def _resolve(self, path: str | Path) -> str:
        p = Path(path)
        if not p.is_absolute():
            p = GAMES_ROOT / p if not (GAMES_ROOT / path).exists() else GAMES_ROOT / path
            if not p.exists():
                p = AUDIO_DIR / Path(path).name
        return str(p)

    def _worker(self):
        while True:
            try:
                cmd, payload = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if cmd == _CMD_SHUTDOWN:
                break
            if not self._mixer:
                continue
            try:
                if cmd == _CMD_STOP_BGM:
                    self._mixer.music.stop()
                elif cmd == _CMD_START_BGM:
                    path, loops = payload
                    if Path(path).exists():
                        self._mixer.music.load(path)
                        self._mixer.music.play(loops=loops)
                elif cmd in (_CMD_PLAY_SFX, _CMD_PLAY_STINGER):
                    path = payload
                    if Path(path).exists():
                        snd = self._mixer.Sound(path)
                        snd.play()
            except Exception as e:
                logger.debug(f"Audio worker error ({cmd}): {e}")

    def _put(self, cmd, payload=None):
        self._ensure_worker()
        if not self._active:
            return
        try:
            self._queue.put_nowait((cmd, payload))
        except queue.Full:
            pass

    def start_bgm(self, path: str, loops: int = -1):
        self._put(_CMD_START_BGM, (self._resolve(path), loops))

    def stop_bgm(self):
        self._put(_CMD_STOP_BGM)

    def play_sfx(self, path: str):
        self._put(_CMD_PLAY_SFX, self._resolve(path))

    def play_stinger(self, path: str | None = None):
        p = path or str(AUDIO_DIR / "transition_stinger.mp3")
        self._put(_CMD_PLAY_STINGER, self._resolve(p))

    def tick_on_second(self, n: int):
        self.play_sfx(str(AUDIO_DIR / "countdown_tick.mp3"))

    def shutdown(self):
        if self._thread and self._thread.is_alive():
            self._put(_CMD_SHUTDOWN)
            self._thread.join(timeout=1.0)


def create_audio_manager() -> AudioManager:
    """Real audio when pygame works; no-op otherwise (CI / mocked imports)."""
    if os.environ.get("LASER_AUDIO_DISABLED", "0") == "1":
        return AudioManager(enabled=False)
    try:
        import pygame  # noqa: F401
        return AudioManager(enabled=True)
    except Exception:
        return AudioManager(enabled=False)
