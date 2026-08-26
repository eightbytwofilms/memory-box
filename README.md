<img src="logo.png" alt="Eight × Two Films" width="96" align="right">

# Memory Box

A Raspberry Pi inside a gutted 1960s radio that plays your family's films, browsed
with the radio's own tuning knob.

It is a completely offline device. No internet, no account, no subscription, no
cloud — the films live on the Pi's SD card and the Pi plays them off itself. Pull
the network and nothing changes, because there was never anything on the other end.

**Turn** the knob to browse shelves of films, **press** to play, **turn while playing**
to scrub 30 seconds a click, **hold** to back out. Two minutes idle and it drifts into
an attract loop.

Built for my father's high-school football films, scanned off 16mm. It works for
anything you'd want permanent, private and sitting on a shelf.

---

## Quick start

Runs on a Mac or PC with no Pi attached — it reports "no GPIO" and you drive it with
the arrow keys, Enter and Escape. That's how most of the interface was written.

```bash
git clone https://github.com/eightbytwofilms/memory-box.git
cd memory-box
cp ui/library.sample.json ui/library.json    # shelves, titles, blurbs — edit it
cp art-items.sample.conf art-items.conf      # which film each poster comes from
mkdir -p ui/media                            # put your .mp4 files here
./build-art.sh                               # generate posters + hover previews
python3 server.py                            # http://localhost:8000/
```

`ui/library.json`, `art-items.conf`, `ui/media/` and the generated art are all gitignored — this repo
is the machine, not anybody's home movies.

---

## 1. Parts

| Part | Notes | ~Cost |
|---|---|---|
| **KY-040 rotary encoder module** (buy a 5-pack) | 20-detent, with push switch. Has onboard 10k pull-ups. 6mm D-shaft, M7 threaded bushing. | $8/5 |
| **Female–female Dupont jumpers**, 5 needed | Or solder directly and heat-shrink — more reliable in a gift/heirloom. | $6 |
| **2× 0.1 µF (100 nF) ceramic caps** | CLK→GND and DT→GND, at the encoder. Kills the KY-040's notorious double-counting. Skip only if it behaves. | $1 |
| **1/8" expanded PVC or 1/4" plywood scrap** | The encoder bracket. Hand-cut, no printer needed. | have |
| **M2.5 or #4 screws + nylon washers/spacers** | Bracket-to-crossbar, and shimming shaft depth. | $5 |
| **Wood strip, ~3/4" × 3/4" × cabinet width** | Interior crossbar to mount the bracket to (see §4). | have |
| **2-part epoxy putty** (JB Weld SteelStik / Milliput) | Custom-molding the vintage knob bore to the 6mm shaft. | $6 |
| **E6000 or 5-min epoxy** | Bracket-to-panel if you don't crossbar it. | have |

Optional: **K&S brass telescoping tubing** if you'd rather sleeve the shaft than mold the knob.

Already owned: Pi 4, microSD, PSU, screen, Adafruit TFT (date readout, later).

---

## 2. Wiring

KY-040 → Pi 40-pin header. **3.3V, not 5V** — GPIO is not 5V tolerant and the
module's pull-ups tie CLK/DT to whatever you feed `+`.

| KY-040 | Pi pin | GPIO |
|---|---|---|
| `+` / VCC | 1 | 3.3V |
| `GND` | 6 | GND |
| `CLK` | 11 | GPIO17 |
| `DT` | 12 | GPIO18 |
| `SW` | 13 | GPIO27 |

`SW` uses the Pi's internal pull-up (set in code) — no external resistor.
If you add the debounce caps: 0.1 µF from CLK to GND and DT to GND, soldered
right at the module pins.

---

## 3. Software

Two players live in this folder. Pick one.

| | `server.py` + `ui/` | `player.py` |
|---|---|---|
| Look | Netflix-style shelves, posters, hover previews, hero panel | fullscreen video + a text overlay |
| Draws with | Chromium in kiosk mode | mpv |
| Use it when | this is the showcase build / the magazine photos | you want the absolute simplest, lightest thing |

**Everything runs on the Pi itself.** `server.py` is a local file-reader on
`localhost` — it reads the MP4s off the Pi's own SD card and bridges the knob
into the page. There is no internet involved; pull the network and it is
identical. Chromium is only being used as the drawing surface, because mpv
can't render a UI like this.

### 3a. The Netflix-style UI (`server.py` + `ui/`)

```bash
sudo apt update && sudo apt install -y chromium-browser python3-gpiozero
```

Copy this whole folder to `/home/pi/memory-box/`, and put the MP4s in
`/home/pi/memory-box/ui/media/`. (On a Mac it's convenient to make `ui/media` a symlink to wherever the films
already live, so nothing is duplicated — on the Pi make it a real folder.) Then:

```bash
cd ~/memory-box && python3 server.py --kiosk
```

Content is defined in **`ui/library.json`** (copy `ui/library.sample.json` to start) — the shelves, their order, and per
game: title, opponent, year, `date`, runtime, corner `tag`, and the `blurb` that
shows in the hero panel. Dial order = the order things appear in that file.
**The `date` fields are blank** — fill in the real game dates and they replace
the year in the hero line (and feed the SPI date TFT later).

Poster stills and the silent hover previews are generated, not hand-made:

```bash
./build-art.sh            # makes anything missing, into ui/art/
./build-art.sh --force    # redo everything
```

Don't like a poster frame? Change that row's percentage in the table at the top
of `build-art.sh`, delete the `.jpg`, re-run.

Behavior:
- **Turn** → moves along the shelf; at the end of a shelf it rolls onto the next
  one, so the whole library is one continuous dial.
- **Sit on a tile ~0.7 s** → the poster starts playing a silent 7-second preview.
- **Press** → play. Press again while playing → pause.
- **Turn while playing** → scrubs 30 s a click. This matters: these are 16–28
  minute game reels and you will want to get to a specific play.
- **Hold 2 s** → back out.
- **2 min idle** → attract loop.

Tuning knobs at the top of `ui/app.js`:
- `DWELL_PLAY_MS` — set it to e.g. `5000` and a tile you sit on plays itself.
  **This is the insurance policy if the vintage knob turns out not to press**;
  with it on, the build never depends on the switch working.
- `SEEK_PER_DETENT`, `ATTRACT_IDLE_MS`, `PREVIEW_DELAY_MS`.

`STEPS_PER_DETENT` is in `server.py` — raise it to 2 or 4 if one click of the
knob jumps several tiles.

If the Pi struggles, load `http://localhost:8000/?lite=1` — that kills the film
grain and the hover previews, which are the only expensive parts.

Test it on a Mac with no Pi in sight: `python3 server.py` and drive it with the
arrow keys, Enter, and Escape. It just reports "no GPIO" and carries on.

### 3b. The simple player (`player.py`)

```bash
sudo apt update && sudo apt install -y mpv python3-gpiozero
```

Videos in `memory-box/media/`, edit `games.json`. **Turn** tunes straight to a
game and plays it, **press** pauses, **hold 2 s** returns to the attract loop.
If one detent jumps several games, set `STEPS_PER_DETENT` at the top of the file.

### Autostart on boot

`/etc/systemd/system/memorybox.service` — swap the `ExecStart` line for
`player.py` if you went that route:

```ini
[Unit]
Description=Memory Box player
After=graphical.target

[Service]
User=pi
Environment=XDG_RUNTIME_DIR=/run/user/1000
Environment=DISPLAY=:0
WorkingDirectory=/home/pi/memory-box
ExecStart=/usr/bin/python3 /home/pi/memory-box/server.py --kiosk
Restart=always
RestartSec=3

[Install]
WantedBy=graphical.target
```

```bash
sudo systemctl enable --now memorybox
```

Set the Pi to **boot to desktop, auto-login** (`sudo raspi-config` → System →
Boot/Auto Login) and disable screen blanking (Display → Screen Blanking → off).

### Last step before it leaves the bench

`sudo raspi-config` → Performance → **Overlay File System → enable** (read-only
boot partition too). After that the SD card is immune to yanked power cords —
non-negotiable for something someone unplugs at will. Do this *after* all
content and code is final; to change anything later you turn overlay off, edit,
turn it back on.

Then: days of burn-in + at least a dozen pull-the-plug tests.

---

## 4. Mounting the encoder with the tuner gone

The original knob rode on the tuning capacitor's shaft, which passed through a
bushing anchored to the chassis. Chassis is gone, so the front-panel hole is now
just a hole in thin material with nothing behind it. You need to rebuild that
anchor. Don't try to hang the encoder off the panel hole alone — the KY-040's
M7 bushing has ~5 mm of thread, which won't clamp through most panels plus a
bracket, and a knob you turn hundreds of times will work an epoxy-only joint loose.

> **Visual versions of this section:** `knob-visual-guide.html` (how it mounts),
> `bracket-cut-list.html` (what to cut and buy), `shaft-length-guide.html` (the
> shaft, and why the strip must be ~3 mm).

**Critical dimension:** the M7 bushing is only **~5 mm** of thread, so whatever the
encoder bolts through must be **≈3 mm (⅛")**. ¼" PVC is 6.35 mm — the nut will not
reach. If the stock is thicker, counterbore a ⅜"–½" dish ~3 mm deep on the front
face and drill the 9/32" hole through the middle of it.

**The build, in order:**

**a) Measure four things first**
1. Panel hole diameter (vintage tuning holes are usually 8–10 mm — bigger than
   the encoder's 7 mm bushing, which is fine and gives you centering slop).
2. Panel thickness at the hole.
3. Knob bore diameter *and* depth.
4. How far the knob face originally stood off the panel — match this and the
   front looks stock.

**b) Encoder geometry to plan against**
KY-040 shaft is 6 mm diameter, ~20 mm tall, of which ~13–15 mm sticks up past
the top of the threaded bushing. Budget: `15 mm ≈ panel thickness + air gap +
knob bore depth`. That's the constraint that sets your spacer stack. Leave
**at least 2 mm of air** between the back of the knob and the panel so the
push-switch has travel and the knob never rubs.

**c) Make the bracket**
Cut a ~50 × 50 mm square of 1/8" PVC (or 1/4" ply). Drill a 7 mm hole dead
center. Push the encoder's bushing through **from the back**, secure with the
star washer + nut on the front face. The encoder is now rigid on a flat plate,
and the plate is what you position.

**d) Anchor the bracket — pick one**

- **Best: interior crossbar.** Cut a wood strip that spans the cabinet
  side-to-side at knob height, glued and/or screwed into the side walls (or into
  the old chassis mounting bosses if any survived — they're worth looking for).
  Screw the bracket to the crossbar, using nylon washers as shims to dial in
  shaft depth. Fully reversible, rock solid, and it gives you an anchor point
  for the second knob hole and the Pi later.
- **Acceptable: standoff-and-glue.** Nylon standoffs between bracket and the
  inside face of the panel, E6000 on the standoff feet. Only if the panel is
  solid material, and only after a dry-fit — E6000 stays flexible, which is
  actually good here (absorbs knob torque instead of cracking).

**e) Center it in the hole**
With the bracket loose, put the knob on, sight down the panel face, get the
shaft centered in the hole, *then* tighten/glue. If the hole is much larger than
6 mm and it looks gappy, a thin black finishing washer or a hand-cut PVC ring
behind the knob hides it.

**f) Fit the vintage knob to a 6 mm shaft**
Almost certainly the bore won't match. In order of preference:

1. **Mold it.** Wrap the encoder shaft in one layer of PTFE/plumber's tape as a
   release, pack the knob bore with epoxy putty, press the knob on, let it set
   ~10 min, twist off. You get a perfect custom bore including the D-flat.
   Cheap, no parts, works on splined/odd/oversized bores.
2. **Sleeve it.** Brass tubing that slips over 6 mm and fits the bore, epoxied
   to the shaft.
3. **Set screw.** If the knob has one and the bore is close, a strip of aluminum
   can as a shim + the set screw on the shaft's flat is fine.

Don't permanently epoxy the knob to the shaft until after the dry-fit — you'll
want it off again.

**g) Rotational alignment doesn't matter.** The encoder is relative, not
absolute, so there's no "pointer must line up" problem the old tuner had. One
less thing.

**h) Strain relief.** Once wired, hot-glue the jumper bundle to the bracket a
few cm from the pins so tugging the loom can't pop a Dupont connector off.
Better: solder + heat-shrink for the heirloom build.

**Sequence warning:** do the *entire* dry-fit — encoder, bracket, screen, bezel,
Pi — before the artwork goes on. Enlarging or moving a hole after the hand-drawn
layer and dad stencil are down is unrecoverable.

---

## Credits and licence

Code is MIT (see `LICENSE`). The interface uses **Bebas Neue**, self-hosted in
`ui/fonts/` under the SIL Open Font License — self-hosted deliberately, because the
box has to boot with no network.
