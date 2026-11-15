#!/usr/bin/env python3
"""Toddler Desk - a calm, boring, full-screen "work" screen for small hands.

Keys type into a pretend report; a progress bar fills and the report gets
"saved". Clicks leave a faint ripple. Nothing flashy, no sounds.

Exit:  hold Ctrl + Alt + Shift, then press P and I (together, or P then I).
       Either Alt works (incl. AltGr). If the window has lost keyboard focus,
       a GNOME shortcut for Ctrl+Alt+Shift+I quits it instead. From another
       machine: `toddler_desk.py --quit` (or kill it; it restores on SIGTERM).
Exit 2: tap Esc 8 times; a line top-right asks for two random letters pressed together.
       Any other key, letting go early, a tap, or 15 s hides it again.

While running it:
  * inhibits GNOME system shortcuts (GNOME asks you to "Allow" once),
  * temporarily blanks GNOME keybindings, the Super key, hot corner,
    notification banners, accessibility hotkeys and the power-button action,
  * holds a systemd inhibitor for the power/suspend/hibernate keys and lid,
and puts every setting back on exit. If it ever dies uncleanly, run
`toddler_desk.py --restore` (the launcher script does this automatically).
"""

import json
import logging
import os
import random
import re
import signal
import subprocess
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, Gio, GLib, Graphene, Gsk, Gtk, Pango  # noqa: E402

try:
    gi.require_version("GLibUnix", "2.0")
    from gi.repository import GLibUnix  # noqa: E402

    _signal_add = GLibUnix.signal_add
except (ImportError, ValueError):
    _signal_add = GLib.unix_signal_add

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import speech  # noqa: E402
from icons import icon_for  # noqa: E402

APP_ID = "org.home.ToddlerDesk"
STATE_DIR = os.path.join(
    os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")), "toddler-desk"
)
BACKUP_FILE = os.path.join(STATE_DIR, "settings-backup.json")
PID_FILE = os.path.join(STATE_DIR, "pid")
LOG_FILE = os.path.join(STATE_DIR, "toddler.log")  # the voice writes here too
log = logging.getLogger("app")


def setup_logging(test_mode):
    os.makedirs(STATE_DIR, exist_ok=True)
    try:  # keep it small: one old copy
        if os.path.getsize(LOG_FILE) > 5_000_000:
            os.replace(LOG_FILE, LOG_FILE + ".1")
    except OSError:
        pass
    h = logging.FileHandler(LOG_FILE)
    h.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d %(name)s: %(message)s", "%H:%M:%S"))
    logging.getLogger().addHandler(h)
    logging.getLogger().setLevel(logging.INFO)
    log.info("---- start%s, pid %d", " (test mode)" if test_mode else "", os.getpid())


def _rss_mb(pid):
    try:
        with open(f"/proc/{pid}/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1e6
    except (OSError, ValueError):
        return 0.0


def _cpu_seconds(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            fields = f.read().rsplit(")", 1)[1].split()
        return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError):
        return 0.0

# A GNOME shortcut that quits the app even when its window has lost keyboard
# focus (then the app's own key handler never sees the exit combo). While the
# app has focus, system shortcuts are inhibited and the app handles it itself.
MEDIA_KEYS = "org.gnome.settings-daemon.plugins.media-keys"
EXIT_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/toddler-desk-exit/"
EXIT_BINDING = "<Control><Alt><Shift>i"

# ---------------------------------------------------------------- settings lock

# Every string-list key in these schemas is a keybinding -> set to [].
KEYBINDING_SCHEMAS = [
    "org.gnome.desktop.wm.keybindings",
    "org.gnome.shell.keybindings",
    "org.gnome.mutter.keybindings",
    "org.gnome.mutter.wayland.keybindings",  # includes Super+Esc and Ctrl+Alt+Fn
    "org.gnome.settings-daemon.plugins.media-keys",  # includes Ctrl+Alt+Del, power key
]

# Individual (schema, key, value-while-locked)
SINGLE_KEYS = [
    ("org.gnome.mutter", "overlay-key", GLib.Variant("s", "")),
    ("org.gnome.settings-daemon.plugins.power", "power-button-action", GLib.Variant("s", "nothing")),
    ("org.gnome.desktop.interface", "enable-hot-corners", GLib.Variant("b", False)),
    ("org.gnome.desktop.notifications", "show-banners", GLib.Variant("b", False)),
    ("org.gnome.desktop.a11y.keyboard", "enable", GLib.Variant("b", False)),  # 5x Shift popups
    # Otherwise the touchpad ignores taps while a key is held down.
    ("org.gnome.desktop.peripherals.touchpad", "disable-while-typing", GLib.Variant("b", False)),
    ("org.gnome.shell.extensions.dash-to-dock", "hot-keys", GLib.Variant("b", False)),
]


def _schema_exists(schema_id):
    src = Gio.SettingsSchemaSource.get_default()
    return src is not None and src.lookup(schema_id, True) is not None


def _planned_changes():
    """Yield (schema, key, locked_value) for everything we will change."""
    src = Gio.SettingsSchemaSource.get_default()
    for schema_id in KEYBINDING_SCHEMAS:
        schema = src.lookup(schema_id, True)
        if schema is None:
            continue
        for key in schema.list_keys():
            if schema.get_key(key).get_value_type().dup_string() == "as":
                keep = [EXIT_PATH] if (schema_id, key) == (MEDIA_KEYS, "custom-keybindings") else []
                yield schema_id, key, GLib.Variant("as", keep)
    for schema_id, key, value in SINGLE_KEYS:
        if _schema_exists(schema_id):
            schema = src.lookup(schema_id, True)
            if schema.has_key(key):
                yield schema_id, key, value


def lock_settings():
    os.makedirs(STATE_DIR, exist_ok=True)
    if os.path.exists(BACKUP_FILE):
        # A previous run died without restoring; restore first so we never
        # back up the "locked" values as if they were the real ones.
        restore_settings()
    changes = list(_planned_changes())
    backup = []
    settings_cache = {}
    for schema_id, key, _ in changes:
        s = settings_cache.setdefault(schema_id, Gio.Settings.new(schema_id))
        v = s.get_value(key)
        backup.append([schema_id, key, v.get_type_string(), v.print_(False)])
    tmp = BACKUP_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(backup, f)
    os.replace(tmp, BACKUP_FILE)
    _set_exit_shortcut(True)
    for schema_id, key, value in changes:
        settings_cache[schema_id].set_value(key, value)
    Gio.Settings.sync()


def _set_exit_shortcut(on):
    if not _schema_exists(MEDIA_KEYS + ".custom-keybinding"):
        return
    s = Gio.Settings.new_with_path(MEDIA_KEYS + ".custom-keybinding", EXIT_PATH)
    if on:
        s.set_string("name", "Quit Toddler Desk")
        s.set_string("command", f"{sys.executable} {os.path.abspath(__file__)} --quit")
        s.set_string("binding", EXIT_BINDING)
    else:
        for key in ("name", "command", "binding"):
            s.reset(key)


def restore_settings():
    if not os.path.exists(BACKUP_FILE):
        return
    with open(BACKUP_FILE) as f:
        backup = json.load(f)
    cache = {}
    for schema_id, key, type_str, text in backup:
        try:
            s = cache.setdefault(schema_id, Gio.Settings.new(schema_id))
            s.set_value(key, GLib.Variant.parse(GLib.VariantType.new(type_str), text, None, None))
        except Exception as e:  # keep going; restore as much as possible
            print(f"restore failed for {schema_id} {key}: {e}", file=sys.stderr)
    _set_exit_shortcut(False)
    Gio.Settings.sync()
    os.remove(BACKUP_FILE)


def quit_running():
    """Ask a running Toddler Desk to exit (it restores settings itself)."""
    try:
        with open(PID_FILE) as f:
            pid = int(f.read())
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            if b"toddler_desk.py" not in f.read():
                return False
        os.kill(pid, signal.SIGTERM)
        return True
    except (OSError, ValueError):
        return False


def start_power_inhibitor():
    """Block power/suspend/hibernate keys and lid switch while we're alive.

    `tail --pid` exits when this process dies, so the inhibitor can't leak.
    """
    try:
        return subprocess.Popen(
            [
                "systemd-inhibit",
                "--what=handle-power-key:handle-suspend-key:handle-hibernate-key:handle-lid-switch:idle:sleep",
                "--who=Toddler Desk",
                "--why=Toddler is working",
                "--mode=block",
                "tail", f"--pid={os.getpid()}", "-f", "/dev/null",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None


# ------------------------------------------------------------------ the "work"

# Each key press reveals the next letter of a report. Reports live in
# reports/*.md next to this file: a "# Title" line, then the story text.
REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
FALLBACK_REPORT = ("Fixing the Tractor",
                   "The tractor was broked. It went clunk clunk. I got my spanner. "
                   "Now it goes brum brum. Job done.")


def load_reports():
    reports = []
    try:
        names = sorted(n for n in os.listdir(REPORTS_DIR) if n.endswith(".md"))
    except OSError:
        names = []
    for name in names:
        try:
            with open(os.path.join(REPORTS_DIR, name), encoding="utf-8") as f:
                lines = [ln.strip() for ln in f]
        except OSError:
            continue
        title = os.path.splitext(name)[0]
        body = []
        for ln in lines:
            if ln.startswith("#") and not body:
                title = ln.lstrip("#").strip()
            elif ln:
                body.append(ln)
        text = " ".join(body)
        if text:
            reports.append((title, text))
    return reports or [FALLBACK_REPORT]


# Muted palette - deliberately unexciting.
# Warm off-white, like a screen with f.lux on: low blue, nothing pure white.
BG = (0.89, 0.85, 0.77)
PAPER = (0.97, 0.94, 0.87)
INK = (0.29, 0.25, 0.21)
DIM = (0.55, 0.49, 0.42)
BAR_BG = (0.83, 0.78, 0.69)
BAR_FG = (0.64, 0.56, 0.45)
WAITING = (0.92, 0.86, 0.74)  # the rest of a tapped sentence, before it's read
READING = (0.86, 0.75, 0.56)  # the word being said now
RIPPLE = (0.45, 0.39, 0.32)
# Pictures are drawn in a warm greyscale (sepia-ish) to match.
WARM = (1.0, 0.93, 0.80)


def _sentences(story):
    """(start, end) of each sentence in the story, end just after its . ! or ?"""
    return [(m.start(), m.end()) for m in re.finditer(r"\S.*?(?:[.!?](?=\s|$)|$)", story)]


def _rgba(c, a=1.0):
    v = Gdk.RGBA()
    v.red, v.green, v.blue, v.alpha = c[0], c[1], c[2], a
    return v


def _rect(x, y, w, h):
    r = Graphene.Rect()
    return r.init(x, y, w, h)


class Desk(Gtk.Widget):
    def __init__(self):
        super().__init__()
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.text = ""
        self.report_no = random.randint(100, 400)
        self.reports = load_reports()
        self.queue = []
        self._next_report()
        self.progress = 0.0
        self.saved_until = 0.0
        self.ripples = []  # (x, y, t0)
        self.last_input = 0.0
        self.letter = ""  # most recent letter, shown as "Hh"
        self.icon_rect = self.letter_rect = None
        self.prompt = None  # (X, Y) while the "close?" line is showing
        self.text_box = None  # (layout, x, y, clip rect) of the written text, for taps
        self.reading = None  # see read_from()
        self.read_id = 0
        self.stats = {"frames": [], "tick_late": 0.0, "keys": 0, "taps": 0}
        self.last_tick = time.monotonic()
        GLib.timeout_add(50, self.tick)

    def _next_report(self):
        if not self.queue:
            self.queue = random.sample(self.reports, len(self.reports))
        self.title, self.story = self.queue.pop()
        if not self.queue:  # always know the next report, to prepare it early
            self.queue = random.sample(self.reports, len(self.reports))
        self.text = ""
        self.reading = None
        self.progress = 0.0
        self.sentences = _sentences(self.story)
        log.info("report: %r, %d sentences, %d chars", self.title, len(self.sentences), len(self.story))
        self.prepped = {t for t in getattr(self, "prepped", ()) if t in self.story}
        self._prepare_sentences()
        # Until a picture word is being written, show the title's picture.
        self.icon = next(filter(None, map(icon_for, reversed(self.title.split()))), None)
        if self.icon:
            speech.prepare_word(self.icon[0])
        self._prepare_next_icon(0)

    def _prepare_next_icon(self, pos):
        """Make the clip for the next picture word after `pos` before it shows up,
        so tapping it plays straight away instead of waiting ~1.5 s."""
        for word in self.story[pos:].split():
            found = icon_for(word)
            if found and found != self.icon:
                speech.prepare_word(found[0])
                return

    def _prepare_sentences(self):
        """Make the clips for the sentence being written and the next one (on
        the last sentence: the next report's first), so a tap on any word plays
        at once. The voice makes one clip per word position."""
        n = len(self.text)
        for k, (a, b) in enumerate(self.sentences):
            if b > n:  # the sentence being written (none finished just now)
                ahead = [self.story[a2:b2] for a2, b2 in self.sentences[k:k + 2]]
                if len(ahead) < 2 and self.queue:
                    nxt = self.queue[-1][1]
                    ahead += [nxt[a2:b2] for a2, b2 in _sentences(nxt)[:1]]
                for text in ahead:
                    if text not in self.prepped:
                        self.prepped.add(text)
                        speech.prepare_sentence(text)
                return

    def _write_more(self):
        """Reveal the next letter (and any spaces before it)."""
        if self.saved_until:
            return  # brief pause while "saving"
        n = len(self.text)
        n += 1
        while n < len(self.story) and self.story[n - 1] == " ":
            n += 1
        self.text = self.story[:n]
        self.progress = n / len(self.story)
        # The word being written: from the last space up to the end of it.
        start = self.text.rfind(" ") + 1
        end = self.story.find(" ", start)
        found = icon_for(self.story[start:end if end != -1 else None])
        if found and found != self.icon:
            self.icon = found
            speech.prepare_word(found[0])  # normally made already, see below
            self._prepare_next_icon(end if end != -1 else len(self.story))
        if self.text[-1].isalnum():
            self.letter = self.text[-1]
        if self.text[-1] in ".!?":
            self._prepare_sentences()
        if n >= len(self.story):
            self.progress = 1.0
            self.saved_until = time.monotonic() + 2.5

    # -- input ---------------------------------------------------------------
    def key(self, keyval):
        self.stats["keys"] += 1
        name = Gdk.keyval_name(keyval) or ""
        if name.endswith(("_L", "_R")):
            return  # bare modifiers do nothing
        self.last_input = time.monotonic()
        self._write_more()
        ch = Gdk.keyval_to_unicode(keyval)
        if ch and chr(ch).isascii() and chr(ch).isalnum():
            self.letter = chr(ch)  # show the key they actually pressed
        self.queue_draw()

    @staticmethod
    def _inside(rect, x, y):
        return rect and rect[0] <= x <= rect[0] + rect[2] and rect[1] <= y <= rect[1] + rect[3]

    def click(self, x, y):
        self.last_input = time.monotonic()
        self.ripples.append((x, y, time.monotonic()))
        self.stats["taps"] += 1
        if self._inside(self.icon_rect, x, y):
            if self.icon:
                log.info("tap picture: %s", self.icon[0])
                self.reading = None
                speech.say_word(self.icon[0])
        elif self._inside(self.letter_rect, x, y):
            if self.letter:
                log.info("tap letter: %s", self.letter)
                self.reading = None
                speech.say_letter(self.letter)
        elif not self.read_from(x, y):
            self._write_more()
        self.queue_draw()

    # -- reading the writing aloud -------------------------------------------
    def _word_at(self, x, y):
        """(start, end) of the fully written word under (x, y), or None."""
        if not self.text_box:
            return None
        layout, ox, oy, clip = self.text_box
        if not self._inside(clip, x, y):
            return None
        inside, byte, _ = layout.xy_to_index(int((x - ox) * Pango.SCALE), int((y - oy) * Pango.SCALE))
        if not inside:
            return None
        i = len(layout.get_text().encode()[:byte].decode(errors="ignore"))
        t = self.text
        if i >= len(t) or t[i].isspace():
            return None
        a = i
        while a > 0 and not t[a - 1].isspace():
            a -= 1
        b = i
        while b < len(t) and not t[b].isspace():
            b += 1
        if b == len(t) and b < len(self.story) and not self.story[b].isspace():
            return None  # still being written
        return a, b

    def read_from(self, x, y):
        """Tap on a word: read from there to the end of its sentence.

        The whole report is known, so a sentence still being written is read
        to its end too, from the clip made ahead; words not on screen yet are
        heard but have nothing to highlight (until they're typed).
        """
        word = self._word_at(x, y)
        if not word:
            return False
        sa, sb = next(sp for sp in self.sentences if sp[0] <= word[0] < sp[1])
        words = [(sa + m.start(), sa + m.end()) for m in re.finditer(r"\S+", self.story[sa:sb])]
        first = next(i for i, w in enumerate(words) if w[0] == word[0])
        self.read_id += 1
        log.info("tap word: read %d = %r", self.read_id,
                 " ".join(self.story[a:b] for a, b in words[first:]))
        self.reading = {"id": self.read_id, "ranges": words[first:], "asked": time.monotonic(),
                        "starts": None, "t0": 0.0, "end": 0.0}
        speech.read(self.read_id, first, len(words), self.story[sa:sb])
        return True

    def on_voice(self, line):
        """A line from the voice process."""
        kind, _, rest = line.partition(" ")
        rid, _, data = rest.partition(" ")
        r = self.reading
        if kind in ("reading", "noread"):
            if r and str(r["id"]) == rid:
                log.info("read %s %s after %.2f s", rid, "started" if kind == "reading" else "FAILED",
                         time.monotonic() - r["asked"])
            else:
                log.info("read %s answered (%s) but no longer wanted", rid, kind)
        if not r or str(r["id"]) != rid:
            return
        if kind == "reading":
            times, _, dur = data.partition(";")
            r["starts"] = [float(v) for v in times.split(",")]
            r["end"] = float(dur or 0) or r["starts"][-1] + 0.6
            r["t0"] = time.monotonic()
        else:  # couldn't read it
            self.reading = None
        self.queue_draw()

    def _reading_now(self):
        """(word ranges to tint as waiting, range being said) for drawing;
        only the parts already written."""
        n = len(self.text)
        waiting, current = self._reading_ranges()
        on_screen = lambda rng: rng and rng[0] < n and (rng[0], min(rng[1], n))  # noqa: E731
        return [x for x in map(on_screen, waiting) if x], on_screen(current) or None

    def _reading_ranges(self):
        r = self.reading
        if not r:
            return [], None
        now = time.monotonic()
        if r["starts"] is None:
            if now - r["asked"] > 15:  # the voice never answered
                self.reading = None
                return [], None
            return r["ranges"][1:], r["ranges"][0]  # tapped word lit at once
        t = now - r["t0"]
        if t > r["end"]:
            self.reading = None
            return [], None
        k = max((i for i, st in enumerate(r["starts"]) if st <= t), default=0)
        k = min(k, len(r["ranges"]) - 1)
        return r["ranges"][k + 1:], r["ranges"][k]

    def _shade(self, snap, layout, ox, oy, rng, color):
        text = layout.get_text()
        pad = 2
        for i in range(*rng):
            byte = len(text[:i].encode())
            pos = layout.index_to_pos(byte)
            x, y = ox + pos.x / Pango.SCALE, oy + pos.y / Pango.SCALE
            w, h = pos.width / Pango.SCALE, pos.height / Pango.SCALE
            snap.append_color(_rgba(color), _rect(x - pad, y, w + 2 * pad, h))

    def tick(self):
        now = time.monotonic()
        late = now - self.last_tick - 0.05
        self.stats["tick_late"] = max(self.stats["tick_late"], late)
        if late > 0.25:
            log.info("main loop stalled: tick %.0f ms late", late * 1000)
        self.last_tick = now
        self.ripples = [r for r in self.ripples if now - r[2] < 0.7]
        if self.saved_until and now >= self.saved_until:
            self.saved_until = 0.0
            self.report_no += 1
            self._next_report()
        self.queue_draw()
        return True

    # -- drawing -------------------------------------------------------------
    def _text(self, snap, text, size, x, y, color, mono=False, width=None):
        layout = self.create_pango_layout(text)
        layout.set_font_description(
            Pango.FontDescription.from_string(("Monospace " if mono else "Sans ") + str(size)))
        if width:
            layout.set_width(int(width * Pango.SCALE))
            layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        snap.save()
        snap.translate(Graphene.Point().init(x, y))
        snap.append_layout(layout, _rgba(color))
        snap.restore()
        return layout

    def _draw_icon(self, snap, emoji, x, y, size):
        """Draw an emoji centred in a square, in greyscale."""
        lay = self.create_pango_layout(emoji)
        lay.set_font_description(Pango.FontDescription.from_string(f"Noto Color Emoji {int(size * 0.45)}"))
        _, ext = lay.get_pixel_extents()
        m = Graphene.Matrix()
        # rows = input channel; every output colour gets the same luminance
        m.init_from_float([v * w for v in (0.30, 0.59, 0.11) for w in WARM + (0,)][:12]
                          + [0, 0, 0, 1])
        snap.push_color_matrix(m, Graphene.Vec4().init(0, 0, 0, 0))
        snap.save()
        snap.translate(Graphene.Point().init(x + (size - ext.width) / 2 - ext.x,
                                             y + (size - ext.height) / 2 - ext.y))
        snap.append_layout(lay, _rgba(INK))
        snap.restore()
        snap.pop()

    def do_snapshot(self, snap):
        t0 = time.monotonic()
        self._snapshot(snap)
        took = time.monotonic() - t0
        self.stats["frames"].append(took)
        if took > 0.05:
            log.info("slow frame: %.0f ms (text %d chars)", took * 1000, len(self.text))

    def _snapshot(self, snap):
        w, h = self.get_width(), self.get_height()
        now = time.monotonic()
        snap.append_color(_rgba(BG), _rect(0, 0, w, h))

        px, py = w * 0.06, h * 0.12
        pw, ph = w * 0.62, h * 0.62
        small = max(10, int(h / 60))

        self._text(snap, f"Report No. {self.report_no} \u2014 {self.title}", small, px, py - h * 0.05, DIM)
        snap.append_color(_rgba(PAPER), _rect(px, py, pw, ph))

        # text, wrapped, scrolled so the end is visible
        pad = w * 0.02
        size = max(11, int(h / 42))
        cursor = "\u258f" if int(now * 2) % 2 == 0 else " "
        layout = self.create_pango_layout(self.text + cursor)
        layout.set_font_description(Pango.FontDescription.from_string(f"Monospace {size}"))
        layout.set_width(int((pw - 2 * pad) * Pango.SCALE))
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        _, logical = layout.get_pixel_extents()
        avail = ph - 2 * pad
        offset = max(0, logical.height - avail)
        clip = (px, py + pad, pw, avail)
        ox, oy = px + pad, py + pad - offset
        self.text_box = (layout, ox, oy, clip)
        snap.push_clip(_rect(*clip))
        waiting, current = self._reading_now()
        for rng in waiting:
            self._shade(snap, layout, ox, oy, rng, WAITING)
        if current:
            self._shade(snap, layout, ox, oy, current, READING)
        snap.save()
        snap.translate(Graphene.Point().init(ox, oy))
        snap.append_layout(layout, _rgba(INK))
        snap.restore()
        snap.pop()

        # progress bar + status
        by = py + ph + h * 0.05
        bh = max(8, h * 0.018)
        snap.append_color(_rgba(BAR_BG), _rect(px, by, pw, bh))
        if self.progress > 0:
            snap.append_color(_rgba(BAR_FG), _rect(px, by, pw * self.progress, bh))
        if self.saved_until:
            status = "Saved."
        elif now - self.last_input < 1.5:
            status = f"Working\u2026 {int(self.progress * 100)}%"
        else:
            status = f"{int(self.progress * 100)}%"
        self._text(snap, status, small, px, by + bh + h * 0.015, DIM)

        # side panel: picture of the current word, then the latest letter
        sx = px + pw + w * 0.04
        sw = w - sx - w * 0.06
        card = min(sw, ph * 0.58)
        cx = sx + (sw - card) / 2
        self.icon_rect = (cx, py, card, card)
        snap.append_color(_rgba(PAPER), _rect(*self.icon_rect))
        if self.icon:
            # picture in the upper part, its word underneath
            self._draw_icon(snap, self.icon[1], cx + card * 0.1, py + card * 0.02, card * 0.8)
            lay = self.create_pango_layout(self.icon[0])
            lay.set_font_description(Pango.FontDescription.from_string(f"Sans {max(10, int(card * 0.075))}"))
            _, ext = lay.get_pixel_extents()
            snap.save()
            snap.translate(Graphene.Point().init(cx + (card - ext.width) / 2 - ext.x,
                                                 py + card * 0.86 - ext.height / 2 - ext.y))
            snap.append_layout(lay, _rgba(INK))
            snap.restore()
        ly = py + card + ph * 0.06
        lh = ph - card - ph * 0.06
        self.letter_rect = (cx, ly, card, lh)
        snap.append_color(_rgba(PAPER), _rect(*self.letter_rect))
        if self.letter:
            pair = self.letter.upper() + self.letter.lower() if self.letter.isalpha() else self.letter
            lay = self.create_pango_layout(pair)
            lay.set_font_description(Pango.FontDescription.from_string(f"Sans {max(12, int(lh * 0.42))}"))
            _, ext = lay.get_pixel_extents()
            snap.save()
            snap.translate(Graphene.Point().init(cx + (card - ext.width) / 2 - ext.x,
                                                 ly + (lh - ext.height) / 2 - ext.y))
            snap.append_layout(lay, _rgba(INK))
            snap.restore()

        # click ripples: faint grey rings
        for x, y, t0 in self.ripples:
            t = (now - t0) / 0.7
            r = 8 + 30 * t
            rr = Gsk.RoundedRect()
            rr.init_from_rect(_rect(x - r, y - r, 2 * r, 2 * r), r)
            c = _rgba(RIPPLE, 0.3 * (1 - t))
            snap.append_border(rr, [2, 2, 2, 2], [c, c, c, c])

        if self.prompt:
            self._draw_prompt(snap, w, h)

    def _draw_prompt(self, snap, w, h):
        """A quiet line of text in the top-right corner."""
        x, y = self.prompt
        lay = self.create_pango_layout(f"If you want to close, press {x} and {y} together.")
        lay.set_font_description(Pango.FontDescription.from_string(f"Sans {max(10, int(h / 60))}"))
        _, ext = lay.get_pixel_extents()
        snap.save()
        snap.translate(Graphene.Point().init(w * 0.98 - ext.width - ext.x, h * 0.02 - ext.y))
        snap.append_layout(lay, _rgba(DIM))
        snap.restore()


# ------------------------------------------------------------------- app shell

class ToddlerDesk(Gtk.Application):
    def __init__(self, test_mode=False):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.test_mode = test_mode
        self.allow_quit = False
        self.held = set()
        self.p_pressed_at = 0.0
        self.esc_count = 0
        self.esc_at = 0.0
        self.prompt_down = set()
        self.prompt_timer = 0
        self.inhibitor = None
        self.connect("activate", self.on_activate)

    def on_activate(self, _app):
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            _signal_add(GLib.PRIORITY_HIGH, sig, self.quit_for_real)
        if not self.test_mode:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(PID_FILE, "w") as f:
                f.write(str(os.getpid()))
            lock_settings()
            self.inhibitor = start_power_inhibitor()
            speech.start()

        win = Gtk.ApplicationWindow(application=self, title="Toddler Desk")
        self.win = win
        win.set_decorated(False)
        win.set_cursor(Gdk.Cursor.new_from_name("default", None))
        self.desk = Desk()
        win.set_child(self.desk)
        speech.on_line(self.desk.on_voice)
        self._cpu_prev = {}
        GLib.timeout_add_seconds(60, self._log_stats)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key_pressed)
        keys.connect("key-released", self.on_key_released)
        win.add_controller(keys)

        click = Gtk.GestureClick()
        click.set_button(0)
        click.connect("pressed", self.on_click)
        win.add_controller(click)

        win.connect("close-request", lambda _w: not self.allow_quit)
        win.connect("notify::is-active", self.on_active_changed)
        win.connect("map", self.on_map)
        win.connect("notify::fullscreened", self.on_fullscreen_changed)

        self.inhibit(win, Gtk.ApplicationInhibitFlags.IDLE | Gtk.ApplicationInhibitFlags.SUSPEND
                     | Gtk.ApplicationInhibitFlags.LOGOUT | Gtk.ApplicationInhibitFlags.SWITCH,
                     "Toddler is working")

        if not self.test_mode:
            self._watch_overview()

        if self.test_mode:
            win.set_default_size(900, 600)
            GLib.timeout_add(3000, self.quit_for_real)
        else:
            win.fullscreen()
        win.present()

    def on_map(self, win):
        if self.test_mode:
            return
        surface = win.get_surface()
        if isinstance(surface, Gdk.Toplevel):
            surface.inhibit_system_shortcuts(None)

    def on_fullscreen_changed(self, win, _pspec):
        # GNOME's touchscreen "drag down from the top edge" un-fullscreens the
        # focused window, revealing the top bar. Put it straight back.
        if not win.is_fullscreen() and not self.allow_quit and not self.test_mode:
            GLib.idle_add(win.fullscreen)

    def _watch_overview(self):
        """Close the GNOME overview whenever a touchpad/touchscreen swipe opens it."""
        try:
            self.shell = Gio.DBusProxy.new_for_bus_sync(
                Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
                "org.gnome.Shell", "/org/gnome/Shell", "org.gnome.Shell", None)
        except GLib.Error:
            self.shell = None
            return
        self.shell.connect("g-properties-changed", lambda *_: self._close_overview())
        GLib.timeout_add(500, self._close_overview)  # belt and braces

    def _close_overview(self):
        if self.allow_quit:
            return False
        active = self.shell.get_cached_property("OverviewActive")
        if active is not None and active.unpack():
            self.shell.call(
                "org.freedesktop.DBus.Properties.Set",
                GLib.Variant("(ssv)", ("org.gnome.Shell", "OverviewActive", GLib.Variant("b", False))),
                Gio.DBusCallFlags.NONE, -1, None, None)
            GLib.timeout_add(300, self._refocus)
        return True

    def on_active_changed(self, win, _pspec):
        # Lost focus (e.g. touchpad gesture opened the overview): forget held
        # keys and try to come back to the front.
        self.held.clear()
        if not win.is_active() and not self.allow_quit and not self.test_mode:
            GLib.timeout_add(300, self._refocus)

    def _refocus(self):
        if not self.allow_quit and not self.win.is_active():
            self.win.fullscreen()
            self.win.present()
        return False

    # -- the secret exit -----------------------------------------------------
    ALT_KEYS = {Gdk.KEY_Alt_L, Gdk.KEY_Alt_R, Gdk.KEY_ISO_Level3_Shift, Gdk.KEY_Meta_L, Gdk.KEY_Meta_R}

    def _base_key(self, keyval, keycode):
        """The key's plain (unshifted) letter, so AltGr/Shift levels don't matter."""
        ok, base, *_ = Gdk.Display.get_default().translate_key(keycode, 0, 0)
        return Gdk.keyval_to_lower(base if ok else keyval)

    def _log_stats(self):
        d = self.desk
        st = d.stats
        frames = st["frames"] or [0.0]
        parts = [f"frames {len(st['frames'])}, draw avg {1000 * sum(frames) / len(frames):.1f} ms "
                 f"max {1000 * max(frames):.0f} ms, tick late max {1000 * st['tick_late']:.0f} ms, "
                 f"keys {st['keys']}, taps {st['taps']}, text {len(d.text)} chars"]
        for name, pid in (("app", os.getpid()), ("voice", speech.pid())):
            if pid:
                cpu = _cpu_seconds(pid)
                used = cpu - self._cpu_prev.get(name, cpu)
                self._cpu_prev[name] = cpu
                parts.append(f"{name} {_rss_mb(pid):.0f} MB, cpu {100 * used / 60:.0f}%")
        log.info("stats: " + "; ".join(parts))
        d.stats = {"frames": [], "tick_late": 0.0, "keys": 0, "taps": 0}
        return True

    def on_click(self, _gesture, _n, x, y):
        if self.desk.prompt:
            self._dismiss_prompt()
        else:
            self.desk.click(x, y)

    def on_key_pressed(self, _ctrl, keyval, keycode, state):
        t0 = time.monotonic()
        try:
            return self._on_key_pressed(keyval, keycode, state)
        finally:
            took = time.monotonic() - t0
            if took > 0.05:
                log.info("slow key handler: %.0f ms", took * 1000)

    def _on_key_pressed(self, keyval, keycode, state):
        repeat = keyval in self.held  # auto-repeat from a key held down
        self.held.add(keyval)
        k = self._base_key(keyval, keycode)

        if self.desk.prompt:
            self._prompt_key(k, repeat)
            return True

        mods = Gdk.ModifierType
        alt = bool(state & mods.ALT_MASK) or bool(self.held & self.ALT_KEYS)  # left Alt or AltGr
        if alt and state & mods.CONTROL_MASK and state & mods.SHIFT_MASK:
            now = time.monotonic()
            if k == Gdk.KEY_p:
                self.p_pressed_at = now
            if k == Gdk.KEY_i and now - self.p_pressed_at < 3:
                self.quit_for_real()
                return True

        if not repeat and self._count_esc(keyval):
            return True
        self.desk.key(keyval)
        return True  # swallow everything

    def on_key_released(self, _ctrl, keyval, keycode, _state):
        self.held.discard(keyval)
        if self.desk.prompt and self._base_key(keyval, keycode) in self.prompt_down:
            self._dismiss_prompt()  # let go before both were down

    # -- the second exit: Esc x8, then a random pair of letters ---------------
    ESC_TAPS = 8

    def _count_esc(self, keyval):
        """Count separate Esc taps in a row; True once the prompt opens."""
        if keyval != Gdk.KEY_Escape:
            name = Gdk.keyval_name(keyval) or ""
            if not name.endswith(("_L", "_R")):
                self.esc_count = 0
            return False
        now = time.monotonic()
        self.esc_count = self.esc_count + 1 if now - self.esc_at < 1.5 else 1
        self.esc_at = now
        if self.esc_count < self.ESC_TAPS:
            return False
        self.esc_count = 0
        a, b = random.sample("ABCDEFGHIJKLMNOPQRSTUVWXYZ", 2)
        self.desk.prompt = (a, b)
        self.prompt_down = set()
        self.prompt_timer = GLib.timeout_add_seconds(15, self._prompt_timed_out)
        self.desk.queue_draw()
        return True

    def _prompt_key(self, k, repeat):
        pair = {Gdk.unicode_to_keyval(ord(c.lower())) for c in self.desk.prompt}
        if k in pair:
            self.prompt_down.add(k)
            if self.prompt_down == pair:
                self.quit_for_real()
        elif not repeat:
            self._dismiss_prompt()  # any other key: not a grown-up

    def _prompt_timed_out(self):
        self.prompt_timer = 0  # this source ends itself by returning False
        return self._dismiss_prompt()

    def _dismiss_prompt(self):
        if self.prompt_timer:
            GLib.source_remove(self.prompt_timer)
            self.prompt_timer = 0
        self.desk.prompt = None
        self.prompt_down = set()
        self.desk.queue_draw()
        return False

    def quit_for_real(self):
        if self.allow_quit:
            return False
        log.info("quitting")
        self.allow_quit = True
        self.shutdown_cleanup()
        self.quit()
        return False

    def shutdown_cleanup(self):
        speech.stop()
        if self.inhibitor and self.inhibitor.poll() is None:
            self.inhibitor.terminate()
        if not self.test_mode:
            restore_settings()
            try:
                os.remove(PID_FILE)
            except OSError:
                pass


def main():
    if "--quit" in sys.argv:
        return 0 if quit_running() else 1
    if "--restore" in sys.argv:
        restore_settings()
        print("GNOME settings restored.")
        return 0
    setup_logging("--test" in sys.argv)
    app = ToddlerDesk(test_mode="--test" in sys.argv)
    try:
        return app.run([sys.argv[0]])
    finally:
        app.shutdown_cleanup()


if __name__ == "__main__":
    sys.exit(main())
