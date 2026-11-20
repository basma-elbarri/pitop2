# pi-top AI Robot

A modular robot controller for a pi-top [4] with two phones: Phone 1 is the remote, Phone 2 is the animated face.
**This code has been run in simulation only. It has not been tested on real pi-top hardware**, so follow the
staged test plan below and fix the config as you go.

## Layout

| File | Job |
|---|---|
| `main.py` | starts everything, prints the phone URLs |
| `config.py` | every port, speed, limit and AI setting |
| `robot.py` | wires modules together, owns mode/voice/tracking state |
| `motor_controller.py`, `servo_controller.py`, `ultrasonic.py` | hardware, each with a simulation fallback |
| `obstacle_avoidance.py` | safety thread: obstacle stop, watchdog, autonomous wandering. Independent of the AI. |
| `robot_actions.py` | the only gate to motion: allowlist, validation, speed limits |
| `camera.py`, `face_tracking.py` | camera thread, OpenCV Haar face detection, nearest-face tracking |
| `speech.py` | text-to-speech (Piper or espeak-ng) and meme sounds with a cooldown |
| `ai_assistant.py`, `conversation.py` | cloud LLM with offline keyword fallback, conversation flow |
| `server.py`, `bus.py` | FastAPI server, WebSocket link, video stream |
| `web/controller.html`, `web/face.html` | Phone 1 and Phone 2 pages |
| `tools/` | hardware tests, placeholder sounds, certificate script |

## Install (on the pi-top)

```bash
sudo apt update
sudo apt install -y python3-opencv opencv-data python3-venv espeak-ng alsa-utils openssl
cd pitop-robot
python3 -m venv --system-site-packages venv     # keeps the system pitop SDK and OpenCV visible
. venv/bin/activate
pip install -r requirements.txt
python3 tools/make_placeholder_sounds.py
```

## Run

```bash
ROBOT_SIMULATE=1 python3 main.py     # no hardware needed: try the UI first
python3 main.py                      # real robot
```

Open the printed URLs: Phone 1 `http://<ip>:8000/`, Phone 2 `http://<ip>:8000/face`.

Cloud AI (optional): `export LLM_API_KEY=...` (and `LLM_BASE_URL`, `LLM_MODEL` if you use another provider).
Without a key the robot uses the offline keyword brain.

### Microphone (Phone 2)

Browsers only allow the microphone on HTTPS. Run `sh tools/make_cert.sh` once, restart `main.py`, and open
`https://<ip>:8000/face` on Phone 2, accepting the certificate warning. Speech recognition in Chrome sends audio to
Google, so it needs internet. Without internet, drive and tracking still work; voice does not.

Better voice: install Piper, download a voice, and set `PIPER_MODEL=/path/voice.onnx`. Otherwise espeak-ng is used.
Real meme sounds: put your own `vine_boom.wav`, `bruh.wav`, `sad_trombone.wav`, `airhorn.wav`, `rimshot.wav`, `wow.wav` in `sounds/`.

## Staged test plan (do these in order, do not skip ahead)

1. **Phone 1 connects.** Simulation mode, open `/`. Pass: green dot, "connected", mode pills update.
2. **Motors.** `python3 tools/hardware_test.py motors` with wheels lifted. Pass: both wheels spin the same way for forward. Fix with `*_FORWARD_CLOCKWISE`. If it errors on `set_power`, send me the traceback.
3. **Camera servos.** `tools/hardware_test.py servos`. Pass: right/up for positive. Else flip `PAN_SIGN`/`TILT_SIGN`.
4. **Eyes on Phone 2.** Open `/face`, tap. Pass: blinking and idle looking. From Phone 1 toggle Voice and Face track to see expressions change.
5. **Phone 2 link.** Pass: the dot in the corner of `/face` is green.
6. **Speech.** `tools/hardware_test.py audio`; then enable Voice and speak on Phone 2. Pass: the robot answers aloud.
7. **AI.** Set `LLM_API_KEY`. Pass: Phone 1 info line says "brain: cloud" and answers are more natural than the canned ones.
8. **Voice movement.** Wheels lifted first. Say "move forward", "turn left", "stop". Pass: it moves briefly, and "stop" halts immediately.
9. **Face tracking.** `tools/hardware_test.py faces`, then press Face track. Pass: camera follows the nearest face. If it moves the wrong way, flip `PAN_SIGN`/`TILT_SIGN`.
10. **Obstacles.** `tools/hardware_test.py sensors`, then drive at a wall slowly. Pass: it stops before `STOP_CM`. Unplug a sensor: forward must be blocked.
11. **Everything together.** Auto mode on the floor, open space, hand on the STOP button.

## Safety design

- Every motor command expires after about half a second unless refreshed, so a lost Wi-Fi link or crashed AI stops the robot.
- The safety thread cancels forward motion under `STOP_CM`, and treats dead sensors as "blocked".
- The AI can only request actions from a fixed list. It cannot pick speeds, and nothing it says is executed as code.
- Spoken "stop" is handled locally before the AI is consulted. The mic is paused while the robot talks, so use the STOP button then.
- There are no rear sensors: reversing is slow and short. If the Python process is killed with `kill -9`, the motor controller may keep its last command, so always test wheels-up first.

## Things I could not verify (check these first)

- The pi-top SDK calls (`EncoderMotor.set_power`, `ServoMotor.target_angle`, `UltrasonicSensor.distance`, `Battery`) are written from memory of the API. `tools/hardware_test.py` will reveal any mismatch.
- Default ports (`M3`/`M0`, `S1`/`S2`, `D0`/`D1`) are guesses; match them to where you plugged things in.
- Generic DC motors need `MOTOR_BACKEND=gpiozero` plus a driver board and the correct GPIO pins in `config.py`.
- Haar face detection is lightweight but only reliable for frontal, well-lit faces.
