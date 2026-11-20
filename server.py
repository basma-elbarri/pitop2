"""Web server: serves the two phone pages, the live camera stream and the WebSocket link."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse, Response

from config import BASE_DIR, cfg

log = logging.getLogger("server")
WEB = BASE_DIR / "web"


class Hub:
    def __init__(self):
        self.clients = {"controller": [], "face": []}

    async def broadcast(self, msg):
        for role in self.clients:
            for ws in list(self.clients[role]):
                try:
                    await ws.send_json(msg)
                except Exception:  # noqa: BLE001
                    if ws in self.clients[role]:
                        self.clients[role].remove(ws)


def create_app(robot):
    app = FastAPI(title="pi-top robot")
    hub = Hub()

    @app.on_event("startup")
    async def _startup():
        robot.start(asyncio.get_running_loop())
        app.state.pump = asyncio.ensure_future(_pump())
        app.state.sensors = asyncio.ensure_future(_sensor_loop())

    @app.on_event("shutdown")
    async def _shutdown():
        robot.shutdown()

    async def _pump():
        while True:
            msg = await robot.bus.queue.get()
            await hub.broadcast(msg)

    async def _sensor_loop():
        while True:
            await hub.broadcast({"type": "sensors", **robot.snapshot()})
            await asyncio.sleep(0.25)

    @app.get("/")
    async def controller_page():
        return FileResponse(WEB / "controller.html")

    @app.get("/face")
    async def face_page():
        return FileResponse(WEB / "face.html")

    @app.get("/video")
    async def video():
        async def gen():
            last = None
            while True:
                jpg = robot.camera.get_jpeg()
                if jpg is not None and jpg is not last:
                    last = jpg
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                await asyncio.sleep(1.0 / cfg.STREAM_FPS)
        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.get("/favicon.ico")
    async def favicon():
        return Response(status_code=204)

    @app.websocket("/ws/{role}")
    async def ws_endpoint(websocket: WebSocket, role: str):
        if role not in hub.clients:
            await websocket.close()
            return
        await websocket.accept()
        hub.clients[role].append(websocket)
        log.info("%s connected", role)
        try:
            await websocket.send_json({"type": "hello", **robot.snapshot()})
            while True:
                text = await websocket.receive_text()
                try:
                    msg = json.loads(text)
                    if not isinstance(msg, dict):
                        continue
                except ValueError:
                    continue
                await robot.handle_message(role, msg)
        except WebSocketDisconnect:
            pass
        except Exception:  # noqa: BLE001
            log.exception("websocket error")
        finally:
            if websocket in hub.clients[role]:
                hub.clients[role].remove(websocket)
            log.info("%s disconnected", role)
            if role == "controller" and not hub.clients["controller"]:
                # connection lost: the robot must not keep doing what it was told
                robot.motors.stop()

    return app
