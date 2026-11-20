"""All settings in one place. Every value can be overridden with an environment variable
where noted, but for hardware you will mostly just edit this file."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _e(name, default):
    v = os.environ.get(name)
    if v is None:
        return default
    if isinstance(default, bool):
        return v.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        return int(v)
    if isinstance(default, float):
        return float(v)
    return v


class Config:
    # ---------------------------------------------------------------- general
    ROBOT_NAME = _e("ROBOT_NAME", "Pixel")
    SIMULATE = _e("ROBOT_SIMULATE", False)      # True = run with no hardware at all
    HOST = _e("ROBOT_HOST", "0.0.0.0")
    PORT = _e("ROBOT_PORT", 8000)
    CERT_FILE = BASE_DIR / "certs" / "robot.crt"  # if both exist, HTTPS is used
    KEY_FILE = BASE_DIR / "certs" / "robot.key"

    # ----------------------------------------------------------------- motors
    MOTOR_BACKEND = _e("MOTOR_BACKEND", "pitop")  # "pitop" (encoder motors) or "gpiozero" (DC + driver board)
    LEFT_MOTOR_PORT = "M3"
    RIGHT_MOTOR_PORT = "M0"
    LEFT_FORWARD_CLOCKWISE = True    # flip these if a wheel spins the wrong way
    RIGHT_FORWARD_CLOCKWISE = False
    GPIO_LEFT = (5, 6)               # (forward_pin, backward_pin), BCM numbers, gpiozero backend only
    GPIO_RIGHT = (13, 19)

    # speeds are 0..1 fractions of full power
    MANUAL_MAX_SPEED = 0.7
    AUTO_SPEED = 0.4
    VOICE_SPEED = 0.4
    VOICE_TURN_SPEED = 0.4
    FOLLOW_SPEED = 0.35
    REVERSE_MAX_SPEED = 0.3          # no rear sensors, so reversing is always slow
    VOICE_MAX_MOVE_S = 3.0           # longest single move the AI can request
    JOYSTICK_TTL_S = 0.5             # motors stop by themselves if no new command arrives in this time

    # ------------------------------------------------------------- ultrasonic
    US_LEFT_PORT = "D0"
    US_RIGHT_PORT = "D1"
    STOP_CM = 25.0                   # forward motion is blocked below this distance
    SLOW_CM = 60.0                   # speed ramps down between SLOW_CM and STOP_CM
    SENSOR_FAULT_TICKS = 6           # this many failed reads in a row = treat as blocked
    SAFETY_HZ = 20

    # ----------------------------------------------------------------- servos
    SERVO_PAN_PORT = "S1"
    SERVO_TILT_PORT = "S2"
    PAN_SIGN = 1                     # set to -1 if the camera pans the wrong way
    TILT_SIGN = 1
    PAN_OFFSET = 0.0                 # trim so "0" really is straight ahead
    TILT_OFFSET = 0.0
    PAN_LIMITS = (-80.0, 80.0)       # robot frame: + = right
    TILT_LIMITS = (-35.0, 45.0)      # robot frame: + = up
    CAMERA_RATE_DEG = 3.0            # degrees per 100 ms at full stick deflection

    # ----------------------------------------------------------------- camera
    CAMERA_INDEX = _e("CAMERA_INDEX", 0)
    CAMERA_W = 320
    CAMERA_H = 240
    CAMERA_FPS = 10
    STREAM_FPS = 8
    JPEG_QUALITY = 60

    # ---------------------------------------------------------- face tracking
    TRACK_FPS = 8
    MIN_FACE_PX = 28
    KP_PAN = 7.0                     # degrees of correction per unit of error
    KP_TILT = 5.0
    MAX_STEP_DEG = 4.0
    DEADZONE = 0.07
    LOST_S = 1.5                     # face gone this long = "person disappeared"
    SEARCH_AFTER_S = 3.0             # start sweeping the camera after this long without a face
    SEARCH_STEP_DEG = 1.5
    ARRIVE_FRAMES = 4                # frames in a row before we believe a face is real
    ARRIVE_ABSENT_S = 4.0
    GREET_MIN_SIZE = 0.12            # face width / frame width needed to count as "approached"
    GREET_COOLDOWN_S = 60.0
    FOLLOW_TARGET_SIZE = 0.30        # stop following when the face is this big (close enough)
    FOLLOW_TURN_PAN_DEG = 15.0
    FOLLOW_LOST_S = 6.0

    # ------------------------------------------------------------------ audio
    PIPER_BIN = _e("PIPER_BIN", "piper")
    PIPER_MODEL = _e("PIPER_MODEL", "")          # path to a .onnx voice; empty = use espeak-ng
    PIPER_RATE = 22050
    ESPEAK_VOICE = "en-us"
    SOUNDS_DIR = BASE_DIR / "sounds"
    SOUND_COOLDOWN_S = 45.0          # meme sounds are never closer together than this

    # -------------------------------------------------------------------- LLM
    # Any OpenAI-compatible chat API works (Groq, OpenRouter, Gemini's compat endpoint, a local server...)
    LLM_BASE_URL = _e("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    LLM_API_KEY = _e("LLM_API_KEY", "")          # empty = offline brain only
    LLM_MODEL = _e("LLM_MODEL", "llama-3.1-8b-instant")
    LLM_TIMEOUT = 12.0


cfg = Config()
