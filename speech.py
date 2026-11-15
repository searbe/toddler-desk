"""Pre-recorded British English speech for letters and picture words.

Recordings live in sounds/letters/<char>.wav and sounds/words/<word>.wav and
are made once by make_voices.py (Kokoro TTS, British voice). If a recording is
missing, nothing is played.
"""

import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SOUNDS = os.path.join(HERE, "sounds")

# Digits are recorded from these words; letters from the capital letter itself
# (which gives British names: "aitch", "zed").
LETTER_NAMES = {
    "a": "ay", "b": "bee", "c": "see", "d": "dee", "e": "ee", "f": "eff",
    "g": "jee", "h": "aitch", "i": "eye", "j": "jay", "k": "kay", "l": "ell",
    "m": "em", "n": "en", "o": "oh", "p": "pee", "q": "queue", "r": "ar",
    "s": "ess", "t": "tee", "u": "you", "v": "vee", "w": "double you",
    "x": "ex", "y": "why", "z": "zed",
    "0": "nought", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}

_player = shutil.which("pw-play") or shutil.which("paplay") or shutil.which("aplay")
_current = None


def _play(path):
    global _current
    if not _player or not os.path.exists(path):
        return
    if _current and _current.poll() is None:
        _current.terminate()  # one voice at a time, newest wins
    _current = subprocess.Popen([_player, path], stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)


def say_letter(ch):
    _play(os.path.join(SOUNDS, "letters", ch.lower() + ".wav"))


def say_word(word):
    _play(os.path.join(SOUNDS, "words", word.lower() + ".wav"))
