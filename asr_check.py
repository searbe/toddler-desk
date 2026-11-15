"""Transcribe clips with Whisper to catch junk syllables (dev tool)."""
import os, sys
import numpy as np, soundfile as sf
os.environ.setdefault("HF_HOME", os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts", "hf"))
from faster_whisper import WhisperModel
_m = None
def model():
    global _m
    if _m is None:
        _m = WhisperModel("small.en", device="cpu", compute_type="int8")
    return _m
def to16k(s, r):
    if s.ndim > 1: s = s.mean(1)
    n = int(len(s) * 16000 / r)
    return np.interp(np.linspace(0, len(s) - 1, n), np.arange(len(s)), s).astype(np.float32)
def transcribe(samples, rate):
    pad = np.zeros(8000, np.float32)  # 0.5 s silence each side helps short clips
    a = np.concatenate([pad, to16k(np.asarray(samples, np.float32), rate), pad])
    segs, _ = model().transcribe(a, language="en", beam_size=5, without_timestamps=True,
                                 condition_on_previous_text=False)
    return "".join(s.text for s in segs).strip()
if __name__ == "__main__":
    for f in sys.argv[1:]:
        s, r = sf.read(f)
        print(f"{os.path.basename(f):16s}", repr(transcribe(s, r)))
