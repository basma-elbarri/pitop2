"""Wheel motors. Every drive command carries a time-to-live (ttl): when it expires the motors stop
by themselves, so a lost connection or crashed AI can never leave the robot driving."""
from __future__ import annotations

import logging
import threading
import time

from config import cfg

log = logging.getLogger("motors")


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


class _SimBackend:
    name = "sim"

    def set(self, left, right):
        pass

    def stop(self):
        pass


class _PitopBackend:
    """pi-top EncoderMotor on the Foundation/Expansion plate (ports M0-M3)."""
    name = "pitop"

    def __init__(self):
        from pitop import EncoderMotor, ForwardDirection
        fl = ForwardDirection.CLOCKWISE if cfg.LEFT_FORWARD_CLOCKWISE else ForwardDirection.COUNTER_CLOCKWISE
        fr = ForwardDirection.CLOCKWISE if cfg.RIGHT_FORWARD_CLOCKWISE else ForwardDirection.COUNTER_CLOCKWISE
        self.l = EncoderMotor(cfg.LEFT_MOTOR_PORT, fl)
        self.r = EncoderMotor(cfg.RIGHT_MOTOR_PORT, fr)

    def set(self, left, right):
        for m, p in ((self.l, left), (self.r, right)):
            if abs(p) < 0.01:
                m.stop()
            else:
                m.set_power(p)  # signed power -1..1  (verify with tools/hardware_test.py)

    def stop(self):
        self.l.stop()
        self.r.stop()


class _GpioBackend:
    """Generic DC motors through an H-bridge driver (L298N, TB6612...), using gpiozero PWM."""
    name = "gpiozero"

    def __init__(self):
        from gpiozero import Motor
        self.l = Motor(forward=cfg.GPIO_LEFT[0], backward=cfg.GPIO_LEFT[1], pwm=True)
        self.r = Motor(forward=cfg.GPIO_RIGHT[0], backward=cfg.GPIO_RIGHT[1], pwm=True)

    def set(self, left, right):
        self.l.value = left
        self.r.value = right

    def stop(self):
        self.l.stop()
        self.r.stop()


class MotorController:
    def __init__(self):
        self._lock = threading.Lock()
        self.left = 0.0
        self.right = 0.0
        self._deadline = 0.0
        self.backend = _SimBackend()
        if not cfg.SIMULATE:
            try:
                self.backend = _GpioBackend() if cfg.MOTOR_BACKEND == "gpiozero" else _PitopBackend()
            except Exception as exc:  # noqa: BLE001
                log.error("Motor hardware init failed (%s). Running with SIMULATED motors!", exc)
        log.info("Motor backend: %s", self.backend.name)
        self.stop()

    @property
    def forward_component(self):
        return (self.left + self.right) / 2.0

    @property
    def moving(self):
        return abs(self.left) > 0.01 or abs(self.right) > 0.01

    def drive(self, left, right, ttl):
        left = clamp(left, -1.0, 1.0)
        right = clamp(right, -1.0, 1.0)
        with self._lock:
            self.left, self.right = left, right
            self._deadline = time.monotonic() + ttl
            self._apply(left, right)

    def stop(self):
        with self._lock:
            self.left = self.right = 0.0
            self._deadline = 0.0
            try:
                self.backend.stop()
            except Exception as exc:  # noqa: BLE001
                log.error("stop() failed: %s", exc)

    def tick(self):
        """Called by the safety loop: enforces the time-to-live."""
        if self.moving and time.monotonic() > self._deadline:
            self.stop()

    def _apply(self, left, right):
        try:
            self.backend.set(left, right)
        except Exception as exc:  # noqa: BLE001
            log.error("motor command failed: %s", exc)
            try:
                self.backend.stop()
            except Exception:  # noqa: BLE001
                pass
            self.left = self.right = 0.0
