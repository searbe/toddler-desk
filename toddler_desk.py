#!/usr/bin/env python3
"""Toddler Desk - a calm, boring, full-screen "work" screen for small hands.

Keys type into a pretend report; a progress bar fills and the report gets
"saved". Clicks leave a faint ripple. Nothing flashy, no sounds.

Exit:  hold Ctrl + Alt + Shift, then press P and I (together, or P then I).

While running it:
  * inhibits GNOME system shortcuts (GNOME asks you to "Allow" once),
  * temporarily blanks GNOME keybindings, the Super key, hot corner,
    notification banners, accessibility hotkeys and the power-button action,
  * holds a systemd inhibitor for the power/suspend/hibernate keys and lid,
and puts every setting back on exit. If it ever dies uncleanly, run
`toddler_desk.py --restore` (the launcher script does this automatically).
"""

import json
import os
import random
import subprocess
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, Gio, GLib, Graphene, Gsk, Gtk, Pango  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import speech  # noqa: E402
from icons import icon_for  # noqa: E402

APP_ID = "org.home.ToddlerDesk"
STATE_DIR = os.path.join(
    os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")), "toddler-desk"
)
BACKUP_FILE = os.path.join(STATE_DIR, "settings-backup.json")

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
                yield schema_id, key, GLib.Variant("as", [])
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
    for schema_id, key, value in changes:
        settings_cache[schema_id].set_value(key, value)
    Gio.Settings.sync()


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
    Gio.Settings.sync()
    os.remove(BACKUP_FILE)


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
BG = (0.17, 0.19, 0.21)
PAPER = (0.86, 0.85, 0.82)
INK = (0.25, 0.27, 0.30)
DIM = (0.55, 0.58, 0.61)
BAR_BG = (0.26, 0.29, 0.32)
BAR_FG = (0.45, 0.53, 0.60)


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
        GLib.timeout_add(50, self.tick)

    def _next_report(self):
        if not self.queue:
            self.queue = random.sample(self.reports, len(self.reports))
        self.title, self.story = self.queue.pop()
        self.text = ""
        self.progress = 0.0
        # Until a picture word is being written, show the title's picture.
        self.icon = next(filter(None, map(icon_for, reversed(self.title.split()))), None)

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
        if found:
            self.icon = found
        if self.text[-1].isalnum():
            self.letter = self.text[-1]
        if n >= len(self.story):
            self.progress = 1.0
            self.saved_until = time.monotonic() + 2.5

    # -- input ---------------------------------------------------------------
    def key(self, keyval):
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
        if self._inside(self.icon_rect, x, y):
            if self.icon:
                speech.say_word(self.icon[0])
        elif self._inside(self.letter_rect, x, y):
            if self.letter:
                speech.say_letter(self.letter)
        else:
            self._write_more()
        self.queue_draw()

    def tick(self):
        now = time.monotonic()
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
        m.init_from_float([0.30, 0.30, 0.30, 0, 0.59, 0.59, 0.59, 0,
                           0.11, 0.11, 0.11, 0, 0, 0, 0, 1])
        snap.push_color_matrix(m, Graphene.Vec4().init(0, 0, 0, 0))
        snap.save()
        snap.translate(Graphene.Point().init(x + (size - ext.width) / 2 - ext.x,
                                             y + (size - ext.height) / 2 - ext.y))
        snap.append_layout(lay, _rgba(INK))
        snap.restore()
        snap.pop()

    def do_snapshot(self, snap):
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
        snap.push_clip(_rect(px, py + pad, pw, avail))
        snap.save()
        snap.translate(Graphene.Point().init(px + pad, py + pad - offset))
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
            c = _rgba((0.8, 0.8, 0.8), 0.35 * (1 - t))
            snap.append_border(rr, [2, 2, 2, 2], [c, c, c, c])


# ------------------------------------------------------------------- app shell

class ToddlerDesk(Gtk.Application):
    def __init__(self, test_mode=False):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.test_mode = test_mode
        self.allow_quit = False
        self.held = set()
        self.p_pressed_at = 0.0
        self.inhibitor = None
        self.connect("activate", self.on_activate)

    def on_activate(self, _app):
        if not self.test_mode:
            lock_settings()
            self.inhibitor = start_power_inhibitor()

        win = Gtk.ApplicationWindow(application=self, title="Toddler Desk")
        self.win = win
        win.set_decorated(False)
        win.set_cursor(Gdk.Cursor.new_from_name("default", None))
        self.desk = Desk()
        win.set_child(self.desk)

        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_key_pressed)
        keys.connect("key-released", self.on_key_released)
        win.add_controller(keys)

        click = Gtk.GestureClick()
        click.set_button(0)
        click.connect("pressed", lambda _g, _n, x, y: self.desk.click(x, y))
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
    def on_key_pressed(self, _ctrl, keyval, _keycode, state):
        k = Gdk.keyval_to_lower(keyval)
        self.held.add(k)
        mods = Gdk.ModifierType
        need = mods.CONTROL_MASK | mods.ALT_MASK | mods.SHIFT_MASK
        if (state & need) == need:
            now = time.monotonic()
            if k == Gdk.KEY_p:
                self.p_pressed_at = now
            if k == Gdk.KEY_i and (Gdk.KEY_p in self.held or now - self.p_pressed_at < 1.5):
                self.quit_for_real()
                return True
        self.desk.key(keyval)
        return True  # swallow everything

    def on_key_released(self, _ctrl, keyval, _keycode, _state):
        self.held.discard(Gdk.keyval_to_lower(keyval))

    def quit_for_real(self):
        self.allow_quit = True
        self.shutdown_cleanup()
        self.quit()
        return False

    def shutdown_cleanup(self):
        if self.inhibitor and self.inhibitor.poll() is None:
            self.inhibitor.terminate()
        if not self.test_mode:
            restore_settings()


def main():
    if "--restore" in sys.argv:
        restore_settings()
        print("GNOME settings restored.")
        return 0
    app = ToddlerDesk(test_mode="--test" in sys.argv)
    try:
        return app.run([sys.argv[0]])
    finally:
        app.shutdown_cleanup()


if __name__ == "__main__":
    sys.exit(main())
