# Toddler Desk

A deliberately calm, unexciting full-screen "work" app for a toddler (GNOME on
Wayland, Python + GTK4). Keys and taps write out a pretend report; a greyscale
picture of the word being written and the latest letter ("Hh") sit to the right.
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
- Letters are spoken "aitch" and "zed"; 0 is "nought". Voice is a British
  Piper voice (en_GB-cori-high).
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
- `speech.py` — letter names and playback; `make_voices.py` records
  `sounds/` with Piper (`tts/`, not committed). Re-run after adding icon words.
- `run.sh` / `~/.local/bin/toddler` — launcher; always restores settings after.

## Testing

`python3 toddler_desk.py --test` opens a 900×600 window for 3 s and changes no
GNOME settings. Never test the real full-screen mode without the user present:
it disables system shortcuts.
