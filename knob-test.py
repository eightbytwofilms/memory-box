#!/usr/bin/env python3
"""
Prove the knob is wired right — BEFORE it goes in the radio.

    python3 knob-test.py            # normal: shows detents and presses
    python3 knob-test.py --raw      # diagnose: shows each wire's raw state

Run this on the Pi with the encoder on the bench. Once it's mounted behind
the radio face and the cabinet is closed, finding a swapped wire means
taking it all apart again.

Wiring (same pins server.py uses):

    KY-040          Pi header
    ------          -------------------------
    +      ->       pin 1   3.3V   (NOT 5V — the GPIO pins are 3.3V)
    GND    ->       pin 6   ground
    CLK    ->       pin 11  GPIO 17
    DT     ->       pin 12  GPIO 18
    SW     ->       pin 13  GPIO 27

Wire it with the Pi POWERED OFF and unplugged.
"""

import argparse
import sys
import time

PIN_CLK, PIN_DT, PIN_SW = 17, 18, 27


def normal():
    """What the box actually does: count detents, notice presses."""
    from gpiozero import Button, RotaryEncoder

    enc = RotaryEncoder(PIN_CLK, PIN_DT, max_steps=0)
    btn = Button(PIN_SW, pull_up=True, bounce_time=0.05)

    print(f"CLK=GPIO{PIN_CLK}  DT=GPIO{PIN_DT}  SW=GPIO{PIN_SW}")
    print("Turn the knob. Press it. Ctrl-C when you're satisfied.\n")

    state = {"steps": 0, "turns": 0, "presses": 0}

    def rotated():
        delta = enc.steps - state["steps"]
        state["steps"] = enc.steps
        state["turns"] += 1
        arrow = "RIGHT  -->" if delta > 0 else "<--  LEFT"
        print(f"  {arrow}   position {enc.steps:+d}")

    def pressed():
        state["presses"] += 1
        print("  PRESS")

    enc.when_rotated = rotated
    btn.when_pressed = pressed

    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        t, p = state["turns"], state["presses"]
        print(f"\n{t} detents, {p} presses.")
        if t == 0:
            print("\nNo detents at all -> CLK or DT (or 3.3V/GND) isn't connected.")
            print("Re-run with --raw to see which wire is dead.")
        if p == 0:
            print("\nNo presses -> SW isn't connected, or this knob doesn't click.")
            print("Not fatal: turning alone drives the UI. But check the wire first.")
        if t:
            print("\nIf RIGHT and LEFT are backwards, swap the CLK and DT wires")
            print("(pin 11 and pin 12). Nothing is broken — the encoder is")
            print("relative, so which way is 'forward' is just which wire leads.")


def raw():
    """One wire at a time. Use when normal mode sees nothing."""
    from gpiozero import Button

    clk = Button(PIN_CLK, pull_up=True)
    dt = Button(PIN_DT, pull_up=True)
    sw = Button(PIN_SW, pull_up=True)

    print("Raw pin states. Turn the knob VERY slowly, one click at a time.")
    print("CLK and DT should each flip between 0 and 1 as you turn.")
    print("If one never changes, that wire (or its solder joint) is the problem.")
    print("SW should go 1 while you hold the knob down.\n")
    print("   CLK  DT   SW")

    last = None
    try:
        while True:
            now = (int(clk.is_pressed), int(dt.is_pressed), int(sw.is_pressed))
            if now != last:
                print(f"    {now[0]}    {now[1]}    {now[2]}")
                last = now
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", action="store_true",
                    help="show raw pin states instead of decoded turns")
    args = ap.parse_args()

    try:
        raw() if args.raw else normal()
    except ImportError:
        sys.exit("gpiozero not available — are you running this on the Pi?")
    except Exception as e:
        sys.exit(f"GPIO error: {e}\n\nIs the kiosk still running? It holds these "
                 f"pins.\nStop it first:  pkill -f 'server[.]py'")
