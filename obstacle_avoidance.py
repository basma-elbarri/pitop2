"""The safety layer. Runs in its own thread, never touches the network or the AI, and has the final say:

  * blocks / cancels forward motion when something is closer than STOP_CM (or sensors are dead)
  * enforces the time-to-live of every motor command (watchdog)
  * in AUTO mode, wanders around and steers away from obstacles
"""
from __future__ import annotations

import logging
import random
import threading
import time

from config import cfg

log = logging.getLogger("safety")


class SafetyController(threading.Thread):
    def __init__(self, motors, sensors, on_event=None):
        super().__init__(daemon=True, name="safety")
        self.motors = motors
        self.sensors = sensors
        self.on_event = on_event
        self._halt = threading.Event()
        self.auto = False
        self._paused = False
        self.left_cm = None
        self.right_cm = None
        self.min_cm = None
        self.blocked = False
        self.fault = False
        self._bad = 0
        self._last_event = 0.0
        self._state = "cruise"
        self._until = 0.0
        self._turn_dir = 1

    # ---------------------------------------------------------------- control
    def set_auto(self, on):
        self.auto = bool(on)
        self._state = "cruise"
        self.motors.stop()

    @property
    def paused(self):
        return self._paused

    @paused.setter
    def paused(self, value):
        value = bool(value)
        if value and not self._paused:
            self.motors.stop()
        self._paused = value

    def shutdown(self):
        self._halt.set()
        self.motors.stop()

    # ------------------------------------------------------------------- loop
    def run(self):
        period = 1.0 / cfg.SAFETY_HZ
        while not self._halt.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                log.exception("safety tick crashed - stopping motors")
                self.motors.stop()
            time.sleep(period)

    def tick(self):
        now = time.monotonic()
        left, right = self.sensors.read()
        self.left_cm, self.right_cm = left, right
        vals = [v for v in (left, right) if v is not None]
        self._bad = 0 if vals else self._bad + 1
        self.fault = self._bad >= cfg.SENSOR_FAULT_TICKS
        self.min_cm = min(vals) if vals else None
        self.blocked = self.fault or (self.min_cm is not None and self.min_cm < cfg.STOP_CM)

        if self.blocked and self.motors.forward_component > 0.02:
            self.motors.stop()
            self._emit("obstacle", now, cm=self.min_cm, fault=self.fault)

        self.motors.tick()  # time-to-live watchdog

        if self.auto and not self._paused:
            self._auto_step(now)

    def _emit(self, kind, now, **data):
        if self.on_event and now - self._last_event > 2.0:
            self._last_event = now
            self.on_event(kind, **data)

    # --------------------------------------------------------- autonomous mode
    def _auto_step(self, now):
        if self._state == "cruise":
            if self.blocked:
                self.motors.stop()
                self._state = "reverse"
                self._until = now + 0.6
                self._emit("obstacle", now, cm=self.min_cm, fault=self.fault)
                return
            span = max(1.0, cfg.SLOW_CM - cfg.STOP_CM)
            ratio = (self.min_cm - cfg.STOP_CM) / span if self.min_cm is not None else 0.4
            speed = cfg.AUTO_SPEED * max(0.4, min(1.0, ratio))
            self.motors.drive(speed, speed, ttl=0.3)
        elif self._state == "reverse":
            s = -cfg.REVERSE_MAX_SPEED
            self.motors.drive(s, s, ttl=0.3)
            if now >= self._until:
                lc = self.left_cm if self.left_cm is not None else 0
                rc = self.right_cm if self.right_cm is not None else 0
                if abs(lc - rc) > 5:
                    self._turn_dir = -1 if lc > rc else 1   # turn toward the side with more room
                else:
                    self._turn_dir = random.choice((-1, 1))
                self._state = "turn"
                self._until = now + random.uniform(0.5, 1.0)
        elif self._state == "turn":
            t = cfg.VOICE_TURN_SPEED * self._turn_dir   # +1 = right turn
            self.motors.drive(t, -t, ttl=0.3)
            if now >= self._until:
                self._state = "cruise"
