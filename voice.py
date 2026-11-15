#!/usr/bin/env python3
"""Live British speech with Kokoro TTS. Runs inside tts/venv (see setup_tts.py).

As a server (started by the app):  voice.py --serve
    reads lines from stdin:  "say word banana" | "say letter h" | "prep word banana"
                             "read <id> I got the jack."  (a sentence, word by word)
    and for "read" prints:   "reading <id> <word starts in seconds, comma-separated>;<clip length>"
                             once playback starts, or "noread <id>" if it failed.
For testing by hand:                ./say banana   |   ./say -l h   |   ./say --check [--no-play] fish

All the decisions about *how* things are said live in synth() below. Clips are
cached in ~/.cache/toddler-desk/voice/<fingerprint>/, where the fingerprint
covers synth() and the voice settings - so after editing synth(), ./say makes
fresh clips straight away.

Clips are made on demand. Only letters and digits (36 clips, under a minute)
are made in the background, because any key can be tapped next; picture words
are asked for one word ahead by the app ("prep"), so they're ready in time.
"""

import os
import queue
import re
import shutil
import subprocess
import sys
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


# Sound words in the reports ("Pssh", "Shh", "Vrrrrr") have no vowels, and the
# phonemiser spells those out letter by letter ("P S S H"). So they are turned
# into sounds here; everything else goes through the phonemiser as normal.
_SOUND = {"sh": "ʃ", "ch": "tʃ", "th": "θ", "r": "ɹ", "c": "k", "q": "k", "x": "ks",
          "j": "dʒ", "y": "j"}
_NOT_SOUNDS = {"mr", "mrs", "dr", "st"}


def _is_sound(core):
    return (len(core) > 1 and core.lower() not in _NOT_SOUNDS
            and not re.search(r"[aeiouy]", core, re.I))


def _sound_phonemes(core):
    w = re.sub(r"(.)\1{2,}", r"\1\1\1", core.lower())  # long sounds long, not silly
    out = []
    i = 0
    while i < len(w):
        if w[i:i + 2] in _SOUND:
            out.append(_SOUND[w[i:i + 2]])
            i += 2
        elif w[i] == "h":  # "shh": the h makes the sound before it last longer
            if out:
                out.append(out[-1])
            i += 1
        else:
            out.append(_SOUND.get(w[i], w[i]))
            i += 1
    return "".join(out)


def sentence_phonemes(text):
    parts, plain = [], []
    for word in text.split():
        core = re.sub(r"[^A-Za-z']", "", word)
        if _is_sound(core):
            if plain:
                parts.append(phonemes(" ".join(plain)))
                plain = []
            parts.append(_sound_phonemes(core) + "".join(c for c in word if c in ".,!?"))
        else:
            plain.append(re.sub(r"([A-Za-z])\1{2,}", r"\1\1", word))  # Splooosh -> Sploosh
    if plain:
        parts.append(phonemes(" ".join(plain)))
    return " ".join(parts)


def _quiet_spans(s, r, min_ms=40):
    """(start, end) of stretches quieter than the threshold for >= min_ms."""
    fr = int(r * 0.01)
    quiet = [np.sqrt(np.mean(s[i:i + fr] ** 2)) < 0.01 for i in range(0, len(s) - fr, fr)]
    spans, i = [], 0
    while i < len(quiet):
        j = i
        while j < len(quiet) and quiet[j] == quiet[i]:
            j += 1
        if quiet[i] and (j - i) * 10 >= min_ms:
            spans.append((i * fr, j * fr))
        i = j
    return spans


def synth(kind, text):
    """Return (samples, rate) for a letter/digit, a word or a sentence."""
    global _lead_len
    k = kokoro()
    if kind == "sentence":
        ph = sentence_phonemes(text)
    elif kind == "letter":
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
    if kind == "sentence":
        # Cut in the long pause after the lead-in. (Cutting nearest the expected
        # point can leave the "t" of "next" at the start, then half a second of
        # silence, which throws the word timings out.)
        spans = [sp for sp in _quiet_spans(s, r)
                 if start + 0.6 * _lead_len < sum(sp) / 2 < start + 1.6 * _lead_len]
        if spans:
            a, b = max(spans, key=lambda sp: sp[1] - sp[0])
            return _trim(s[b - int(0.03 * r):], r), r
    expected = start + _lead_len
    gaps = [g for g in _quiet_gaps(s, r) if g > start + 0.6 * _lead_len]
    cut = min(gaps, key=lambda g: abs(g - expected)) if gaps else expected
    return _trim(s[cut:], r), r


# ------------------------------------------------------------ cache & playback
#
# Making a clip takes ~1.5 s, far too slow for a tap. So every clip is kept on
# disk; letters are made in the background, words just before they're needed.
# The cache folder is named after a fingerprint of the voice settings and the
# synth code itself, so editing synth() automatically starts a fresh cache.

_STRESS = "ˈˌ "


def word_starts(text, s, r):
    """Estimate when each word of `text` starts in its clip, in seconds.

    The voice model gives no timings, so share the speech out in proportion to
    each word's phoneme count, leave room for the pauses at commas and full
    stops, then nudge each boundary to the quietest moment within 80 ms.
    """
    words = text.split()
    weights = []
    for w in words:
        core = "".join(c for c in w if c.isalnum() or c == "'")
        ph = (_sound_phonemes(core) if _is_sound(core) else phonemes(core)) if core else ""
        weights.append(max(1.0, sum(0.5 if c == "ː" else 1.0 for c in ph if c not in _STRESS)))
    pauses = [0.35 * r if w[-1] in ".!?" else 0.2 * r if w[-1] in ",;:" else 0.0
              for w in words[:-1]] + [0.0]
    a, b = _speech(s)
    per = max(0.0, b - a - sum(pauses)) / sum(weights)
    fr = int(r * 0.01)
    env = np.array([np.sqrt(np.mean(s[i:i + fr] ** 2)) for i in range(0, len(s) - fr, fr)])
    starts, t = [], a
    for i, w in enumerate(weights):
        if i == 0:
            starts.append(t)
        else:
            c = int(t // fr)
            lo, hi = max(0, c - 8), min(len(env), c + 9)
            snapped = (lo + int(np.argmin(env[lo:hi]))) * fr if hi > lo else t
            starts.append(max(snapped, starts[-1] + int(0.08 * r)))  # always move forward
        t += w * per + pauses[i]
    return [round(x / r, 3) for x in starts]


def _fingerprint():
    import hashlib
    import inspect
    parts = [VOICE, str(SPEED), LEAD, repr(DIGITS)]
    parts += [inspect.getsource(f)
              for f in (phonemes, _trim, _speech, _quiet_gaps, _quiet_spans, synth, word_starts,
                        _is_sound, _sound_phonemes, sentence_phonemes)]
    parts.append(repr(_SOUND) + repr(sorted(_NOT_SOUNDS)))  # sets print in random order
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()[:12]


CACHE_ROOT = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                          "toddler-desk", "voice")
CACHE = os.path.join(CACHE_ROOT, _fingerprint())
_player = None


def clip(kind, text):
    text = "".join(c for c in text.lower() if c.isalnum())
    path = os.path.join(CACHE, f"{kind}-{text}.wav")
    if not os.path.exists(path):
        os.makedirs(CACHE, exist_ok=True)
        s, r = synth(kind, text)
        sf.write(path + ".tmp.wav", s, r)
        os.replace(path + ".tmp.wav", path)
    return path


def sentence_clip(text):
    """(path, word start times) for a sentence; both kept in the cache."""
    import hashlib
    import json
    name = hashlib.sha1(text.encode()).hexdigest()[:16]
    path = os.path.join(CACHE, f"sentence-{name}.wav")
    meta = path[:-4] + ".json"
    if not (os.path.exists(path) and os.path.exists(meta)):
        os.makedirs(CACHE, exist_ok=True)
        s, r = synth("sentence", text)
        with open(meta + ".tmp", "w") as f:
            json.dump(word_starts(text, s, r), f)
        sf.write(path + ".tmp.wav", s, r)
        os.replace(meta + ".tmp", meta)
        os.replace(path + ".tmp.wav", path)
    with open(meta) as f:
        return path, json.load(f)


LETTERS = [("letter", c) for c in "abcdefghijklmnopqrstuvwxyz0123456789"]


def play(path):
    global _player
    if _player and _player.poll() is None:
        _player.terminate()  # newest tap wins
    _player = subprocess.Popen(["pw-play", path], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)


def serve():
    """Answer requests at once; make letter clips in the background while idle."""
    os.nice(5)  # never make the screen stutter
    # Old caches belong to earlier versions of synth(): remove them.
    if os.path.isdir(CACHE_ROOT):
        for d in os.listdir(CACHE_ROOT):
            if d != os.path.basename(CACHE):
                shutil.rmtree(os.path.join(CACHE_ROOT, d), ignore_errors=True)
    requests = queue.Queue()

    def reader():
        for line in sys.stdin:
            requests.put(line)
        requests.put(None)  # stdin closed: the app has gone

    threading.Thread(target=reader, daemon=True).start()
    todo = [item for item in LETTERS
            if not os.path.exists(os.path.join(CACHE, f"{item[0]}-{item[1]}.wav"))]
    if todo:
        kokoro()
    print("ready", flush=True)
    pending = []  # requests not handled yet, oldest first
    while True:
        try:  # wait for work only when there's nothing else to do
            line = requests.get(timeout=0 if (todo or pending) else None)
            if line is None:
                break
            pending.append(line.strip())
            while not requests.empty():  # take everything that has arrived
                line = requests.get()
                if line is None:
                    return
                pending.append(line.strip())
        except queue.Empty:
            pass
        # Taps first, newest tap wins; then picture words; then letters.
        taps = [p for p in pending if p.startswith(("say ", "read "))]
        if taps:
            job = taps[-1]
            for old in taps[:-1]:
                if old.startswith("read "):
                    print(f"noread {old.split()[1]}", flush=True)
            pending = [p for p in pending if p not in taps]
        elif pending:
            job = pending.pop(0)
            pending = [p for p in pending if p != job]  # same word asked twice
        else:
            clip(*todo.pop(0))
            continue
        handle(job)


def handle(line):
    parts = line.split(maxsplit=2)
    if parts[:1] == ["read"] and len(parts) == 3:
        rid, text = parts[1], parts[2]
        try:
            path, starts = sentence_clip(text)
            play(path)
            print(f"reading {rid} " + ",".join(map(str, starts))
                  + f";{sf.info(path).duration:.3f}", flush=True)
        except Exception as e:
            print(f"error: {e}", file=sys.stderr, flush=True)
            print(f"noread {rid}", flush=True)
        return
    if len(parts) != 3 or parts[0] not in ("say", "prep") or parts[1] not in ("word", "letter"):
        return
    try:
        path = clip(parts[1], parts[2])
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
