#!/usr/bin/env python3
import numpy as np
from multiprocessing import shared_memory
import asyncio
import struct
import logging
from aiohttp import web, WSCloseCode

logging.basicConfig(level=logging.INFO)
MAGIC = b"FRAM"

WIDTH = 320
HEIGHT = 240
BPP = 16
FPS = 60
SHM_NAME = "headless_fb"

# Attach to shared memory
shm = shared_memory.SharedMemory(name=SHM_NAME)
fb = np.ndarray((HEIGHT, WIDTH), dtype=np.uint16, buffer=shm.buf)

# Frame source
class FrameSourceHeadless:
    def __init__(self, fb_array):
        self.fb = fb_array
        self.width = fb_array.shape[1]
        self.height = fb_array.shape[0]
        self.bpp = BPP
        self.frame_size = self.width * self.height * (self.bpp // 8)

    def read_frame(self):
        return self.fb.tobytes()

    def close(self):
        shm.close()

# WebSocket server
class RGB565Server:
    def __init__(self, frame_source, fps):
        self.frame_source = frame_source
        self.fps = fps
        self.clients = set()
        self.header_struct = struct.Struct(">4sHHBBI")
        self.running = True

    async def broadcaster(self):
        interval = 1.0 / self.fps
        logging.info("Broadcaster running at %d FPS", self.fps)
        try:
            while self.running:
                frame = self.frame_source.read_frame()
                header = self.header_struct.pack(
                    MAGIC,
                    self.frame_source.width,
                    self.frame_source.height,
                    self.frame_source.bpp,
                    0,
                    len(frame)
                )
                msg = header + frame
                dead = []
                for ws in self.clients:
                    try:
                        await ws.send_bytes(msg)
                    except Exception:
                        dead.append(ws)
                for ws in dead:
                    self.clients.discard(ws)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logging.info("Broadcaster cancelled")

    async def ws_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.clients.add(ws)
        logging.info("Client connected: %s", request.remote)
        try:
            async for _ in ws:
                pass
        finally:
            self.clients.discard(ws)
            await ws.close(code=WSCloseCode.GOING_AWAY, message=b"Server shutdown")
            logging.info("Client disconnected: %s", request.remote)
        return ws

async def init_app(host, port, frame_source, fps):
    server = RGB565Server(frame_source, fps)
    app = web.Application()
    app.add_routes([web.get("/", server.ws_handler)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    broadcaster_task = asyncio.create_task(server.broadcaster())
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        broadcaster_task.cancel()
        await broadcaster_task
        frame_source.close()

if __name__ == "__main__":
    fs = FrameSourceHeadless(fb)
    try:
        asyncio.run(init_app("0.0.0.0", 8765, fs, FPS))
    except KeyboardInterrupt:
        logging.info("Shutdown requested")
