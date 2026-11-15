"""Word -> picture (an emoji, drawn in greyscale by the app).

Keys are lower-case words as they appear in the reports. Plurals are matched
automatically ("ducks" -> "duck", "fishes" -> "fish"), so only add singulars
unless the plural is irregular (teeth, sheep, ...).
"""

ICONS = {
    # vehicles
    "tractor": "🚜", "helicopter": "🚁", "train": "🚂", "car": "🚗", "bus": "🚌",
    "ambulance": "🚑", "police": "🚓", "rocket": "🚀", "boat": "⛵", "ship": "🚢",
    "ferry": "⛴️", "aeroplane": "✈️", "bike": "🚲", "lorry": "🚚", "tanker": "🚚",
    "digger": "🚜", "excavator": "🏗️", "crane": "🏗️", "bulldozer": "🚜",
    "fire": "🔥", "engine": "🚒", "racing": "🏎️", "submarine": "🌊",
    "carriage": "🚃", "tugboat": "🚤", "float": "🥛", "wheel": "🛞", "tyre": "🛞",
    "petrol": "⛽", "trailer": "🚚", "forklift": "📦", "plough": "🚜", "mixer": "🏗️",
    "harvester": "🌾", "track": "🛤️", "runway": "✈️", "pilot": "✈️", "siren": "🚨",
    "lights": "🚨",
    # sea and water creatures
    "fish": "🐟", "whale": "🐋", "octopus": "🐙", "crab": "🦀", "shark": "🦈",
    "dolphin": "🐬", "turtle": "🐢", "penguin": "🐧", "starfish": "⭐",
    "jellyfish": "🪼", "lobster": "🦞", "squid": "🦑", "seal": "🦭", "shrimp": "🦐",
    "tadpole": "🐸", "frog": "🐸", "snail": "🐌", "shell": "🐚", "seaweed": "🌿",
    "sea": "🌊", "water": "💧", "wave": "🌊", "pond": "🦆", "pool": "🌊",
    "bubble": "🫧", "goldfish": "🐠", "net": "🎣", "fisherman": "🎣",
    "seaside": "🏖️", "beach": "🏖️", "aquarium": "🐠",
    # animals
    "duck": "🦆", "bird": "🐦", "seagull": "🐦", "puppy": "🐶", "dog": "🐕",
    "cat": "🐈", "bear": "🐻", "teddy": "🧸", "hamster": "🐹", "horse": "🐴",
    "cow": "🐄", "pig": "🐖", "chicken": "🐔", "sheep": "🐑", "dinosaur": "🦕",
    "dragon": "🐉", "bunny": "🐰", "worm": "🪱", "crocodile": "🐊", "owl": "🦉",
    "rabbit": "🐰", "bee": "🐝", "butterfly": "🦋", "spider": "🕷️", "mouse": "🐭",
    "patient": "🧸", "farm": "🐄", "farmer": "🧑‍🌾", "paw": "🐾",
    # doctor things
    "doctor": "🩺", "nurse": "🩺", "hospital": "🏥", "medicine": "💊",
    "plaster": "🩹", "bandage": "🩹", "thermometer": "🌡️", "tooth": "🦷",
    "teeth": "🦷", "dentist": "🦷", "glasses": "👓", "eye": "👁️", "ear": "👂",
    "heart": "❤️", "knee": "🦵", "leg": "🦵", "arm": "💪", "tummy": "🤒",
    "cough": "🤧", "sniffle": "🤧", "tissue": "🤧", "sneezed": "🤧",
    "sticker": "⭐", "spoon": "🥄", "torch": "🔦",
    # tools and fixing
    "spanner": "🔧", "hammer": "🔨", "screwdriver": "🪛", "nail": "🔩",
    "bolt": "🔩", "screw": "🔩", "ladder": "🪜", "oil": "🛢️", "hose": "🧯",
    "pump": "🎈", "brick": "🧱", "block": "🧱", "rope": "🪢", "knot": "🪢",
    "needle": "🪡", "thread": "🧵", "battery": "🔋", "bulb": "💡", "light": "💡",
    "plug": "🔌", "wire": "🔌", "jack": "🔧", "plunger": "🪠", "cone": "🚧",
    "hat": "⛑️", "bucket": "🪣", "chain": "⛓️", "key": "🔑", "magnet": "🧲",
    "saw": "🪚", "level": "📏", "sponge": "🧽", "soap": "🧼", "squeegee": "🧽",
    "fence": "🚧", "gate": "🚧", "hole": "🕳️",
    # house and things
    "house": "🏠", "door": "🚪", "window": "🪟", "roof": "🏠", "bath": "🛁",
    "tap": "🚰", "sink": "🚰", "clock": "🕰️", "radio": "📻", "computer": "💻",
    "toaster": "🍞", "washing": "🧺", "sock": "🧦", "hoover": "🧹", "shelf": "📚",
    "book": "📚", "bed": "🛏️", "blanket": "🛏️", "swing": "🛝", "tower": "🗼",
    "lighthouse": "🗼", "barn": "🛖", "garage": "🔧", "bin": "🗑️", "box": "📦",
    "parcel": "📦", "letter": "✉️", "bag": "👜", "postman": "📮", "bell": "🔔",
    "whistle": "📯", "cup": "🏆", "tent": "⛺", "nest": "🪺", "lego": "🧱",
    "doll": "🪆", "baby": "👶", "bottle": "🍼", "grandma": "👵", "daddy": "👨",
    "mummy": "👩", "milkman": "🥛", "builder": "👷", "firefighter": "🧑‍🚒",
    "mechanic": "🔧", "plumber": "🔧", "captain": "⚓", "driver": "🧢",
    "shop": "🏪", "road": "🛣️", "street": "🛣️", "rubbish": "🗑️", "recycling": "♻️",
    "planet": "🌍", "step": "🪜",
    # food
    "egg": "🥚", "cake": "🍰", "tea": "☕", "toast": "🍞", "butter": "🧈",
    "carrot": "🥕", "banana": "🍌", "milk": "🥛", "cereal": "🥣", "biscuit": "🍪",
    "sweetie": "🍬", "spaghetti": "🍝", "seed": "🌱", "bean": "🫘", "wheat": "🌾",
    "grain": "🌾", "hay": "🌾", "straw": "🌾", "apple": "🍎", "sandwich": "🥪",
    "lunch": "🍽️", "breakfast": "🥣", "snack": "🍎", "food": "🍽️", "sunflower": "🌻",
    # weather, sky, nature
    "moon": "🌙", "earth": "🌍", "sun": "☀️", "star": "⭐", "cloud": "☁️",
    "rain": "🌧️", "snow": "❄️", "snowman": "⛄", "smoke": "💨", "tree": "🌳",
    "flower": "🌸", "garden": "🌻", "mud": "🟫", "puddle": "💧", "rock": "🪨",
    "stone": "🪨", "dirt": "🟫", "sand": "🏖️", "hill": "⛰️", "field": "🌾",
    "night": "🌙", "space": "🚀", "coal": "🪨", "cement": "🧱",
    # misc
    "music": "🎵", "sleep": "😴", "hug": "🤗", "cuddle": "🤗", "crash": "💥",
}

IRREGULAR = {"teeth": "tooth", "mice": "mouse", "geese": "goose", "children": "child",
             "people": "people", "feet": "foot", "boxes": "box", "fishes": "fish",
             "wheels": "wheel", "sweeties": "sweetie", "puppies": "puppy",
             "babies": "baby", "carriages": "carriage", "lorries": "lorry"}


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
