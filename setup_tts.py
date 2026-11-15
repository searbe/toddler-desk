#!/usr/bin/env python3
"""Set up the live Kokoro voice inside tts/ (nothing system-wide).

Usage: python3 setup_tts.py [--dev]

Installs the `uv` package manager, a Python 3.12 venv with kokoro-onnx, and
the Kokoro model. --dev also installs Whisper for `./say --check`.
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


def main():
    setup()
    if "--dev" in sys.argv:  # Whisper, for ./say --check
        subprocess.run([os.path.join(TTS, "uv"), "pip", "install", "-q", "faster-whisper"],
                       env=dict(os.environ, UV_CACHE_DIR=os.path.join(TTS, "uv-cache"),
                                VIRTUAL_ENV=os.path.join(TTS, "venv")), check=True)
    print("Voice ready. Try: ./say banana")


if __name__ == "__main__":
    main()
