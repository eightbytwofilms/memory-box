#!/usr/bin/env bash
# Generates the poster stills + silent hover previews the Netflix UI needs.
# Re-run any time you add footage or want a different poster frame:
#   ./build-art.sh            # only makes what's missing
#   ./build-art.sh --force    # rebuild everything
#
# To change one poster, delete ui/art/<id>.jpg and re-run, or bump the
# percentage in the table below (3rd column = where in the film to grab).

set -euo pipefail
cd "$(dirname "$0")"

SRC="${MEDIA_DIR:-ui/media}"
OUT="ui/art"
FORCE="${1:-}"
mkdir -p "$OUT"

# id | filename | poster % | preview start % | backdrop %
#
# The backdrop % is deliberately a different point in the film from the
# poster. If they matched, the screen would be one photo shown twice —
# a giant copy of the tile you're already looking at.
if [[ ! -f art-items.conf ]]; then
  echo "No art-items.conf - copy art-items.sample.conf and list your films." >&2
  exit 1
fi
# shellcheck source=/dev/null
source art-items.conf

# Hand-picked art is protected from rebuilds.
#
# Some frames you can't reach by naming a percentage — the Jeannette backdrop
# is the Three Rivers midfield logo, found by scrubbing, and no timestamp in
# the table lands on it. Drop a marker next to any file you picked yourself:
#
#   touch ui/art/1972-jeannette.bg.keep
#
# and even --force will leave it alone.
keep(){ [[ -f "${1%.*}.keep" ]]; }   # foo.bg.jpg -> foo.bg.keep
build(){ # build <outfile>  -> true if it should be (re)made
  keep "$1" && { echo "keep    $(basename "$1")"; return 1; }
  [[ "$FORCE" == "--force" || ! -f "$1" ]]
}

for row in "${ITEMS[@]}"; do
  IFS='|' read -r id file ppct spct bpct <<<"$row"
  in="$SRC/$file"
  if [[ ! -f "$in" ]]; then echo "MISSING: $file"; continue; fi

  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$in")
  pts=$(awk -v d="$dur" -v p="$ppct" 'BEGIN{printf "%.2f", d*p/100}')
  sts=$(awk -v d="$dur" -v p="$spct" 'BEGIN{printf "%.2f", d*p/100}')
  bts=$(awk -v d="$dur" -v p="${bpct:-58}" 'BEGIN{printf "%.2f", d*p/100}')

  # Every one of these scans is 4:3 picture sitting inside a 16:9 file, with
  # ~25% of the width as black bars. Left alone, the thumbnails would be a
  # quarter black. Crop to the centred 4:3 so tiles are all picture.
  # (Playback is NOT cropped — the films play as shot.)
  CROP="crop=ih*4/3:ih"

  # The backdrop goes edge-to-edge, so the film's own gate edges — the soft
  # black border baked into every scan — would show up as hard lines across
  # the screen. Overscan to eat them, then take a 16:9 band out of the
  # middle so the image already matches the screen and doesn't have to be
  # cover-cropped and upscaled at runtime.
  #
  # 9% a side, not the 3% this started at: the 1969 junior-high reel has the
  # widest gate edge of the set and still showed a black bar at 3%. It also
  # matters more than it looks, because `normalize` below reads the whole
  # frame — leave the bars in and they drag the black point down, so the
  # picture itself never gets stretched up.
  BGCROP="${CROP},crop=iw*0.82:ih*0.82,crop=iw:iw*9/16"

  if build "$OUT/$id.jpg"; then
    echo "poster  $id"
    ffmpeg -nostdin -v error -y -ss "$pts" -i "$in" -frames:v 1 \
      -vf "${CROP},scale=800:-2:flags=lanczos" -q:v 3 "$OUT/$id.jpg"
  fi

  # The full-screen wash behind the shelves.
  #
  # The blur is baked in here rather than done in CSS on purpose: a
  # `filter:blur()` on a full-screen layer is recomputed every frame the
  # Ken Burns transform moves, which is real GPU work on a Pi 4. Baking it
  # costs nothing at runtime.
  #
  # sigma=2, down from 4. The 4 was set when this art covered the whole
  # screen — at that size it was magnified enough that grain read as
  # digital noise, and heavy blur was the cheapest way to kill it. The
  # backdrop is now a panel roughly two-thirds of the screen, so the same
  # art is enlarged far less and 2 is enough to keep it from competing
  # with the type. Any lower and the scan's grain starts to sparkle.
  #
  # `normalize` runs BEFORE the grade and is what makes this work across the
  # whole box. These scans range from bright afternoon games to night games
  # several stops darker, so any fixed brightness/contrast that suits one
  # ruins the other — an earlier fixed grade crushed the 1971 Belle Vernon
  # night game to a black rectangle. normalize stretches each frame's own
  # levels to the same range first, so the grade below only has to set the
  # look, not fix the exposure.
  #
  # Also: desaturated to true grey, then warmed back with colorbalance.
  # The scans carry a green-ish cast that goes sickly at this scale, and a
  # warm tone is what makes the panel look like a lit object in a wooden
  # radio instead of a monitor.
  # A hand-picked backdrop can't always be reached by naming a percentage.
  # The Jeannette one is the Three Rivers midfield logo, found by scrubbing;
  # no timestamp in the table lands on it. Drop a full-res frame at
  # art-src/<id>.bg.png and it's used as the source instead of the film.
  #
  # Store it CLEAN but UNGRADED — already cropped 16:9 and with any overlay
  # removed, but no blur, levels or colour. That way it still goes through
  # the same chain as the other eleven, and re-tuning the look re-tunes all
  # twelve together. (Stashing a finished JPEG instead is what leaves one
  # backdrop stranded at the old settings.)
  handpick="art-src/$id.bg.png"
  if [[ -f "$handpick" ]]; then bgin="$handpick"; bgpre="null"; bgss=0
  else                          bgin="$in";       bgpre="$BGCROP"; bgss="$bts"; fi

  if build "$OUT/$id.bg.jpg"; then
    echo "backdrop $id"
    ffmpeg -nostdin -v error -y -ss "$bgss" -i "$bgin" -frames:v 1 \
      -vf "${bgpre},scale=1600:-2:flags=lanczos,\
normalize=blackpt=0x0A0A0A:whitept=0xEAEAEA:smoothing=0,gblur=sigma=2,\
eq=contrast=1.05:saturation=0,\
colorbalance=rm=.12:gm=.02:bm=-.08:rh=.10:bh=-.06" \
      -q:v 4 "$OUT/$id.bg.jpg"
  fi

  if build "$OUT/$id.preview.mp4"; then
    echo "preview $id"
    ffmpeg -nostdin -v error -y -ss "$sts" -i "$in" -t 7 -an \
      -vf "${CROP},scale=640:-2:flags=lanczos,fps=24" \
      -c:v libx264 -profile:v baseline -level 3.1 -pix_fmt yuv420p \
      -crf 30 -preset veryfast -movflags +faststart "$OUT/$id.preview.mp4"
  fi
done

echo "done -> $OUT"
