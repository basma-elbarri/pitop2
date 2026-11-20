"""Start the robot:   python3 main.py      (simulation, no hardware:  ROBOT_SIMULATE=1 python3 main.py)"""
from __future__ import annotations

import atexit
import logging
import socket

import uvicorn

from config import cfg
from robot import Robot
from server import create_app


def _local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    robot = Robot()
    atexit.register(robot.motors.stop)      # last line of defence if Python exits unexpectedly
    app = create_app(robot)

    ssl_args = {}
    scheme = "http"
    if cfg.CERT_FILE.exists() and cfg.KEY_FILE.exists():
        ssl_args = {"ssl_certfile": str(cfg.CERT_FILE), "ssl_keyfile": str(cfg.KEY_FILE)}
        scheme = "https"

    ip = _local_ip()
    print("\n" + "=" * 60)
    print(f"  Phone 1 (controller):  {scheme}://{ip}:{cfg.PORT}/")
    print(f"  Phone 2 (robot face):  {scheme}://{ip}:{cfg.PORT}/face")
    if scheme == "http":
        print("  NOTE: microphone on Phone 2 needs HTTPS (see README, 'Microphone').")
    print("=" * 60 + "\n")

    uvicorn.run(app, host=cfg.HOST, port=cfg.PORT, log_level="warning", **ssl_args)


if __name__ == "__main__":
    main()
