"""Wires all modules together and owns the robot's overall state (mode, voice, tracking)."""
from __future__ import annotations

import asyncio
import logging
import os
import time

from ai_assistant import Assistant
from bus import Bus
from camera import Camera
from config import cfg
from conversation import Conversation
from face_tracking import FaceTracker
from motor_controller import MotorController
from obstacle_avoidance import SafetyController
from robot_actions import RobotActions
from servo_controller import ServoController
from speech import SoundBoard, Speaker
from ultrasonic import DistanceSensors

log = logging.getLogger("robot")


def _num(v, lo=-1.0, hi=1.0):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    if v != v:
        return 0.0
    return max(lo, min(hi, v))


class Robot:
    def __init__(self):
        self.bus = Bus()
        self.motors = MotorController()
        self.servos = ServoController()
        self.sensors = DistanceSensors()
        self.safety = SafetyController(self.motors, self.sensors, self._on_safety_event)
        self.camera = Camera()
        self.tracker = FaceTracker(self.camera, self.servos, self._on_track, self._on_arrival)
        self.speaker = Speaker()
        self.sounds = SoundBoard()
        self.assistant = Assistant()
        self.actions = RobotActions(self)
        self.convo = Conversation(self)
        self.mode = "manual"
        self.tracking = False
        self.voice = False
        self.state = "idle"
        self._tasks = set()
        self._last_look = 0.0
        self._battery = (None, None)
        self._battery_t = 0.0
        self._last_obstacle_talk = 0.0

    # --------------------------------------------------------------- lifecycle
    def start(self, loop):
        self.bus.bind(loop)
        self.safety.start()
        self.camera.start()
        self.tracker.start()
        log.info("Robot started (simulate=%s)", cfg.SIMULATE)

    def shutdown(self):
        log.info("Shutting down: stopping motors")
        self.safety.shutdown()
        self.tracker.shutdown()
        self.camera.shutdown()
        self.speaker.stop()
        self.motors.stop()

    # ------------------------------------------------------------------- state
    def set_state(self, state):
        self.state = state
        self.bus.emit("state", state=state)

    def set_mode(self, mode):
        if mode not in ("manual", "auto"):
            return
        self.mode = mode
        if mode == "auto":
            self.actions.stop_following()
            self.tracker.enabled = True
            self.safety.set_auto(True)
        else:
            self.safety.set_auto(False)
            self.safety.paused = False
            self.tracker.enabled = self.tracking or self.actions.following
        self.bus.emit("mode", mode=self.mode)

    def set_tracking(self, on):
        self.tracking = bool(on)
        self.tracker.enabled = self.tracking or self.mode == "auto" or self.actions.following

    def set_voice(self, on):
        self.voice = bool(on)
        self.set_state("listening" if self.voice else "idle")
        self.bus.emit("voice", enabled=self.voice)

    # ------------------------------------------------- callbacks from threads
    def _on_safety_event(self, kind, **data):
        if kind == "obstacle":
            self.bus.emit("expression", name="surprised", hold=2.0)
            now = time.monotonic()
            if self.voice and now - self._last_obstacle_talk > 20:
                self._last_obstacle_talk = now
                self.bus.run(self.convo.react_obstacle())

    def _on_track(self, info):
        if self.mode == "auto":
            self.safety.paused = bool(info["present"]) and not self.actions.following
        if self.actions.following:
            self.actions.follow_step(info)
        now = time.monotonic()
        if now - self._last_look > 0.2:
            self._last_look = now
            self.bus.emit("look", x=info["ex"], y=info["ey"], present=info["present"])
            self.bus.emit("searching", on=info["searching"])

    def _on_arrival(self, size):
        log.info("Person approached (face size %.2f)", size)
        self.bus.run(self.convo.greet())

    # ------------------------------------------------------------ phone input
    async def handle_message(self, role, msg):
        t = msg.get("type")
        if role == "controller":
            if t == "drive":
                self.actions.drive_manual(_num(msg.get("x")), _num(msg.get("y")))
            elif t == "estop":
                self.actions.stop()
            elif t == "camera":
                self.actions.camera_rate(_num(msg.get("dpan")), _num(msg.get("dtilt")))
            elif t == "camera_center":
                self.servos.center()
            elif t == "mode":
                self.set_mode(msg.get("mode"))
            elif t == "tracking":
                self.set_tracking(bool(msg.get("enabled")))
            elif t == "voice":
                self.set_voice(bool(msg.get("enabled")))
            elif t == "sim_distance" and cfg.SIMULATE:
                self.sensors.sim_cm = (_num(msg.get("left"), 0, 400), _num(msg.get("right"), 0, 400))
        elif role == "face":
            if t == "speech_text" and isinstance(msg.get("text"), str):
                task = asyncio.ensure_future(self.convo.on_user_text(msg["text"]))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

    # ---------------------------------------------------------------- snapshot
    def _read_battery(self):
        now = time.monotonic()
        if now - self._battery_t > 10:
            self._battery_t = now
            try:
                from pitop.battery import Battery
                if not hasattr(self, "_bat_obj"):
                    self._bat_obj = Battery()
                self._battery = (self._bat_obj.capacity, self._bat_obj.is_charging)
            except Exception:  # noqa: BLE001
                self._battery = (None, None)
        return self._battery

    @staticmethod
    def _cpu_temp():
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return round(int(f.read().strip()) / 1000.0, 1)
        except Exception:  # noqa: BLE001
            return None

    def snapshot(self):
        cap, charging = self._read_battery()
        try:
            load = round(os.getloadavg()[0], 2)
        except (OSError, AttributeError):
            load = None
        return {
            "left": self.safety.left_cm, "right": self.safety.right_cm,
            "blocked": self.safety.blocked, "fault": self.safety.fault,
            "mode": self.mode, "tracking": self.tracking, "following": self.actions.following,
            "voice": self.voice, "state": self.state,
            "person": self.tracker.present, "pan": round(self.servos.pan, 1), "tilt": round(self.servos.tilt, 1),
            "battery": cap, "charging": charging, "temp": self._cpu_temp(), "load": load,
            "sim": cfg.SIMULATE, "camera": self.camera.real, "brain": "cloud" if self.assistant.online else "offline",
        }
