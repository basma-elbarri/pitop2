"""Two ultrasonic distance sensors. read() returns (left_cm, right_cm); None means 'no valid reading'."""
from __future__ import annotations

import logging

from config import cfg

log = logging.getLogger("ultrasonic")


class DistanceSensors:
    def __init__(self):
        self._l = None
        self._r = None
        self.sim_cm = (200.0, 200.0)   # adjustable from the controller page when ROBOT_SIMULATE=1
        if not cfg.SIMULATE:
            try:
                from pitop import UltrasonicSensor
                self._l = UltrasonicSensor(cfg.US_LEFT_PORT)
                self._r = UltrasonicSensor(cfg.US_RIGHT_PORT)
            except Exception as exc:  # noqa: BLE001
                log.error("Ultrasonic init failed (%s). Sensors will report NO DATA, so the robot stays blocked!", exc)

    @staticmethod
    def _one(sensor):
        if sensor is None:
            return None
        try:
            d = sensor.distance  # metres
            if d is None or d != d:  # None or NaN
                return None
            return round(float(d) * 100.0, 1)
        except Exception:  # noqa: BLE001
            return None

    def read(self):
        if cfg.SIMULATE:
            return self.sim_cm
        return self._one(self._l), self._one(self._r)
