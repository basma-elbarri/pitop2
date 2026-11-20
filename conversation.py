"""Conversation flow: heard text -> (instant local stop check) -> AI -> action + eyes + sound + speech."""
from __future__ import annotations

import logging
import random
import re

log = logging.getLogger("convo")

STOP_RE = re.compile(r"\b(stop|halt|freeze|emergency|don'?t move|hold on|wait)\b", re.I)
GREETINGS = [
    "Oh, hello! What brings you here?",
    "Well well, a human! Hi there. Need something?",
    "Hey! I was getting bored. What's up?",
]
OBSTACLE_LINES = ["Whoa, that wall came out of nowhere!", "Nope. Not going through that.", "Excuse me, you're in my way."]


class Conversation:
    def __init__(self, robot):
        self.r = robot
        self.busy = False

    async def _speak(self, text, emotion="normal", sound=None):
        r = self.r
        r.bus.emit("expression", name=emotion, hold=3.0)
        if sound:
            r.sounds.maybe_play(sound)
        r.set_state("speaking")
        await r.speaker.say(text)

    async def say(self, text, emotion="normal", sound=None):
        if self.busy:
            return
        self.busy = True
        try:
            await self._speak(text, emotion, sound)
        finally:
            self.busy = False
            self.r.set_state("listening" if self.r.voice else "idle")

    async def greet(self):
        if self.r.voice and not self.busy:
            await self.say(random.choice(GREETINGS), "happy")

    async def react_obstacle(self):
        if self.r.voice and not self.busy:
            await self.say(random.choice(OBSTACLE_LINES), "surprised", "vine_boom")

    async def on_user_text(self, text):
        r = self.r
        text = (text or "").strip()[:300]
        if not text or not r.voice:
            return
        log.info("Heard: %s", text)
        # Safety first: a spoken stop never waits for the AI and works even if the internet is down.
        if STOP_RE.search(text) and not re.search(r"\bstop (following|looking)\b", text, re.I):
            r.actions.stop()
            r.bus.emit("expression", name="surprised", hold=1.5)
        if self.busy:
            return
        self.busy = True
        try:
            r.set_state("thinking")
            context = (f"mode={r.mode}, nearest obstacle="
                       f"{'unknown' if r.safety.min_cm is None else str(int(r.safety.min_cm)) + 'cm'}, "
                       f"person visible={'yes' if r.tracker.present else 'no'}")
            reply = await r.assistant.ask(text, context)
            if reply.get("action") and reply["action"].get("type") != "stop":
                result = r.actions.execute(reply["action"])
                log.info("Action %s -> %s", reply["action"], result)
            await self._speak(reply["say"], reply["emotion"], reply.get("sound"))
        except Exception:  # noqa: BLE001
            log.exception("conversation error")
            r.motors.stop()
        finally:
            self.busy = False
            r.set_state("listening" if r.voice else "idle")
