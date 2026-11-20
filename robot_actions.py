"""The ONLY way anything (joystick, voice, AI) makes the robot move.

The AI can request an action from a fixed allowlist. Everything is validated, clamped to the speed
limits in config.py, and passed through the safety rules below. The AI cannot choose speeds, and
there is no path from AI text to Python/shell execution.
"""
from __future__ import annotations

import logging
import time

from config import cfg

log = logging.getLogger("actions")


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


MOVE_DIRECTIONS = ("forward", "backward", "left", "right")
LOOK_DIRECTIONS = ("up", "down", "left", "right", "center", "at_me")
ALLOWED_TYPES = ("move", "stop", "look", "come_closer", "follow_me", "stop_following", "auto_mode", "manual_mode")


class RobotActions:
    def __init__(self, robot):
        self.r = robot
        self.following = False
        self._follow_until = None
        self._follow_seen = 0.0

    # ----------------------------------------------------------- safe driving
    def _safe_drive(self, left, right, ttl):
        """Apply the safety rules to a requested wheel command, then send it."""
        saf = self.r.safety
        fwd = (left + right) / 2.0
        rot = (right - left) / 2.0
        if fwd > 0:
            if saf.blocked:
                fwd = 0.0                      # blocked: rotating is still allowed, driving ahead is not
            elif saf.min_cm is not None:
                span = max(1.0, cfg.SLOW_CM - cfg.STOP_CM)
                fwd *= _clamp((saf.min_cm - cfg.STOP_CM) / span, 0.35, 1.0)   # slow down when close
        elif fwd < 0:
            fwd = max(fwd, -cfg.REVERSE_MAX_SPEED)  # no rear sensors: reverse slowly
        left, right = fwd - rot, fwd + rot
        self.r.motors.drive(left, right, ttl)

    def drive_manual(self, x, y):
        """Joystick: x right+, y forward+, both -1..1."""
        x, y = _clamp(x, -1, 1), _clamp(y, -1, 1)
        if x == 0 and y == 0:
            if self.r.mode == "manual":
                self.r.motors.stop()
            return
        if self.r.mode == "auto":
            self.r.set_mode("manual")           # touching the stick takes over from autonomous mode
        if self.following:
            self.stop_following()
        left, right = y + x, y - x
        m = max(1.0, abs(left), abs(right))
        left, right = left / m * cfg.MANUAL_MAX_SPEED, right / m * cfg.MANUAL_MAX_SPEED
        self._safe_drive(left, right, cfg.JOYSTICK_TTL_S)

    def camera_rate(self, dpan, dtilt):
        k = cfg.CAMERA_RATE_DEG
        self.r.servos.nudge(_clamp(dpan, -1, 1) * k, _clamp(dtilt, -1, 1) * k)

    def stop(self):
        """Full stop: motors, following, and autonomous mode."""
        self.stop_following()
        self.r.set_mode("manual")
        self.r.motors.stop()

    # ---------------------------------------------------------------- follow
    def start_follow(self, limit_s=None):
        self.following = True
        self._follow_until = time.monotonic() + limit_s if limit_s else None
        self._follow_seen = time.monotonic()
        self.r.tracker.enabled = True
        if self.r.mode == "auto":
            self.r.set_mode("manual")
            self.r.tracker.enabled = True
        self.r.bus.emit("following", on=True)

    def stop_following(self):
        if self.following:
            self.following = False
            self.r.motors.stop()
            self.r.tracker.enabled = self.r.tracking or self.r.mode == "auto"
            self.r.bus.emit("following", on=False)

    def follow_step(self, info):
        """Called by the tracker thread every frame while following."""
        if not self.following:
            return
        now = time.monotonic()
        if self._follow_until and now > self._follow_until:
            self.stop_following()
            return
        if info.get("present"):
            self._follow_seen = now
        elif now - self._follow_seen > cfg.FOLLOW_LOST_S:
            self.stop_following()
            return
        else:
            self.r.motors.stop()
            return
        pan = self.r.servos.pan
        if abs(pan) > cfg.FOLLOW_TURN_PAN_DEG:
            t = cfg.VOICE_TURN_SPEED * (1 if pan > 0 else -1)   # person is to the right -> turn right
            self._safe_drive(t, -t, 0.4)
        elif info.get("size", 0) < cfg.FOLLOW_TARGET_SIZE:
            self._safe_drive(cfg.FOLLOW_SPEED, cfg.FOLLOW_SPEED, 0.4)
        else:
            self.r.motors.stop()
            if self._follow_until:               # "come closer" is finished once we're close
                self.stop_following()

    # ------------------------------------------------------- AI / voice entry
    def execute(self, action):
        """Validate and run an action dict from the AI or the voice parser."""
        if not isinstance(action, dict):
            return {"ok": False, "msg": "no action"}
        kind = action.get("type")
        if kind not in ALLOWED_TYPES:
            log.warning("Rejected unknown action type: %r", kind)
            return {"ok": False, "msg": "unknown action"}
        try:
            if kind == "stop":
                self.stop()
            elif kind == "move":
                d = action.get("direction")
                if d not in MOVE_DIRECTIONS:
                    return {"ok": False, "msg": "bad direction"}
                try:
                    dur = float(action.get("duration", 1.0))
                except (TypeError, ValueError):
                    dur = 1.0
                dur = _clamp(dur, 0.2, cfg.VOICE_MAX_MOVE_S)
                self.r.set_mode("manual")
                self.stop_following()
                v, t = cfg.VOICE_SPEED, cfg.VOICE_TURN_SPEED
                wheels = {"forward": (v, v), "backward": (-v, -v), "left": (-t, t), "right": (t, -t)}[d]
                self._safe_drive(wheels[0], wheels[1], dur)
            elif kind == "look":
                d = action.get("direction")
                if d not in LOOK_DIRECTIONS:
                    return {"ok": False, "msg": "bad direction"}
                s = self.r.servos
                if d == "up":
                    s.move_to(tilt=s.tilt + 20)
                elif d == "down":
                    s.move_to(tilt=s.tilt - 20)
                elif d == "left":
                    s.move_to(pan=s.pan - 30)
                elif d == "right":
                    s.move_to(pan=s.pan + 30)
                elif d == "center":
                    s.center()
                elif d == "at_me":
                    self.r.tracker.enable_for(20.0)
            elif kind == "come_closer":
                self.start_follow(limit_s=5.0)
            elif kind == "follow_me":
                self.start_follow()
            elif kind == "stop_following":
                self.stop_following()
            elif kind == "auto_mode":
                self.stop_following()
                self.r.set_mode("auto")
            elif kind == "manual_mode":
                self.stop_following()
                self.r.set_mode("manual")
            return {"ok": True, "msg": kind}
        except Exception:  # noqa: BLE001
            log.exception("action failed")
            self.r.motors.stop()
            return {"ok": False, "msg": "error"}
