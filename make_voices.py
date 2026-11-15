#!/usr/bin/env python3
"""Record every letter and picture word with Piper TTS (British voice).

Usage: python3 make_voices.py [--voice en_GB-cori-high] [--force]
Downloads Piper and the voice into tts/ if they aren't there yet.
"""

import os
import subprocess
import sys
import tarfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from icons import ICONS  # noqa: E402
from speech import LETTER_NAMES, SOUNDS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TTS = os.path.join(HERE, "tts", "dl")
PIPER_URL = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"
VOICE_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_GB"

# Words the voice reads oddly, spelled the way they should sound.
SPOKEN = {"tyre": "tire"}


def ensure(voice):
    os.makedirs(TTS, exist_ok=True)
    piper = os.path.join(TTS, "piper", "piper")
    if not os.path.exists(piper):
        tgz = os.path.join(TTS, "piper.tar.gz")
        urllib.request.urlretrieve(PIPER_URL, tgz)
        with tarfile.open(tgz) as t:
            t.extractall(TTS, filter="tar")
    model = os.path.join(TTS, voice + ".onnx")
    if not os.path.exists(model):
        _, name, quality = voice.split("-")
        for ext in (".onnx", ".onnx.json"):
            urllib.request.urlretrieve(f"{VOICE_BASE}/{name}/{quality}/{voice}{ext}", model[:-5] + ext)
    return piper, model


def main():
    voice = "en_GB-cori-high"
    if "--voice" in sys.argv:
        voice = sys.argv[sys.argv.index("--voice") + 1]
    force = "--force" in sys.argv
    piper, model = ensure(voice)
    jobs = [("letters", ch, text) for ch, text in LETTER_NAMES.items()]
    jobs += [("words", w, SPOKEN.get(w, w)) for w in ICONS]
    made = 0
    for folder, name, text in jobs:
        out = os.path.join(SOUNDS, folder, name + ".wav")
        if os.path.exists(out) and not force:
            continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run([piper, "-m", model, "-f", out, "--length_scale", "1.15",
                        "--sentence_silence", "0.1"],
                       input=text + ".", text=True, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        made += 1
    print(f"{made} recordings made with {voice}; {len(jobs)} total in {SOUNDS}")


if __name__ == "__main__":
    main()
