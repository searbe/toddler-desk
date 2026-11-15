"""Word -> picture (an emoji, drawn in greyscale by the app).

Keys are lower-case words as they appear in the reports. Plurals are matched
automatically ("ducks" -> "duck", "fishes" -> "fish"), so only add singulars
unless the plural is irregular (teeth, sheep, ...).
"""

# Rule: a word only gets a picture if the emoji actually shows that thing, as
# the word is used in the reports. No "near enough" (a spanner for "jack", a
# balloon for "pump"), and no words the reports also use in another sense
# ("saw" = I saw, "tap tap tap", "cup of tea", turtle "shell", alphabet
# "letters"). Before adding one, check its Unicode name and how the word is
# used in reports/. No picture is fine: the last picture stays up.
ICONS = {
    # vehicles
    "tractor": "🚜", "helicopter": "🚁", "train": "🚂", "car": "🚗", "bus": "🚌",
    "ambulance": "🚑", "rocket": "🚀", "boat": "⛵", "ship": "🚢", "ferry": "⛴️",
    "aeroplane": "✈️", "bike": "🚲", "lorry": "🚚", "crane": "🏗️", "fire": "🔥",
    "racing": "🏎️", "carriage": "🚃", "wheel": "🛞", "tyre": "🛞", "petrol": "⛽",
    "track": "🛤️", "siren": "🚨",
    # sea and water creatures
    "fish": "🐟", "whale": "🐋", "octopus": "🐙", "crab": "🦀", "shark": "🦈",
    "dolphin": "🐬", "turtle": "🐢", "penguin": "🐧", "jellyfish": "🪼",
    "lobster": "🦞", "squid": "🦑", "seal": "🦭", "shrimp": "🦐", "frog": "🐸",
    "snail": "🐌", "sea": "🌊", "water": "💧", "bubble": "🫧", "seaside": "🏖️",
    "beach": "🏖️",
    # animals
    "duck": "🦆", "bird": "🐦", "puppy": "🐶", "dog": "🐕", "cat": "🐈", "bear": "🐻",
    "teddy": "🧸", "hamster": "🐹", "horse": "🐴", "cow": "🐄", "pig": "🐖",
    "chicken": "🐔", "sheep": "🐑", "dinosaur": "🦕", "dragon": "🐉", "bunny": "🐰",
    "worm": "🪱", "crocodile": "🐊", "owl": "🦉", "rabbit": "🐰", "bee": "🐝",
    "butterfly": "🦋", "spider": "🕷️", "paw": "🐾", "nest": "🪺",
    # people
    "doctor": "🧑‍⚕️", "nurse": "🧑‍⚕️", "police": "👮", "pilot": "🧑‍✈️",
    "firefighter": "🧑‍🚒", "mechanic": "🧑‍🔧", "builder": "👷", "farmer": "🧑‍🌾",
    "baby": "👶", "grandma": "👵", "daddy": "👨", "mummy": "👩",
    # doctor things and the body
    "hospital": "🏥", "medicine": "💊", "plaster": "🩹", "thermometer": "🌡️",
    "tooth": "🦷", "teeth": "🦷", "glasses": "👓", "eye": "👁️", "ear": "👂",
    "heart": "❤️", "leg": "🦵", "sneezed": "🤧", "spoon": "🥄", "torch": "🔦",
    # tools and fixing
    "spanner": "🔧", "hammer": "🔨", "screwdriver": "🪛", "bolt": "🔩",
    "ladder": "🪜", "oil": "🛢️", "brick": "🧱", "knot": "🪢", "needle": "🪡",
    "thread": "🧵", "battery": "🔋", "bulb": "💡", "light": "💡", "plug": "🔌",
    "plunger": "🪠", "chain": "⛓️", "key": "🔑", "magnet": "🧲", "sponge": "🧽",
    "soap": "🧼", "hole": "🕳️",
    # house and things
    "house": "🏠", "door": "🚪", "window": "🪟", "bath": "🛁", "clock": "🕰️",
    "radio": "📻", "computer": "💻", "sock": "🧦", "book": "📚", "bed": "🛏️",
    "bin": "🗑️", "box": "📦", "parcel": "📦", "bell": "🔔", "tent": "⛺",
    "shop": "🏪", "road": "🛣️", "recycling": "♻️", "music": "🎵",
    # food
    "egg": "🥚", "cake": "🍰", "tea": "☕", "butter": "🧈", "carrot": "🥕",
    "banana": "🍌", "milk": "🥛", "cereal": "🥣", "biscuit": "🍪", "sweetie": "🍬",
    "spaghetti": "🍝", "bean": "🫘", "wheat": "🌾", "grain": "🌾", "apple": "🍎",
    "sandwich": "🥪", "sunflower": "🌻",
    # weather, sky, nature
    "moon": "🌙", "earth": "🌍", "planet": "🌍", "sun": "☀️", "star": "⭐",
    "cloud": "☁️", "rain": "🌧️", "snow": "❄️", "snowman": "⛄", "tree": "🌳",
    "flower": "🌸", "rock": "🪨", "stone": "🪨",
    # feelings and happenings
    "sleep": "😴", "hug": "🤗", "cuddle": "🤗", "crash": "💥",
}

IRREGULAR = {"teeth": "tooth", "mice": "mouse", "geese": "goose", "children": "child",
             "people": "people", "feet": "foot", "boxes": "box", "fishes": "fish",
             "wheels": "wheel", "sweeties": "sweetie", "puppies": "puppy",
             "babies": "baby", "teddies": "teddy", "carriages": "carriage", "lorries": "lorry"}


def icon_for(word):
    """Return (canonical_word, emoji) or None."""
    w = "".join(c for c in word.lower() if c.isalpha())
    if not w:
        return None
    for cand in (w, IRREGULAR.get(w), w[:-1] if w.endswith("s") else None,
                 w[:-2] if w.endswith("es") else None):
        if cand and cand in ICONS:
            return cand, ICONS[cand]
    return None
