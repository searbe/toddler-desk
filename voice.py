#!/usr/bin/env python3
"""Live British speech with Kokoro TTS. Runs inside tts/venv (see setup_tts.py).

As a server (started by the app):  voice.py --serve
    reads lines from stdin:  "say word banana" | "say letter h" | "prep word banana"
For testing by hand:                ./say banana   |   ./say -l h   |   ./say --check [--no-play] fish

All the decisions about *how* things are said live in synth() below, so a fix
can be tried with ./say straight away - no re-recording.
"""

import atexit
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(HERE, "tts", "kokoro")
# bm_lewis scored best by far when every British voice was checked with
# Whisper; the British female voices garble or pad short words.
VOICE = os.environ.get("TODDLER_VOICE", "bm_lewis")
SPEED = 0.9

# Digits are said from these words; letters from the capital letter itself,
# which the British phonemiser turns into "aitch", "zed" and so on.
DIGITS = {"0": "nought", "1": "one", "2": "two", "3": "three", "4": "four",
          "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine"}

_k = None


def kokoro():
    global _k
    if _k is None:
        _k = Kokoro(os.path.join(MODEL_DIR, "kokoro-v1.0.onnx"),
                    os.path.join(MODEL_DIR, "voices-v1.0.bin"))
    return _k


def phonemes(text):
    return kokoro().tokenizer.phonemize(text, "en-gb").strip()


def _trim(s, r):
    """Trim silence and bring every clip to the same loudness."""
    loud = np.where(np.abs(s) > 0.01)[0]
    if not len(loud):
        return s
    s = s[max(0, loud[0] - int(0.02 * r)):loud[-1] + int(0.12 * r)]
    rms = np.sqrt(np.mean(s ** 2)) or 1.0
    gain = min(0.12 / rms, 0.9 / (np.max(np.abs(s)) or 1.0))  # target level, never clip
    return (s * gain).astype(np.float32)


# Kokoro garbles a word said on its own ("banana" -> "t-banana", "A" ->
# "an-a"): the junk is always at the very start. So we say a lead-in phrase
# first, then the word, and cut at the pause between them. The lead-in is
# never heard. Whisper over all 306 letters/words: "Okay, next." 278 clean,
# "Right, next." 275 (worse on letters D, E), "Here is one." 275.
LEAD = "Okay, next."
_lead_len = None


def _speech(s, thresh=0.02):
    loud = np.where(np.abs(s) > thresh)[0]
    return (loud[0], loud[-1]) if len(loud) else (0, len(s))


def _quiet_gaps(s, r, min_ms=40):
    """Midpoints of stretches quieter than the threshold for >= min_ms."""
    fr = int(r * 0.01)
    quiet = [np.sqrt(np.mean(s[i:i + fr] ** 2)) < 0.01 for i in range(0, len(s) - fr, fr)]
    gaps, i = [], 0
    while i < len(quiet):
        if quiet[i]:
            j = i
            while j < len(quiet) and quiet[j]:
                j += 1
            if (j - i) * 10 >= min_ms:
                gaps.append(((i + j) // 2) * fr)
            i = j
        else:
            i += 1
    return gaps


def synth(kind, text):
    """Return (samples, rate) for a letter/digit or a word."""
    global _lead_len
    k = kokoro()
    if kind == "letter":
        ph = phonemes(DIGITS.get(text, text.upper()))
    else:
        ph = phonemes(text.capitalize() + ".")
    lead = phonemes(LEAD)
    if _lead_len is None:
        ls, _ = k.create(lead, voice=VOICE, speed=SPEED, is_phonemes=True)
        a, b = _speech(ls)
        _lead_len = b - a
    s, r = k.create(lead + " " + ph, voice=VOICE, speed=SPEED, is_phonemes=True)
    start, _ = _speech(s)
    expected = start + _lead_len
    gaps = [g for g in _quiet_gaps(s, r) if g > start + 0.6 * _lead_len]
    cut = min(gaps, key=lambda g: abs(g - expected)) if gaps else expected
    return _trim(s[cut:], r), r


# ---------------------------------------------------------------- playback

_cache = {}
_player = None
_tmp = tempfile.mkdtemp(prefix="toddler-voice-")
atexit.register(shutil.rmtree, _tmp, ignore_errors=True)


def clip(kind, text):
    key = (kind, text.lower())
    if key not in _cache:
        s, r = synth(kind, text.lower())
        path = os.path.join(_tmp, f"{kind}-{len(_cache)}.wav")
        sf.write(path, s, r)
        _cache[key] = path
    return _cache[key]


def play(path):
    global _player
    if _player and _player.poll() is None:
        _player.terminate()  # newest tap wins
    _player = subprocess.Popen(["pw-play", path], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)


def serve():
    """Answer requests at once; pre-make letter clips only while idle."""
    requests = queue.Queue()

    def reader():
        for line in sys.stdin:
            requests.put(line)
        requests.put(None)  # stdin closed: the app has gone

    threading.Thread(target=reader, daemon=True).start()
    warmup = [("letter", ch) for ch in "abcdefghijklmnopqrstuvwxyz0123456789"]
    kokoro()
    print("ready", flush=True)
    while True:
        try:
            line = requests.get(timeout=0 if warmup else None)
        except queue.Empty:
            clip(*warmup.pop(0))
            continue
        if line is None:
            break
        parts = line.split(maxsplit=2)
        if len(parts) != 3 or parts[0] not in ("say", "prep") or parts[1] not in ("word", "letter"):
            continue
        try:
            path = clip(parts[1], parts[2].strip())
            if parts[0] == "say":
                play(path)
        except Exception as e:  # never let a bad word kill the voice
            print(f"error: {e}", file=sys.stderr, flush=True)


def main():
    args = sys.argv[1:]
    if args[:1] == ["--serve"]:
        return serve()
    check = "--check" in args
    kind = "letter" if "-l" in args else "word"
    words = [a for a in args if not a.startswith("-")]
    if not words:
        print(__doc__)
        return
    for w in words:
        k = "letter" if kind == "letter" or len(w) == 1 else "word"
        path = clip(k, w)
        if check:
            from asr_check import transcribe
            print(f"{w}: whisper heard {transcribe(*sf.read(path))!r}")
        if "--no-play" not in args:
            subprocess.run(["pw-play", path])


if __name__ == "__main__":
    main()
