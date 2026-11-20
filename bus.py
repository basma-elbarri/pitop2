"""Thread-safe bridge: hardware threads emit events, the asyncio server broadcasts them to the phones."""
from __future__ import annotations

import asyncio


class Bus:
    def __init__(self):
        self.loop = None
        self.queue = None

    def bind(self, loop):
        self.loop = loop
        self.queue = asyncio.Queue(maxsize=500)

    def emit(self, type_, **data):
        if self.loop is None:
            return
        self.loop.call_soon_threadsafe(self._put, {"type": type_, **data})

    def _put(self, msg):
        try:
            self.queue.put_nowait(msg)
        except asyncio.QueueFull:
            pass  # dropping a UI event is fine

    def run(self, coro):
        """Schedule a coroutine on the server loop from any thread."""
        if self.loop is None:
            coro.close()
            return
        asyncio.run_coroutine_threadsafe(coro, self.loop)
