#!/usr/bin/env python3
"""
Memory Box player — Magnavox radio build.

Turn the tuning knob  -> tune to the next/previous game (starts playing)
Press the knob        -> pause / resume
Hold the knob (2 sec) -> back to the attract loop (highlights)
Idle for a while      -> back to the attract loop

Video is played by mpv, driven over its JSON IPC socket.
Encoder is read with gpiozero (KY-040 on GPIO 17 / 18 / 27).
"""

import json
import os
import socket
import subprocess
import threading
import time
from pathlib import Path

from gpiozero import Button, RotaryEncoder

# ---------------------------------------------------------------- config
BASE = Path(__file__).resolve().parent
GAMES_FILE = BASE / "games.json"
SOCKET_PATH = "/tmp/mpv-memorybox.sock"

PIN_CLK = 17          # KY-040 CLK -> header pin 11
PIN_DT = 18           # KY-040 DT  -> header pin 12
PIN_SW = 27           # KY-040 SW  -> header pin 13

STEPS_PER_DETENT = 1  # bump to 2 or 4 if one click jumps several games
TURN_SETTLE = 0.35    # sec of stillness before we actually load the game
IDLE_TO_ATTRACT = 300 # sec of no touching before returning to highlights
HOLD_SECONDS = 2.0


# ---------------------------------------------------------------- mpv
class Mpv:
    """Talks to a single long-lived mpv process over its IPC socket."""

    def __init__(self):
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)
        self.proc = subprocess.Popen([
            "mpv",
            "--idle=yes",
            "--force-window=yes",
            "--fullscreen",
            "--no-osc",
            "--no-terminal",
            "--no-input-default-bindings",
            "--cursor-autohide=always",
            "--hwdec=auto",
            "--vo=gpu",
            "--osd-font-size=42",
            "--osd-color=#FFDCA0",
            "--osd-border-size=2",
            f"--input-ipc-server={SOCKET_PATH}",
        ])
        self.sock = self._connect()
        threading.Thread(target=self._drain, daemon=True).start()

    def _connect(self):
        for _ in range(100):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(SOCKET_PATH)
                return s
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.1)
        raise RuntimeError("mpv IPC socket never showed up")

    def _drain(self):
        # mpv sends event JSON constantly; read and discard so it can't block.
        while True:
            try:
                if not self.sock.recv(65536):
                    return
            except OSError:
                return

    def cmd(self, *args):
        payload = json.dumps({"command": list(args)}) + "\n"
        try:
            self.sock.sendall(payload.encode())
        except OSError:
            self.sock = self._connect()
            self.sock.sendall(payload.encode())

    # convenience wrappers
    def play(self, path, loop=False):
        self.cmd("set_property", "loop-file", "inf" if loop else "no")
        self.cmd("loadfile", str(path), "replace")
        self.cmd("set_property", "pause", False)

    def toggle_pause(self):
        self.cmd("cycle", "pause")

    def osd(self, text, ms=3500):
        self.cmd("show-text", text, ms)


# ---------------------------------------------------------------- content
def load_games():
    data = json.loads(GAMES_FILE.read_text())
    games = data["games"]
    for g in games:
        g["path"] = str((BASE / g["file"]).resolve())
    return data.get("attract"), games


def update_date_display(game):
    """Hook for the little SPI date TFT. Prints for now."""
    print(f"[date] {game.get('date', '')}  {game.get('title', '')}", flush=True)


# ---------------------------------------------------------------- box
class MemoryBox:
    def __init__(self):
        self.attract_file, self.games = load_games()
        self.mpv = Mpv()
        self.index = 0
        self.in_attract = True
        self.last_touch = time.time()
        self._pending = 0
        self._timer = None
        self._held = False
        self._lock = threading.Lock()

        self.encoder = RotaryEncoder(PIN_CLK, PIN_DT, max_steps=0)
        self._last_steps = self.encoder.steps
        self.encoder.when_rotated = self.on_rotate

        self.button = Button(PIN_SW, pull_up=True, bounce_time=0.05,
                             hold_time=HOLD_SECONDS)
        self.button.when_held = self.on_hold
        self.button.when_released = self.on_release

        self.start_attract()
        threading.Thread(target=self._idle_watch, daemon=True).start()

    # ---- attract loop
    def start_attract(self):
        self.in_attract = True
        if self.attract_file:
            self.mpv.play((BASE / self.attract_file).resolve(), loop=True)
        else:
            self.mpv.cmd("stop")

    # ---- encoder
    def on_rotate(self):
        with self._lock:
            self.last_touch = time.time()
            delta = self.encoder.steps - self._last_steps
            self._last_steps = self.encoder.steps
            self._pending += delta
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(TURN_SETTLE, self._settle)
            self._timer.start()

    def _settle(self):
        with self._lock:
            move = int(self._pending / STEPS_PER_DETENT)
            self._pending = 0
            if move == 0:
                move = 1 if self.in_attract else 0
            if move == 0:
                return
            if self.in_attract:
                self.index = 0 if move > 0 else len(self.games) - 1
            else:
                self.index = (self.index + move) % len(self.games)
            game = self.games[self.index]
        self.in_attract = False
        self.mpv.play(game["path"])
        self.mpv.osd(f"{game['title']}\\N{game.get('date', '')}")
        update_date_display(game)

    # ---- button
    def on_hold(self):
        self._held = True
        self.last_touch = time.time()
        self.start_attract()
        self.mpv.osd("")

    def on_release(self):
        self.last_touch = time.time()
        if self._held:
            self._held = False
            return
        if self.in_attract:
            self._pending = STEPS_PER_DETENT   # press in attract = play game 1
            self._settle()
        else:
            self.mpv.toggle_pause()

    # ---- idle
    def _idle_watch(self):
        while True:
            time.sleep(5)
            if (not self.in_attract
                    and time.time() - self.last_touch > IDLE_TO_ATTRACT):
                self.start_attract()


if __name__ == "__main__":
    box = MemoryBox()
    try:
        box.mpv.proc.wait()
    except KeyboardInterrupt:
        pass
