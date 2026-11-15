"""Whisper check of stopping a sentence clip before unwritten words.

For each sentence and each k, play words 0..k-1 the way the app does
(voice.sentence_part) and check that the last word heard is one of the words
asked for and nothing beyond word k-1 is heard. Reports how many stopped
early (at a clean gap before k) and how many had to cut without a gap.
Run in tts/venv:  tts/venv/bin/python tests/check_end_cuts.py [n] [seed]
"""
import difflib, glob, os, random, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import soundfile as sf
import voice as v
from asr_check import transcribe

def norm(w): return re.sub(r"[^a-z]", "", w.lower())
def like(a, b): return a == b or (len(a) > 2 and len(b) > 2 and difflib.SequenceMatcher(None, a, b).ratio() >= 0.65)

n, seed = int(sys.argv[1]) if len(sys.argv) > 1 else 10, int(sys.argv[2]) if len(sys.argv) > 2 else 1
random.seed(seed)
sents = []
for f in sorted(glob.glob(os.path.join(os.path.dirname(v.__file__), "reports", "*.md"))):
    body = " ".join(open(f).read().split("\n")[1:])
    sents += [x.strip() for x in re.findall(r"[^.!?]+[.!?]", body) if len(x.split()) >= 4]
good = bad = early = forced = 0
for text in random.sample(sents, n):
    words = text.split()
    for k in range(1, len(words)):
        _, starts, clean = v.sentence_clip(text)
        path, got, _ = v.sentence_part(text, 0, k)
        m = len(got)  # words actually played
        early += m < k
        forced += m == k and not clean[k]
        s, r = sf.read(path, dtype="float32")
        heard = [norm(w) for w in transcribe(s, r).split() if norm(w)]
        want = [norm(w) for w in words[:m]]
        ok = bool(heard) and like(heard[-1], want[-1]) and len(heard) <= len(want) + 1
        good += ok; bad += not ok
        if not ok:
            why = "cut without a gap" if m == k and not clean[k] else "clean gap"
            print(f"  X {' '.join(words[:m])!r:40} heard {' '.join(heard)!r} ({why})", flush=True)
print(f"right {good}, wrong {bad}; stopped early {early}, cut without a gap {forced}, of {good + bad}", flush=True)
