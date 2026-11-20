"""Camera pan/tilt servos. Angles are kept in the ROBOT frame: pan + = right, tilt + = up.
PAN_SIGN / TILT_SIGN / *_OFFSET in config.py map that to the physical servo."""
from __future__ import annotations

import logging
import threading

from config import cfg

log = logging.getLogger("servos")


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class ServoController:
    def __init__(self):
        self._lock = threading.Lock()
        self.pan = 0.0
        self.tilt = 0.0
        self._pan_servo = None
        self._tilt_servo = None
        if not cfg.SIMULATE:
            try:
                from pitop import ServoMotor
                self._pan_servo = ServoMotor(cfg.SERVO_PAN_PORT)
                self._tilt_servo = ServoMotor(cfg.SERVO_TILT_PORT)
            except Exception as exc:  # noqa: BLE001
                log.error("Servo init failed (%s). Running with SIMULATED servos!", exc)
        self.center()

    def _apply(self):
        if self._pan_servo is None:
            return
        try:
            self._pan_servo.target_angle = _clamp(cfg.PAN_SIGN * self.pan + cfg.PAN_OFFSET, -90, 90)
            self._tilt_servo.target_angle = _clamp(cfg.TILT_SIGN * self.tilt + cfg.TILT_OFFSET, -90, 90)
        except Exception as exc:  # noqa: BLE001
            log.error("servo command failed: %s", exc)

    def move_to(self, pan=None, tilt=None):
        with self._lock:
            if pan is not None:
                self.pan = _clamp(pan, *cfg.PAN_LIMITS)
            if tilt is not None:
                self.tilt = _clamp(tilt, *cfg.TILT_LIMITS)
            self._apply()

    def nudge(self, dpan=0.0, dtilt=0.0):
        with self._lock:
            self.pan = _clamp(self.pan + dpan, *cfg.PAN_LIMITS)
            self.tilt = _clamp(self.tilt + dtilt, *cfg.TILT_LIMITS)
            self._apply()

    def center(self):
        self.move_to(0.0, 0.0)
