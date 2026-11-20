"""Face detection + camera tracking.

Detector: OpenCV Haar cascade. It ships with OpenCV (no extra downloads), runs fine at 320x240 on a
Pi 4, and is good enough for frontal faces. 'Nearest person' = the largest face box in the frame.

Servo convention (robot frame): pan + = right, tilt + = up.
"""
from __future__ import annotations

import logging
import os
import threading
import time

from config import cfg

log = logging.getLogger("tracking")


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _find_cascade(cv2):
    override = os.environ.get("FACE_CASCADE")
    candidates = [override] if override else []
    if hasattr(cv2, "data"):
        candidates.append(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    candidates += [
        "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml",
        "/usr/share/opencv/haarcascades/haarcascade_frontalface_default.xml",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


class FaceTracker(threading.Thread):
    def __init__(self, camera, servos, on_update=None, on_arrival=None):
        super().__init__(daemon=True, name="tracker")
        self.camera = camera
        self.servos = servos
        self.on_update = on_update
        self.on_arrival = on_arrival
        self._halt = threading.Event()
        self.enabled = False
        self._enabled_until = 0.0
        self.available = True
        self.present = False
        self.searching = False
        self.info = {"present": False, "ex": 0.0, "ey": 0.0, "size": 0.0, "searching": False}
        self._seen = 0
        self._last_seen = -1e9
        self._prev_last_seen = -1e9
        self._last_greet = -1e9
        self._sweep_dir = 1

    def enable_for(self, seconds):
        self._enabled_until = time.monotonic() + seconds

    def active(self):
        return self.enabled or time.monotonic() < self._enabled_until

    def shutdown(self):
        self._halt.set()

    # ------------------------------------------------------------------- loop
    def run(self):
        try:
            import cv2
        except ImportError:
            self.available = False
            log.error("OpenCV missing: face tracking disabled.")
            return
        path = _find_cascade(cv2)
        if not path:
            self.available = False
            log.error("Face cascade file not found. Set FACE_CASCADE=/path/to/haarcascade_frontalface_default.xml")
            return
        cascade = cv2.CascadeClassifier(path)
        period = 1.0 / cfg.TRACK_FPS
        while not self._halt.is_set():
            t0 = time.monotonic()
            try:
                if not self.active():
                    if self.present or self.searching:
                        self.present = self.searching = False
                        self._seen = 0
                        self._publish(0.0, 0.0, 0.0)
                    time.sleep(0.15)
                    continue
                frame = self.camera.get_frame()
                if frame is None:
                    time.sleep(0.1)
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.equalizeHist(gray)
                faces = cascade.detectMultiScale(gray, 1.2, 5, minSize=(cfg.MIN_FACE_PX, cfg.MIN_FACE_PX))
                self._update(faces, gray.shape, t0)
            except Exception:  # noqa: BLE001
                log.exception("tracker error")
                time.sleep(0.5)
            time.sleep(max(0.0, period - (time.monotonic() - t0)))

    def _update(self, faces, shape, now):
        h, w = shape[:2]
        ex = ey = size = 0.0
        if len(faces):
            x, y, fw, fh = max(faces, key=lambda f: f[2] * f[3])   # nearest = biggest
            ex = ((x + fw / 2) / w - 0.5) * 2.0
            ey = ((y + fh / 2) / h - 0.5) * 2.0
            size = fw / w
            self._seen += 1
            if self._seen == 1:
                self._prev_last_seen = self._last_seen
            self._last_seen = now
            self.searching = False
            if not self.present and self._seen >= cfg.ARRIVE_FRAMES:
                self.present = True
                absent_for = now - self._prev_last_seen
                if (absent_for >= cfg.ARRIVE_ABSENT_S and size >= cfg.GREET_MIN_SIZE
                        and now - self._last_greet >= cfg.GREET_COOLDOWN_S):
                    self._last_greet = now
                    if self.on_arrival:
                        self.on_arrival(size)
            if abs(ex) > cfg.DEADZONE:
                self.servos.nudge(dpan=_clamp(cfg.KP_PAN * ex, -cfg.MAX_STEP_DEG, cfg.MAX_STEP_DEG))
            if abs(ey) > cfg.DEADZONE:
                self.servos.nudge(dtilt=_clamp(-cfg.KP_TILT * ey, -cfg.MAX_STEP_DEG, cfg.MAX_STEP_DEG))
        else:
            self._seen = 0
            if self.present and now - self._last_seen > cfg.LOST_S:
                self.present = False
            if not self.present and now - self._last_seen > cfg.SEARCH_AFTER_S:
                self.searching = True
                self._sweep(now)
        self._publish(ex, ey, size)

    def _sweep(self, now):
        lo, hi = cfg.PAN_LIMITS
        if self.servos.pan >= hi - 5:
            self._sweep_dir = -1
        elif self.servos.pan <= lo + 5:
            self._sweep_dir = 1
        self.servos.nudge(dpan=cfg.SEARCH_STEP_DEG * self._sweep_dir)
        self.servos.move_to(tilt=5.0)

    def _publish(self, ex, ey, size):
        self.info = {"present": self.present, "ex": round(ex, 3), "ey": round(ey, 3),
                     "size": round(size, 3), "searching": self.searching}
        if self.on_update:
            self.on_update(self.info)
