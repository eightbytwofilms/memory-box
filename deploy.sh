#!/usr/bin/env bash
# Push the Memory Box to the Pi.
#
#   ./deploy.sh                  # code + art only  (fast, seconds)
#   ./deploy.sh --media          # code + art + the 2.5 GB of film
#
# Set these to match your Pi, or export them in your shell:
PI="${PI:-pi@raspberrypi.local}"
DEST="${DEST:-/home/pi/memory-box}"

set -euo pipefail
cd "$(dirname "$0")"

SRC_MEDIA="${MEDIA_DIR:-$HOME/Desktop/Films}"
WITH_MEDIA="${1:-}"

echo "==> target: $PI:$DEST"
ssh "$PI" "mkdir -p '$DEST/ui'"

# Code, UI and art.
#
# ui/media is a SYMLINK on the Mac pointing at the Desktop. rsync -a would
# faithfully copy the symlink and it would dangle on the Pi — the UI would
# load, look perfect, and 404 every film. Exclude it here and send the real
# files separately below, so the Pi gets a genuine directory.
rsync -a --progress --delete \
  --exclude 'media' --exclude '_*.html' --exclude '.DS_Store' \
  ui/ "$PI:$DEST/ui/"

rsync -a --progress \
  server.py player.py games.json build-art.sh README.md \
  start-kiosk.sh knob-test.py \
  "$PI:$DEST/"
ssh "$PI" "chmod +x '$DEST/start-kiosk.sh' '$DEST/knob-test.py'"

# art-src holds the hand-picked frames (Jeannette, Ringgold). Not needed to
# run, but it's the only copy of that work — keep the Pi a complete mirror.
[[ -d art-src ]] && rsync -a --progress art-src/ "$PI:$DEST/art-src/"

if [[ "$WITH_MEDIA" == "--media" ]]; then
  echo "==> films (2.5 GB — first run is slow, later runs only send changes)"
  # No -z: H.264 is already compressed, so gzip burns Pi CPU for ~0 gain.
  # --partial so a dropped wifi connection resumes instead of restarting.
  rsync -a --progress --partial \
    "$SRC_MEDIA/" "$PI:$DEST/ui/media/"
else
  echo "==> skipping films (pass --media to send them)"
fi

echo "==> verifying"
ssh "$PI" "cd '$DEST' && \
  echo \"films:  \$(ls ui/media 2>/dev/null | wc -l)\" && \
  echo \"art:    \$(ls ui/art 2>/dev/null | wc -l)\" && \
  echo \"free:   \$(df -h . | awk 'NR==2{print \$4}')\" && \
  python3 -c 'import json;d=json.load(open(\"ui/library.json\"));print(\"library:\",d[\"collection\"],\"-\",sum(len(r[\"items\"]) for r in d[\"rows\"]),\"items\")'"

echo
echo "Done. On the Pi:  sudo systemctl restart memorybox"
