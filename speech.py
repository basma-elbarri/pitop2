"""Text-to-speech (Piper if configured, otherwise espeak-ng) and meme sound effects."""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
import time

from config import cfg

log = logging.getLogger("speech")

SOUND_NAMES = ("vine_boom", "bruh", "sad_trombone", "airhorn", "rimshot", "wow")


class Speaker:
    def __init__(self):
        self._procs = []
        self.engine = "none"
        if cfg.PIPER_MODEL and shutil.which(cfg.PIPER_BIN) and shutil.which("aplay"):
            self.engine = "piper"
        elif shutil.which("espeak-ng"):
            self.engine = "espeak"
        log.info("TTS engine: %s", self.engine)

    @staticmethod
    def _clean(text):
        text = re.sub(r"[\x00-\x1f]", " ", str(text))
        return text.strip()[:400]

    async def say(self, text):
        text = self._clean(text)
        if text:
            await asyncio.to_thread(self._say_blocking, text)

    def _say_blocking(self, text):
        try:
            if self.engine == "piper":
                p1 = subprocess.Popen([cfg.PIPER_BIN, "--model", cfg.PIPER_MODEL, "--output-raw"],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
                p2 = subprocess.Popen(["aplay", "-q", "-r", str(cfg.PIPER_RATE), "-f", "S16_LE", "-t", "raw", "-"],
                                      stdin=p1.stdout, stderr=subprocess.DEVNULL)
                p1.stdout.close()
                self._procs = [p1, p2]
                p1.stdin.write(text.encode("utf-8"))
                p1.stdin.close()
                p2.wait()
            elif self.engine == "espeak":
                p = subprocess.Popen(["espeak-ng", "-v", cfg.ESPEAK_VOICE, "-s", "165", text],
                                     stderr=subprocess.DEVNULL)
                self._procs = [p]
                p.wait()
            else:
                log.warning("No TTS engine installed. Robot says: %s", text)
                time.sleep(min(6.0, len(text) * 0.05))  # keep the eye animation realistic
        except Exception:  # noqa: BLE001
            log.exception("TTS failed")
        finally:
            self._procs = []

    def stop(self):
        for p in list(self._procs):
            try:
                p.terminate()
            except Exception:  # noqa: BLE001
                pass


class SoundBoard:
    """Meme sounds. A global cooldown keeps them occasional instead of constant."""

    def __init__(self):
        self._last = 0.0

    def available(self, name):
        return name in SOUND_NAMES and (cfg.SOUNDS_DIR / f"{name}.wav").exists()

    def maybe_play(self, name, force=False):
        if not name or name not in SOUND_NAMES:
            return False
        now = time.monotonic()
        if not force and now - self._last < cfg.SOUND_COOLDOWN_S:
            return False
        if not self.available(name) or not shutil.which("aplay"):
            return False
        self._last = now
        subprocess.Popen(["aplay", "-q", str(cfg.SOUNDS_DIR / f"{name}.wav")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
