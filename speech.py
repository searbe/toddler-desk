"""Speak letters and picture words via the live Kokoro voice (voice.py).

voice.py runs as a child process inside tts/venv so the app itself needs no
extra Python packages. If the voice isn't set up, the app is simply silent.
"""

import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, "tts", "venv", "bin", "python")

_proc = None


def start():
    """Start the voice in the background (loads the model, warms up letters)."""
    global _proc
    if _proc or not os.path.exists(VENV_PY):
        return
    try:
        _proc = subprocess.Popen([VENV_PY, os.path.join(HERE, "voice.py"), "--serve"],
                                 stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, text=True, bufsize=1)
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


def prepare_word(word):
    """Make the clip ahead of time so a tap plays instantly."""
    _send(f"prep word {word.lower()}")


def stop():
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
    _proc = None
