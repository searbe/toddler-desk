"""Speak letters and picture words via the live Kokoro voice (voice.py).

voice.py runs as a child process inside tts/venv so the app itself needs no
extra Python packages. If the voice isn't set up, the app is simply silent.
"""

import os
import subprocess

from gi.repository import GLib

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, "tts", "venv", "bin", "python")

_proc = None
_listeners = []


def on_line(callback):
    """Call callback(line) for each line the voice prints (e.g. "reading ...")."""
    _listeners.append(callback)


def _readable(stream, cond):
    line = stream.readline() if cond & GLib.IOCondition.IN else ""
    if not line:
        return False  # voice has gone
    for cb in _listeners:
        cb(line.strip())
    return True


def start():
    """Start the voice in the background (loads the model, warms up letters)."""
    global _proc
    if _proc or not os.path.exists(VENV_PY):
        return
    try:
        _proc = subprocess.Popen([VENV_PY, os.path.join(HERE, "voice.py"), "--serve"],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True, bufsize=1)
        GLib.io_add_watch(_proc.stdout, GLib.PRIORITY_DEFAULT,
                          GLib.IOCondition.IN | GLib.IOCondition.HUP, _readable)
    except OSError:
        _proc = None


def _send(line):
    global _proc
    if not _proc or _proc.poll() is not None:
        return
    try:
        _proc.stdin.write(line + "\n")
        _proc.stdin.flush()
    except (BrokenPipeError, OSError):
        _proc = None


def say_letter(ch):
    _send(f"say letter {ch.lower()}")


def say_word(word):
    _send(f"say word {word.lower()}")


def read(read_id, first, last, sentence):
    """Say words first..last-1 of a sentence; the voice answers "reading <id> ..."."""
    if not _proc or _proc.poll() is not None:
        for cb in _listeners:  # no voice: let the highlight go straight away
            cb(f"noread {read_id}")
        return
    _send(f"read {read_id} {first} {last} " + " ".join(sentence.split()))


def prepare_sentence(sentence):
    """Make a sentence's clip ahead of time so taps on its words play at once."""
    _send("prep sentence " + " ".join(sentence.split()))


def prepare_word(word):
    """Make the clip ahead of time so a tap plays instantly."""
    _send(f"prep word {word.lower()}")


def stop():
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
    _proc = None
