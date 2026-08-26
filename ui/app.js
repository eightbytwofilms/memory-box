/* ============================================================
   Memory Box — browse / play logic.

   One knob drives everything:
     turn  (browse) -> move through the shelves, serpentine
     turn  (playing)-> scrub the film, 30s a detent
     press          -> play / pause
     hold 2s        -> back out to the shelves

   Input arrives either from the keyboard (desktop testing) or
   from server.py over an SSE stream at /events (the real knob).
   ============================================================ */

const CONFIG = {
  PREVIEW_DELAY_MS: 700,    // how long you have to sit on a tile before it starts moving
  DWELL_PLAY_MS: 2500,      // >0 = a tile you sit on auto-plays. ON, and load-
                            //      bearing: the encoder's SW switch is unreliable
                            //      on this build, so turning is the only input we
                            //      can count on. Turn to browse, stop to play,
                            //      wind anticlockwise past the start to come back.
                            //      Don't set this to 0 unless the press has been
                            //      confirmed working - it is the only way to
                            //      select a film without it.
  ATTRACT_IDLE_MS: 120000,  // no input this long -> attract loop
  SEEK_PER_DETENT: 30,      // seconds jumped per click while a film is playing
  CARD_MS: 5000,            // how long the title card stays up when playback starts
  PIN_X: 0.22,              // selected tile parks here, as a fraction of screen width
};

const QS = new URLSearchParams(location.search);
const LITE = QS.has('lite');
if (LITE) document.body.classList.add('lite');

const $ = id => document.getElementById(id);

const S = {
  lib: null,
  flat: [],          // every item, in dial order
  idx: 0,
  mode: 'browse',    // browse | play | attract
  bdFlip: false,
  previewTimer: null,
  dwellTimer: null,
  idleTimer: null,
  cardTimer: null,
  barTimer: null,
};

/* ---------------------------------------------------------- setup */
async function boot() {
  S.lib = await (await fetch('library.json')).json();

  // accent colour: ?theme= wins, else library.json, else the CSS default
  const theme = QS.get('theme') || S.lib.theme;
  if (theme) document.documentElement.dataset.theme = theme;

  $('brand').textContent = S.lib.brand || '';
  $('collection').textContent = S.lib.collection || '';
  $('attractBrand').textContent = S.lib.collection || '';

  // Stamped mark. An explicit `mark` is used verbatim — it has to be, or a
  // jersey number gets truncated to its first digit. Only the fallback
  // (derived from the collection name, minus any leading "THE") is a
  // single letter.
  const mark = (S.lib.mark || '').trim();
  $('mark').textContent =
    mark || (S.lib.collection || '?').replace(/^THE\s+/i, '').trim()[0] || '?';
  $('mark').classList.toggle('mark-wide', mark.length > 1);

  buildShelves();
  select(0, { instant: true, noDwell: true });   // rest on ARCHIVE 88 until the knob moves
  bindInput();
  connectKnob();
  poke();
}

function buildShelves() {
  const track = $('shelfTrack');
  track.innerHTML = '';
  S.flat = [];

  S.lib.rows.forEach((row, r) => {
    const shelf = document.createElement('div');
    shelf.className = 'shelf';
    shelf.innerHTML = `<div class="shelf-title">${row.title}</div>`;

    const strip = document.createElement('div');
    strip.className = 'shelf-row';

    row.items.forEach(item => {
      item.row = r;
      item.poster = `art/${item.id}.jpg`;
      item.backdrop = `art/${item.id}.bg.jpg`;
      item.preview = `art/${item.id}.preview.mp4`;
      item.flat = S.flat.length;
      S.flat.push(item);

      const tile = document.createElement('div');
      tile.className = 'tile';
      tile.style.backgroundImage = `url("${item.poster}")`;
      tile.innerHTML =
        `<div class="tile-year">${item.year || ''}</div>` +
        (item.tag ? `<div class="tile-tag">${item.tag}</div>` : '') +
        `<div class="tile-label">${item.title}</div>`;
      item.el = tile;
      strip.appendChild(tile);
    });

    shelf.appendChild(strip);
    item_shelf(row, shelf, strip);
    track.appendChild(shelf);
  });
}

function item_shelf(row, shelf, strip) { row._shelf = shelf; row._strip = strip; }

/* ---------------------------------------------------------- selection */
function select(next, opts = {}) {
  const n = S.flat.length;
  const idx = ((next % n) + n) % n;
  const prev = S.flat[S.idx];
  const item = S.flat[idx];
  S.idx = idx;

  if (prev && prev !== item) prev.el.classList.remove('selected');
  item.el.classList.add('selected');

  killPreview();
  layout(opts.instant);
  paintHero(item, opts.instant);
  setBackdrop(item.backdrop);

  $('dial').firstElementChild.style.setProperty(
    '--p', n > 1 ? idx / (n - 1) : 0);
  $('counter').innerHTML =
    `<b>${String(idx + 1).padStart(2, '0')}</b> / ${String(n).padStart(2, '0')}`;

  if (!opts.instant) {
    const shelves = document.querySelector('.shelves');
    shelves.classList.remove('tick');
    void shelves.offsetWidth;
    shelves.classList.add('tick');
  }

  if (!LITE) S.previewTimer = setTimeout(() => startPreview(item), CONFIG.PREVIEW_DELAY_MS);

  // Dwell-play arms only on a real knob turn (opts.noDwell is set by every
  // other caller). Without this the box can never rest on the shelves: stop()
  // and the attract wake both re-select the current tile, so backing out of a
  // film re-armed the timer and the same film restarted 2.5s later. Boot had
  // the same problem — the box would open on ARCHIVE 88 and immediately dive
  // into film one before anyone had touched it.
  if (CONFIG.DWELL_PLAY_MS > 0 && !opts.noDwell)
    S.dwellTimer = setTimeout(() => play(item), CONFIG.DWELL_PLAY_MS);
}

function layout(instant) {
  const item = S.flat[S.idx];
  const track = $('shelfTrack');
  const rows = S.lib.rows;

  rows.forEach((row, r) => row._shelf.classList.toggle('active', r === item.row));

  if (instant) track.style.transition = 'none';
  // offsetTop includes the track's top padding, so measure against the first shelf
  const base = rows[0]._shelf.offsetTop;
  track.style.transform = `translateY(${-(rows[item.row]._shelf.offsetTop - base)}px)`;

  const strip = rows[item.row]._strip;
  const first = strip.firstElementChild;
  const pin = window.innerWidth * CONFIG.PIN_X;
  const center = item.el.offsetLeft + item.el.offsetWidth / 2;
  const shift = Math.min(0, pin - center);   // never scroll past the first tile

  rows.forEach(row => {
    if (instant) row._strip.style.transition = 'none';
    row._strip.style.transform =
      `translateX(${row === rows[item.row] ? shift : 0}px)`;
  });

  if (instant) {
    void track.offsetWidth;
    track.style.transition = '';
    rows.forEach(row => (row._strip.style.transition = ''));
  }
}

/* Inline so they work with the network unplugged, and so they inherit the
   accent colour via `stroke:currentColor`-style CSS instead of needing a
   recoloured asset per theme. */
const ICON = {
  cal:   '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
  shield:'<path d="M12 3l7 3v5c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6l7-3z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
};
const metaBit = (icon, text) =>
  `<span class="bit"><svg class="ico" viewBox="0 0 24 24">${ICON[icon]}</svg>${text}</span>`;

function paintHero(item, instant) {
  $('heroKicker').textContent = S.lib.rows[item.row].title;
  $('heroTitle').textContent = item.title;
  $('heroBlurb').textContent = item.blurb || '';

  const bits = [];
  if (item.tag) bits.push(`<span class="badge">${item.tag}</span>`);
  const when = item.date || item.year;
  if (when) bits.push(metaBit('cal', when));
  if (item.opponent) bits.push(metaBit('shield', item.opponent));
  if (item.runtime) bits.push(metaBit('clock', item.runtime));
  $('heroMeta').innerHTML = bits.join('<span class="sep"></span>');

  if (!instant) {
    const el = document.querySelector('.hero-inner');
    el.classList.remove('swap');
    void el.offsetWidth;
    el.classList.add('swap');
  }
}

function setBackdrop(url) {
  const [on, off] = S.bdFlip ? [$('bdA'), $('bdB')] : [$('bdB'), $('bdA')];
  S.bdFlip = !S.bdFlip;
  on.style.backgroundImage = `url("${url}")`;
  on.classList.add('on');
  off.classList.remove('on');
}

/* ---------------------------------------------------------- hover preview */
let previewEl = null;

function startPreview(item) {
  if (S.mode !== 'browse') return;
  if (!previewEl) {
    previewEl = document.createElement('video');
    previewEl.className = 'tile-prev';
    previewEl.muted = true;
    previewEl.loop = true;
    previewEl.playsInline = true;
  }
  previewEl.src = item.preview;
  item.el.appendChild(previewEl);
  previewEl.play().then(
    () => previewEl.classList.add('on'),
    () => {}                              // no preview file yet — poster stays, no harm
  );
}

function killPreview() {
  clearTimeout(S.previewTimer);
  clearTimeout(S.dwellTimer);
  if (previewEl) {
    previewEl.classList.remove('on');
    previewEl.pause();
    previewEl.remove();
  }
}

/* ---------------------------------------------------------- playback */
function play(item) {
  killPreview();
  clearTimeout(S.idleTimer);
  S.mode = 'play';

  const v = $('video');
  v.src = item.file;
  v.currentTime = 0;
  v.play().catch(() => {});

  $('pcKicker').textContent = S.lib.rows[item.row].title;
  $('pcTitle').textContent = item.title;
  $('pcMeta').textContent =
    [item.date || item.year, item.opponent].filter(Boolean).join('   /   ');
  $('pbTitle').textContent = item.title;
  $('pausedBadge').classList.remove('on');

  show('player');
  $('playerCard').classList.add('on');
  clearTimeout(S.cardTimer);
  S.cardTimer = setTimeout(() => $('playerCard').classList.remove('on'), CONFIG.CARD_MS);
  flashBar();
}

function stop() {
  const v = $('video');
  v.pause();
  v.removeAttribute('src');
  v.load();
  S.mode = 'browse';
  show('browse');
  select(S.idx, { instant: true, noDwell: true });   // don't restart the film you just left
  poke();
}

function flashBar() {
  $('playerBar').classList.add('on');
  clearTimeout(S.barTimer);
  S.barTimer = setTimeout(() => $('playerBar').classList.remove('on'), 3500);
}

$('video').addEventListener('timeupdate', () => {
  const v = $('video');
  if (!v.duration) return;
  $('pbFill').style.width = (v.currentTime / v.duration) * 100 + '%';
  $('pbTime').textContent = clock(v.currentTime) + ' / ' + clock(v.duration);
});
$('video').addEventListener('ended', stop);

const clock = s => {
  s = Math.max(0, Math.floor(s));
  return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
};

/* ---------------------------------------------------------- attract */
function poke() {
  clearTimeout(S.idleTimer);
  if (S.mode === 'attract') {
    $('attractVideo').pause();
    S.mode = 'browse';
    show('browse');
    select(S.idx, { instant: true, noDwell: true });   // waking up is not a selection
  }
  if (S.mode === 'browse')
    S.idleTimer = setTimeout(toAttract, CONFIG.ATTRACT_IDLE_MS);
}

function toAttract() {
  if (QS.has('noattract')) return;   // dev harnesses stay on the browse screen
  killPreview();
  S.mode = 'attract';
  show('attract');

  // load the attract reel on first use, not at boot — it's a full-size file
  const v = $('attractVideo');
  if (!v.getAttribute('src')) {
    const att = S.flat.find(i => i.id === S.lib.attract) || S.flat[0];
    if (!att) return;
    v.src = att.file;
  }
  v.play().catch(() => {});
}

function show(which) {
  ['browse', 'player', 'attract'].forEach(id =>
    $(id).classList.toggle('is-active', id === which));
}

/* ---------------------------------------------------------- input */
function rotate(delta) {
  poke();
  if (S.mode === 'play') {
    const v = $('video');
    // The way back to the shelf, with no working switch on the knob: wind the
    // dial anticlockwise past the start of the film and you come out of it.
    // Otherwise a film that began on its own is a 28-minute trap — turning
    // only scrubs, and back() is reachable only from the button or a keyboard.
    // It doubles as an undo for a dwell-play you didn't mean to trigger.
    if (delta < 0 && v.currentTime <= 0.5) { stop(); return; }
    v.currentTime = Math.max(0,
      Math.min((v.duration || 0) - 1, v.currentTime + delta * CONFIG.SEEK_PER_DETENT));
    flashBar();
    return;
  }
  select(S.idx + delta);
}

function press() {
  poke();
  if (S.mode === 'play') {
    const v = $('video');
    if (v.paused) { v.play(); $('pausedBadge').classList.remove('on'); }
    else { v.pause(); $('pausedBadge').classList.add('on'); }
    flashBar();
  } else {
    play(S.flat[S.idx]);
  }
}

function back() {
  poke();
  if (S.mode === 'play') stop();
  else toAttract();
}

function jumpRow(dir) {
  const item = S.flat[S.idx];
  const r = item.row + dir;
  if (r < 0 || r >= S.lib.rows.length) return;
  const here = S.flat.filter(i => i.row === item.row).indexOf(item);
  const target = S.lib.rows[r].items;
  select(target[Math.min(here, target.length - 1)].flat);
}

function bindInput() {
  addEventListener('keydown', e => {
    switch (e.key) {
      case 'ArrowRight': case 'ArrowDown': rotate(1); break;
      case 'ArrowLeft':  case 'ArrowUp':   rotate(-1); break;
      case 'Enter': case ' ':              press(); break;
      case 'Escape': case 'Backspace':     back(); break;
      case 'PageDown': jumpRow(1); break;
      case 'PageUp':   jumpRow(-1); break;
      default: return;
    }
    e.preventDefault();
  });
  addEventListener('resize', () => layout(true));
}

/* the real knob: server.py streams events here.

   Skipped inside an iframe. The knob stream is a permanently-open connection,
   and browsers cap concurrent connections per host at 6 — so the dev harnesses,
   which show several copies of this UI at once, would use up the whole pool and
   starve the posters and JSON. The real box is never in an iframe. */
function connectKnob() {
  if (window.top !== window.self) return;
  let es;
  const open = () => {
    es = new EventSource('/events');
    es.onmessage = e => {
      const m = JSON.parse(e.data);
      if (m.type === 'rotate') rotate(m.delta);
      else if (m.type === 'press') press();
      else if (m.type === 'hold') back();
    };
    es.onerror = () => { es.close(); setTimeout(open, 3000); };
  };
  open();
}

boot();
