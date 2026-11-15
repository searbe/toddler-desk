#!/usr/bin/env python3
"""Record every letter, digit and picture word with Kokoro TTS (British voice).

Usage: python3 make_voices.py [--voice bf_emma] [--force]

First run sets everything up inside tts/ (nothing system-wide): the `uv`
package manager, a Python 3.12 venv with kokoro-onnx, and the Kokoro model.
Only missing recordings are made unless --force is given.
"""

import os
import subprocess
import sys
import tarfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TTS = os.path.join(HERE, "tts")
VENV_PY = os.path.join(TTS, "venv", "bin", "python")
MODEL_DIR = os.path.join(TTS, "kokoro")
UV_URL = "https://github.com/astral-sh/uv/releases/download/0.9.5/uv-x86_64-unknown-linux-gnu.tar.gz"
MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
MODEL_FILES = ["kokoro-v1.0.onnx", "voices-v1.0.bin"]
DEFAULT_VOICE = "bf_emma"  # British female; others: bf_isabella, bm_george, bm_lewis


def setup():
    """Create tts/venv with kokoro-onnx and fetch the model, if missing."""
    os.makedirs(MODEL_DIR, exist_ok=True)
    env = dict(os.environ, UV_PYTHON_INSTALL_DIR=os.path.join(TTS, "python"),
               UV_CACHE_DIR=os.path.join(TTS, "uv-cache"))
    uv = os.path.join(TTS, "uv")
    if not os.path.exists(VENV_PY):
        if not os.path.exists(uv):
            tgz = os.path.join(TTS, "uv.tar.gz")
            urllib.request.urlretrieve(UV_URL, tgz)
            with tarfile.open(tgz) as t:
                member = t.getmember("uv-x86_64-unknown-linux-gnu/uv")
                member.name = "uv"
                t.extract(member, TTS, filter="tar")
            os.remove(tgz)
        subprocess.run([uv, "venv", "-q", "--python", "3.12", os.path.join(TTS, "venv")],
                       env=env, check=True)
        subprocess.run([uv, "pip", "install", "-q", "kokoro-onnx", "soundfile"],
                       env=dict(env, VIRTUAL_ENV=os.path.join(TTS, "venv")), check=True)
    for f in MODEL_FILES:
        path = os.path.join(MODEL_DIR, f)
        if not os.path.exists(path):
            print(f"downloading {f} ...")
            urllib.request.urlretrieve(MODEL_URL + f, path)


def record(voice, force):
    import numpy as np
    import soundfile as sf
    from kokoro_onnx import Kokoro

    sys.path.insert(0, HERE)
    from icons import ICONS
    from speech import LETTER_NAMES, SOUNDS

    k = Kokoro(*(os.path.join(MODEL_DIR, f) for f in MODEL_FILES))

    # Letters go in as exact phonemes. Spellings like "eff" get misread as
    # abbreviations ("E-F-F"), but a lone capital gives the proper British
    # letter name. Check the two that differ from American.
    def phonemes(text):
        return k.tokenizer.phonemize(text, "en-gb").strip()
    assert "eɪtʃ" in phonemes("H") and "zˈɛd" in phonemes("Z"), "not British letter names"

    jobs = []
    for ch, spoken in LETTER_NAMES.items():
        jobs.append(("letters", ch, phonemes(ch.upper() if ch.isalpha() else spoken)))
    for word in ICONS:
        jobs.append(("words", word, phonemes(word.capitalize() + ".")))

    made = 0
    for folder, name, ph in jobs:
        out = os.path.join(SOUNDS, folder, name + ".wav")
        if os.path.exists(out) and not force:
            continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        samples, rate = k.create(ph, voice=voice, speed=0.9, is_phonemes=True)
        # trim silence, keep a short tail so it doesn't sound clipped
        loud = np.where(np.abs(samples) > 0.01)[0]
        if len(loud):
            samples = samples[max(0, loud[0] - int(0.02 * rate)):loud[-1] + int(0.12 * rate)]
        sf.write(out, samples, rate)
        made += 1
    print(f"{made} recordings made with {voice}; {len(jobs)} total in {SOUNDS}")


def main():
    voice = sys.argv[sys.argv.index("--voice") + 1] if "--voice" in sys.argv else DEFAULT_VOICE
    force = "--force" in sys.argv
    if os.path.realpath(sys.executable) != os.path.realpath(VENV_PY):
        setup()  # then re-run ourselves inside the venv
        os.execv(VENV_PY, [VENV_PY, os.path.abspath(__file__)] + sys.argv[1:])
    record(voice, force)


if __name__ == "__main__":
    main()
