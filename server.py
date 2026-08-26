#!/usr/bin/env python3
"""
Memory Box server — serves the Netflix-style UI and streams the tuning knob to it.

    python3 server.py                 # knob if GPIO is present, keyboard if not
    python3 server.py --port 8080
    python3 server.py --kiosk         # also launch Chromium fullscreen on the Pi

The browser holds an EventSource on /events; every detent and press of the
KY-040 is pushed down that stream as JSON. On a Mac there's no GPIO, so it
just serves the files and you drive it with the arrow keys.
"""

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

UI_DIR = Path(__file__).resolve().parent / "ui"

PIN_CLK = 17            # KY-040 CLK -> header pin 11
PIN_DT = 18             # KY-040 DT  -> header pin 12
PIN_SW = 27             # KY-040 SW  -> header pin 13

STEPS_PER_DETENT = 1    # raise to 2 or 4 if one click of the knob jumps several tiles
HOLD_SECONDS = 2.0

_clients = []
_clients_lock = threading.Lock()


def broadcast(event: dict):
    dead = []
    with _clients_lock:
        for q in _clients:
            try:
                q.put_nowait(event)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _clients.remove(q)


# ---------------------------------------------------------------- knob
class Knob:
    """KY-040 -> broadcast(). No-op if gpiozero/GPIO isn't available."""

    def __init__(self):
        try:
            from gpiozero import Button, RotaryEncoder
        except Exception as e:
            print(f"[knob] no GPIO ({e}) — keyboard only", flush=True)
            self.ok = False
            return

        self.ok = True
        self._accum = 0
        self._held = False

        self.enc = RotaryEncoder(PIN_CLK, PIN_DT, max_steps=0)
        self._last = self.enc.steps
        self.enc.when_rotated = self._rotated

        self.btn = Button(PIN_SW, pull_up=True, bounce_time=0.05,
                          hold_time=HOLD_SECONDS)
        self.btn.when_held = self._held_cb
        self.btn.when_released = self._released
        print("[knob] KY-040 live on GPIO 17/18/27", flush=True)

    def _rotated(self):
        delta = self.enc.steps - self._last
        self._last = self.enc.steps
        self._accum += delta
        while abs(self._accum) >= STEPS_PER_DETENT:
            step = 1 if self._accum > 0 else -1
            self._accum -= step * STEPS_PER_DETENT
            broadcast({"type": "rotate", "delta": step})

    def _held_cb(self):
        self._held = True
        broadcast({"type": "hold"})

    def _released(self):
        if self._held:
            self._held = False
            return
        broadcast({"type": "press"})


# ---------------------------------------------------------------- http
class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"   # keep-alive, so seeking doesn't reopen a socket per jump

    def log_message(self, *a):
        pass  # quiet

    def end_headers(self):
        # the Pi runs this offline off an SD card; never cache stale UI files
        self.send_header("Cache-Control", "no-store")
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def do_GET(self):
        if self.path.startswith("/events"):
            return self.sse()
        if self.headers.get("Range"):
            return self.ranged()
        return super().do_GET()

    def ranged(self):
        """Byte-range replies. Without these the browser can't seek inside a
        20-minute game film — the knob-scrub would just stall."""
        path = self.translate_path(self.path.split("?", 1)[0])
        if not os.path.isfile(path):
            return super().do_GET()

        size = os.path.getsize(path)
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers["Range"].strip())
        if not m:
            return super().do_GET()

        first, last = m.group(1), m.group(2)
        if first == "":                       # suffix range: last N bytes
            start, end = max(0, size - int(last or 0)), size - 1
        else:
            start = int(first)
            end = int(last) if last else size - 1
        end = min(end, size - 1)
        if start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return

        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()

        remaining = end - start + 1
        try:
            with open(path, "rb") as f:
                f.seek(start)
                while remaining > 0:
                    chunk = f.read(min(256 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # browser seeked again and dropped this response — normal

    def sse(self):
        q = queue.Queue(maxsize=64)
        with _clients_lock:
            _clients.append(q)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")   # open-ended body, no Content-Length
        self.close_connection = True
        self.end_headers()
        try:
            while True:
                try:
                    ev = q.get(timeout=15)
                    payload = f"data: {json.dumps(ev)}\n\n"
                except queue.Empty:
                    payload = ": ping\n\n"          # keeps the socket honest
                self.wfile.write(payload.encode())
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with _clients_lock:
                if q in _clients:
                    _clients.remove(q)


def launch_kiosk(port):
    for exe in ("chromium-browser", "chromium", "chromium-browser-stable"):
        if subprocess.run(["which", exe], capture_output=True).returncode == 0:
            cmd = [
                exe,
                "--kiosk", f"http://localhost:{port}/",
                "--noerrdialogs", "--disable-infobars",
                "--disable-session-crashed-bubble",
                "--check-for-update-interval=31536000",
                # Without this the attract loop and the hover previews never
                # start — Chromium blocks autoplay until someone clicks, and
                # nobody ever clicks a radio.
                "--autoplay-policy=no-user-gesture-required",
                "--start-fullscreen",
            ]
            # Pi OS Bookworm runs Wayland (wayfire), not X11. Left alone,
            # Chromium starts under XWayland — it works, but it's a second
            # compositor's worth of overhead and it tears on video. Ask for
            # native Wayland when that's what we're on, and stay on X11 when
            # we're not, so this still runs on a Bullseye card.
            if os.environ.get("WAYLAND_DISPLAY"):
                cmd.insert(1, "--ozone-platform=wayland")
            subprocess.Popen(cmd)
            return
    print("[kiosk] chromium not found", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--kiosk", action="store_true")
    args = ap.parse_args()

    os.chdir(UI_DIR)
    Knob()

    srv = ThreadingHTTPServer(("0.0.0.0", args.port),
                              partial(Handler, directory=str(UI_DIR)))
    srv.daemon_threads = True
    print(f"[http] serving {UI_DIR} on http://localhost:{args.port}/", flush=True)

    if args.kiosk:
        threading.Thread(target=lambda: (time.sleep(1.5), launch_kiosk(args.port)),
                         daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
