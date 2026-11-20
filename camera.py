"""Camera capture in a background thread. Other modules just ask for the latest frame."""
from __future__ import annotations

import logging
import threading
import time

from config import cfg

log = logging.getLogger("camera")


class Camera(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True, name="camera")
        self._halt = threading.Event()
        self._frame = None
        self._jpeg = None
        self._jpeg_for = None
        self._cv2 = None
        self.real = False

    def run(self):
        try:
            import cv2
        except ImportError:
            log.error("OpenCV (cv2) is not installed - no camera, no face tracking.")
            return
        self._cv2 = cv2
        cap = None
        if not cfg.SIMULATE:
            cap = cv2.VideoCapture(cfg.CAMERA_INDEX)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.CAMERA_W)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.CAMERA_H)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            else:
                log.error("Camera index %s could not be opened; using a placeholder image.", cfg.CAMERA_INDEX)
                cap = None
        self.real = cap is not None
        period = 1.0 / cfg.CAMERA_FPS
        fails = 0
        while not self._halt.is_set():
            t0 = time.monotonic()
            if cap is not None:
                ok, frame = cap.read()
                if not ok:
                    fails += 1
                    if fails > 50:
                        log.error("Camera stopped delivering frames.")
                        self.real = False
                    time.sleep(0.1)
                    continue
                fails = 0
            else:
                frame = self._placeholder()
            self._frame = frame
            time.sleep(max(0.0, period - (time.monotonic() - t0)))
        if cap is not None:
            cap.release()

    def _placeholder(self):
        import numpy as np
        img = np.zeros((cfg.CAMERA_H, cfg.CAMERA_W, 3), dtype=np.uint8)
        img[:] = (40, 30, 20)
        self._cv2.putText(img, "NO CAMERA / SIMULATION", (12, cfg.CAMERA_H // 2),
                          self._cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        self._cv2.putText(img, time.strftime("%H:%M:%S"), (12, cfg.CAMERA_H // 2 + 30),
                          self._cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 200, 120), 1)
        return img

    def get_frame(self):
        return self._frame

    def get_jpeg(self):
        frame = self._frame
        if frame is None or self._cv2 is None:
            return None
        if frame is self._jpeg_for:
            return self._jpeg
        ok, buf = self._cv2.imencode(".jpg", frame, [self._cv2.IMWRITE_JPEG_QUALITY, cfg.JPEG_QUALITY])
        if ok:
            self._jpeg = buf.tobytes()
            self._jpeg_for = frame
        return self._jpeg

    def shutdown(self):
        self._halt.set()
