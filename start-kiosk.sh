#!/usr/bin/env bash
# Launched by wayfire at login (see ~/.config/wayfire.ini [autostart]).
#
# Why an autostart entry and not a system-wide systemd service: Chromium has
# to be a client of the logged-in user's Wayland session. Started from
# anywhere else — a system service, an SSH shell — it comes up with no
# workspace context and maps its window where nobody can see it. The process
# runs, the log looks clean, and the screen shows the desktop. Starting it
# from inside the session is what puts it on the screen.

cd "$HOME/memory-box" || exit 1

exec >> /tmp/kiosk.log 2>&1
echo "=== start-kiosk $(date) ==="

# Session managers launch autostart entries with a nearly empty environment —
# no DISPLAY, no WAYLAND_DISPLAY, no XDG_RUNTIME_DIR. Chromium then starts,
# finds no display server to talk to, and runs with no visible window: ten
# live processes, a clean log, a black screen, and no error anywhere. So
# establish the session ourselves rather than inheriting it.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

# X11 first. On this hardware Chromium under wayfire connects, maps a
# correctly-titled window, reports no errors — and paints nothing at all.
# A plain crimson test page came out as black as the real UI did, so it
# isn't the app. X11 renders normally, so that's what the box runs.
if [ -z "${DISPLAY:-}" ] && [ -e /tmp/.X11-unix/X0 ]; then
  export DISPLAY=:0
fi

if [ -n "${DISPLAY:-}" ]; then
  echo "using X11 DISPLAY=$DISPLAY"
  command -v xset >/dev/null && {
    xset s off; xset -dpms; xset s noblank
  } 2>/dev/null
else
  # No X — fall back to Wayland so this still runs on a Wayland card.
  if [ -z "${WAYLAND_DISPLAY:-}" ]; then
    for _ in $(seq 1 60); do
      sock=$(find "$XDG_RUNTIME_DIR" -maxdepth 1 -name 'wayland-[0-9]*' \
             ! -name '*.lock' -type s 2>/dev/null | head -1)
      [ -n "$sock" ] && { export WAYLAND_DISPLAY="$(basename "$sock")"; break; }
      sleep 0.5
    done
  fi
  [ -z "${WAYLAND_DISPLAY:-}" ] && { echo "FATAL: no display server found"; exit 1; }
  echo "using WAYLAND_DISPLAY=$WAYLAND_DISPLAY"
  command -v wlopm >/dev/null && wlopm --on '*' 2>/dev/null
fi

# A stale Chromium holding the profile lock silently swallows every later
# launch ("Opening in existing browser session") and shows nothing.
pkill -f '/usr/lib/chromiu[m]' 2>/dev/null
sleep 2
rm -f "$HOME/.config/chromium/Singleton"* 2>/dev/null

# Screen blanking off — this is a radio, it shouldn't go dark on its own.
# (wlopm is the Wayland equivalent of the old `xset s off`.)
# (blanking handled per-stack above)

exec python3 server.py --port 8000 --kiosk
