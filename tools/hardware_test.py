"""Test each piece of hardware on its own, BEFORE running the full robot.
Run from the project folder:   python3 tools/hardware_test.py <sensors|servos|motors|camera|faces|audio>
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import cfg  # noqa: E402


def sensors():
    from ultrasonic import DistanceSensors
    s = DistanceSensors()
    print("Wave your hand in front of each sensor. Ctrl+C to stop.")
    for _ in range(60):
        print("left %s cm | right %s cm" % s.read())
        time.sleep(0.25)


def servos():
    from servo_controller import ServoController
    s = ServoController()
    print("Pan should go RIGHT for positive angles, tilt UP for positive. If not, flip PAN_SIGN / TILT_SIGN in config.py")
    for name, moves in (("pan", [20, -20, 0]), ("tilt", [15, -15, 0])):
        for a in moves:
            print(name, "->", a)
            s.move_to(**{name: a})
            time.sleep(1.0)
    s.center()


def motors():
    from motor_controller import MotorController
    if input("LIFT THE ROBOT so the wheels spin freely, then type yes: ").strip().lower() != "yes":
        return
    m = MotorController()
    for label, l, r in (("forward", .3, .3), ("backward", -.3, -.3), ("turn right (left wheel fwd)", .3, -.3)):
        print(label)
        m.drive(l, r, 1.2)
        time.sleep(1.4)
        m.stop()
        time.sleep(0.5)
    print("Both wheels must spin the same way for 'forward'. If one is backwards, flip LEFT_/RIGHT_FORWARD_CLOCKWISE in config.py")


def camera():
    import cv2
    cap = cv2.VideoCapture(cfg.CAMERA_INDEX)
    ok, frame = cap.read()
    if not ok:
        print("Could not read a frame. Try CAMERA_INDEX=1 python3 tools/hardware_test.py camera")
        return
    cv2.imwrite("camera_test.jpg", frame)
    print("Saved camera_test.jpg", frame.shape)


def faces():
    import cv2
    from face_tracking import _find_cascade
    path = _find_cascade(cv2)
    print("cascade:", path)
    cap = cv2.VideoCapture(cfg.CAMERA_INDEX)
    casc = cv2.CascadeClassifier(path)
    for _ in range(40):
        ok, frame = cap.read()
        if ok:
            g = cv2.equalizeHist(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
            print("faces:", len(casc.detectMultiScale(g, 1.2, 5, minSize=(cfg.MIN_FACE_PX,) * 2)))
        time.sleep(0.2)


def audio():
    import asyncio
    from speech import Speaker, SoundBoard
    sp = Speaker()
    print("TTS engine:", sp.engine)
    asyncio.run(sp.say("Hello, I am your robot. Testing one two three."))
    sb = SoundBoard()
    for n in ("vine_boom", "rimshot"):
        print(n, "played" if sb.maybe_play(n, force=True) else "missing (run tools/make_placeholder_sounds.py)")
        time.sleep(1.5)


if __name__ == "__main__":
    tests = {"sensors": sensors, "servos": servos, "motors": motors, "camera": camera, "faces": faces, "audio": audio}
    if len(sys.argv) != 2 or sys.argv[1] not in tests:
        print(__doc__)
        sys.exit(1)
    tests[sys.argv[1]]()
