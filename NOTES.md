# Toddler Desk: findings and background

Things learned while building this that aren't obvious from the code.
`CLAUDE.md` has the rules; this file has the evidence behind them. Add to it.

## Who it's for and what matters

- A British household: strict UK English and British culture ("we are british,
  not american"). Lorry, zed, aitch, nought, "Report No.". The original monster
  truck report was replaced with a milk float.
- Keep it boring: no rewards, nothing that makes him *want* screens.
- Live TTS was chosen for a fast feedback loop (no re-recording). Tap delay is
  the thing that annoys most; everything in the voice design serves that.
- Testing speech by ear is hard for the user, so speech changes are checked
  with Whisper (`asr_check.py`, `./say --check`).

## Speech (Kokoro, Whisper-checked)

- One word said on its own gets junk at the start: banana -> "It's bananas",
  tractor -> "You dragged her", A -> "They", H -> "Late". Saying a lead-in
  phrase first and cutting at the pause fixes it; the lead-in is never heard.
- Voices: 12-word hard set, all 8 British voices x 3 methods. Only `bm_lewis`
  is good (11/12 with the lead-in cut); the `bf_*` voices garble short words
  (best 4/12). `bf_emma` was what the user first heard and disliked.
- All 306 letters/words with `bm_lewis`: lead-in "Okay, next." 278 clean,
  "Right, next." 275 (fails D, E), "Here is one." 275. The rest are Whisper's
  bias, not faults: homophones (sea/See, tea/T, eye/I, hay/Hey, plough/plow,
  tree/3) and non-rhotic British vowels (car->Ka, barn->BON, bird->BUD,
  heart->Hard). duck->"Doc" with every lead-in.
- Whisper also drops a soft first word of a clip with nothing before it
  ("went up..." -> "up..."), and guesses "Have a duck" for "had a duck". To
  check where a clip starts, put "next." in front of it before transcribing.
- Never feed letter names ("eff", "jee"): espeak reads "eff" as "E-F-F". Feed
  the capital letter; en-gb says "aitch" and "zed".
- Sound words without vowels ("Pssh", "Shh", "Vrrrr") are spelled out by the
  phonemiser; `sentence_phonemes()` turns them into sounds.
- Timings on this laptop (i7-8550U, 4 cores/8 threads): model load ~1-1.7 s;
  one word with lead-in ~1.5 s; a sentence clip ~2-2.5 s; pw-play adds ~0.1 s.
  The delay is all synthesis, so making playback faster won't help.
- ONNX threads: 4 was fastest (2.4 s a clip), 8 was slower (2.7-4.1 s) and
  pegged every core. The voice uses 3, leaving a core free for the screen.
- `asr_check.py` feeds numpy audio at 16 kHz because faster-whisper's file
  decoder breaks with the installed `av` ("metadata_errors" TypeError).
  Whisper model is small.en, cached under `tts/hf`.

## Reading aloud from a tapped word

- Kokoro computes how long each sound lasts (`/encoder/Clip_output_0`) but
  doesn't output it. `setup_tts.py` makes `kokoro-v1.0-timed.onnx` with that
  as a `duration` output. With kokoro-onnx's extra pauses off
  (`sentence_pause=0, clause_pause=0`) the audio is sample-for-sample the
  same as the original model's.
- Kokoro's audio runs ahead of its frame timings; its reference code subtracts
  3 frames (75 ms). 50 ms tested best here.
- Cutting one sentence clip at a word to start mid-sentence doesn't work well
  enough, with estimated timings (21/47 right) or exact ones (best 47/57):
  words run together ("did it all", "caught a") with no gap to cut in. So
  each word position gets its own clip, made one sentence ahead of the
  writing. Those were heard right 106/110 times; the 4 misses were Whisper.
- Stopping a clip *before* a word (sentence half written) has the same
  problem at the end: 36/41 right with a plain cut; "I caught" came out
  "I co", "in" leaked "it". Silence at the cut point separates the cases:
  real gaps measure 0.001-0.007 RMS, run-together words 0.012-0.06 (cut-off
  0.01, `GAP_RMS`). About half of word boundaries have no clean gap.
- The user doesn't want reading past what's on screen, and wants it instant
  rather than complete: the clip stops at the last clean gap, even if that
  leaves off the last word or two. (Making an exact clip instead took ~2 s.)
  Check (`tests/check_end_cuts.py`): 35/41, no leaked or clipped words; the
  6 misses were one-word clips ("I", "It", "One"), 0.1-0.2 s long and cleanly
  ended, which Whisper can't name. 15/41 stopped early at a gap.

## GNOME 50 on this Dell (ELAN touchscreen + touchpad)

- "Bits of GNOME showing" came from shell gestures. `windowManager.js:909`: a
  touchscreen drag down from the top edge calls `unmake_fullscreen()` on the
  focused fullscreen window. The app re-fullscreens on `notify::fullscreened`.
- The `org.gnome.Shell` `OverviewActive` D-Bus property can be set by any
  client (verified with gdbus), so the app closes the overview after a 3/4
  finger swipe.
- `keyboard.js:1067`: dragging up from the bottom edge opens the on-screen
  keyboard. It's switched on automatically for touchscreens and ignores
  `screen-keyboard-enabled`. Harmless: its keys go to the app. Workspace
  swipes aren't blocked.
- Touchpad "disable while typing" ignored taps while a key was held; the app
  turns it off while running.
- `present()` can't take focus back on Wayland, so if the window loses focus
  the app's own exit combo stops working. Hence the GNOME custom shortcut
  (Ctrl+Alt+Shift+I) as a backup exit.
- On a UK layout right Alt is AltGr and doesn't count as Alt; the exit check
  accepts either and looks at physical keys.

## Recovery

- A hard power cycle skips both the app's and the launcher's restore. The
  login item `autostart/toddler-desk-restore.desktop` (copied to
  `~/.config/autostart/`) runs `toddler_desk.py --restore` at every login;
  it does nothing unless a backup of the settings is left over.
- From another machine: `toddler_desk.py --quit`.
- `kernel.sysrq=176` (Ubuntu default) still allows Alt+SysRq reboot (REISUB).
- sudo can't be used from Claude Code here (needs a real terminal for the
  password; `! sudo` fails too).

## Testing gotchas

- Never run the real full-screen mode without the user there; it locks
  shortcuts. Any unknown option now prints usage instead of launching it.
- When the screen is locked, GTK doesn't paint and `Gtk.WidgetPaintable`
  snapshots come back empty. Call `desk.do_snapshot(Gtk.Snapshot())` directly
  for screenshots.
- `pkill -f <name>` inside a bash command can match and kill that command
  itself (exit 144).
- Test windows (`--test`) open on the user's real screen, and their taps
  reach the app.
- The cache fingerprint must be deterministic: a `repr()` of a set changed
  every run and wiped the whole cache on each start.
- `TODDLER_PLAYER=true` makes the voice silent for tests.
