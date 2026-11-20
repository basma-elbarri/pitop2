"""Creates simple PLACEHOLDER beeps in sounds/ so the sound system can be tested.
For the real effect, replace the files with your own clips (same names, 16-bit WAV, e.g. vine_boom.wav).
Use clips you have the right to use. Convert with:  ffmpeg -i clip.mp3 -ar 44100 -ac 1 vine_boom.wav
"""
import math
import os
import struct
import wave

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sounds")
os.makedirs(OUT, exist_ok=True)
RATE = 22050


def tone(name, freq, secs, decay=3.0):
    frames = bytearray()
    for i in range(int(RATE * secs)):
        t = i / RATE
        v = math.sin(2 * math.pi * freq * t) * math.exp(-decay * t) * 0.6
        frames += struct.pack("<h", int(v * 32767))
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))


for n, f, s in (("vine_boom", 55, 1.0), ("bruh", 140, 0.6), ("sad_trombone", 196, 1.2),
                ("airhorn", 440, 0.8), ("rimshot", 330, 0.4), ("wow", 600, 0.5)):
    tone(n, f, s)
print("Placeholder sounds written to", OUT)
