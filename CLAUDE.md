# Toddler Desk

A deliberately calm, unexciting full-screen "work" app for a toddler (GNOME on
Wayland, Python + GTK4). Keys and taps write out a pretend report; a greyscale
picture of the word being written (word printed underneath) and the latest
letter ("Hh") sit to the right.
Tapping the picture or the letter speaks it. Exit: Ctrl+Alt+Shift+P+I.

## UK English only — no Americanisms

This is a British household. Everything a child sees or hears must be British
English and British culture, not American. This is a hard rule, not a style
preference: importing American language and culture by default is unwelcome.

- Spelling: colour, tyre, aeroplane, grey, centre, mummy, -ise.
- Words: lorry (not truck), bin lorry (not garbage truck), rubbish (not trash),
  petrol (not gas), torch (not flashlight), spanner (not wrench), plaster (not
  band-aid), biscuit (not cookie), sweeties (not candy), nappy, pushchair,
  holiday, pavement, "brum brum" (not "vroom").
- Letters are spoken "aitch" and "zed"; 0 is "nought". Voice is British
  (Kokoro `bm_lewis`, en-gb phonemiser) — never an American voice.
- No American cultural staples (monster trucks, school buses, Halloween
  trick-or-treat, etc.). Prefer British things: milk floats, bin lorries,
  red post boxes, steam trains, rock pools.
- Labels: "Report No. 12", not "Report #12".

Check new reports, icons and UI text against this before committing.

## Keep it boring

Muted greys, no sounds except on deliberate taps, no rewards, no animation
beyond a progress bar and faint tap ripples. The goal is that he feels he is
"doing work", not that the screen is fun.

## Layout

- `toddler_desk.py` — the app; also locks/restores GNOME settings.
- `reports/*.md` — one report per file: `# Title`, blank line, story text.
- `icons.py` — word → emoji (drawn greyscale). Plurals are matched automatically.
- `voice.py` — live Kokoro TTS, runs in `tts/venv` as a child of the app
  (`--serve`). All "how it's said" logic is in `synth()`.
- `speech.py` — app side: starts `voice.py`, sends `say`/`prep` lines.
- `say` — hear exactly what the app says: `./say banana`, `./say -l h`.
- `setup_tts.py` — installs uv, the venv and the model into `tts/` (not committed);
  `--dev` adds Whisper for `./say --check`.
- `asr_check.py` — Whisper transcription, used to check speech without ears.
- `run.sh` / `~/.local/bin/toddler` — launcher; always restores settings after.

## Speech: known Kokoro pitfalls

- Never feed letter names as spellings ("eff", "jee"): the phonemiser reads
  them as abbreviations ("E-F-F"). Feed the capital letter; it gives the
  British letter name.
- A word said on its own gets junk at the start ("t-banana", "an-a"). `synth()`
  says a lead-in phrase first and cuts at the pause; keep that.
- Only `bm_lewis` survived Whisper checks across all 8 British voices; the
  British female voices garble short words. Re-check with Whisper before
  switching voice (`./say --check --no-play word ...`).

## Testing

`python3 toddler_desk.py --test` opens a 900×600 window for 3 s and changes no
GNOME settings. Never test the real full-screen mode without the user present:
it disables system shortcuts.
