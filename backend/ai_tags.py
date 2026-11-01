"""
Orion — ai_tags.py
Visual tag vocabulary for CLIP zero-shot auto-tagging.

Each tag maps to its parent categories. When CLIP decides an image shows a
"cat", Orion stores:  cat, animal, pet   — so searching "animal" finds it too.
"""

# tag -> parent categories
TAGS: dict[str, list[str]] = {
    # ── Animals ──────────────────────────────────────────────────────────────
    "cat": ["animal", "pet"], "kitten": ["cat", "animal", "pet"],
    "dog": ["animal", "pet"], "puppy": ["dog", "animal", "pet"],
    "bird": ["animal"], "parrot": ["bird", "animal"], "pigeon": ["bird", "animal"],
    "eagle": ["bird", "animal"], "owl": ["bird", "animal"], "peacock": ["bird", "animal"],
    "chicken": ["bird", "animal"], "duck": ["bird", "animal"],
    "fish": ["animal"], "goldfish": ["fish", "animal", "pet"], "shark": ["fish", "animal"],
    "horse": ["animal"], "cow": ["animal"], "goat": ["animal"], "sheep": ["animal"],
    "pig": ["animal"], "rabbit": ["animal", "pet"], "hamster": ["animal", "pet"],
    "mouse": ["animal"], "squirrel": ["animal"], "monkey": ["animal"],
    "elephant": ["animal", "wildlife"], "lion": ["animal", "wildlife"],
    "tiger": ["animal", "wildlife"], "leopard": ["animal", "wildlife"],
    "bear": ["animal", "wildlife"], "panda": ["animal", "wildlife"],
    "giraffe": ["animal", "wildlife"], "zebra": ["animal", "wildlife"],
    "deer": ["animal", "wildlife"], "fox": ["animal", "wildlife"], "wolf": ["animal", "wildlife"],
    "camel": ["animal"], "kangaroo": ["animal", "wildlife"],
    "snake": ["animal", "reptile"], "lizard": ["animal", "reptile"],
    "turtle": ["animal", "reptile"], "crocodile": ["animal", "reptile"],
    "frog": ["animal"], "butterfly": ["insect", "animal"], "bee": ["insect", "animal"],
    "spider": ["insect", "animal"], "ant": ["insect", "animal"],
    "dolphin": ["animal", "sea"], "whale": ["animal", "sea"],
    "dinosaur": ["animal"],

    # ── People ───────────────────────────────────────────────────────────────
    "selfie": ["person", "people", "portrait"], "portrait": ["person", "people"],
    "group photo": ["people", "friends"], "crowd": ["people"],
    "baby": ["person", "people", "child"], "child": ["person", "people"],
    "family": ["people"], "couple": ["people"], "wedding": ["event", "people", "celebration"],
    "man": ["person", "people"], "woman": ["person", "people"],
    "old person": ["person", "people"], "student": ["person", "people"],
    "people dancing": ["people", "dance"], "people at a party": ["party", "people", "celebration"],
    "graduation ceremony": ["event", "people", "college"],

    # ── Nature & scenery ─────────────────────────────────────────────────────
    "landscape": ["nature", "scenery"], "mountain": ["nature", "scenery"],
    "snow": ["nature", "winter"], "beach": ["nature", "sea", "scenery"],
    "ocean": ["nature", "sea", "water"], "lake": ["nature", "water"],
    "river": ["nature", "water"], "waterfall": ["nature", "water"],
    "forest": ["nature", "trees"], "trees": ["nature"], "flowers": ["nature", "plant"],
    "rose": ["flowers", "nature", "plant"], "garden": ["nature", "plant"],
    "plant": ["nature"], "desert": ["nature", "scenery"], "field": ["nature"],
    "sky": ["nature"], "clouds": ["sky", "nature"], "sunset": ["sky", "nature", "scenery"],
    "sunrise": ["sky", "nature"], "night sky": ["sky", "night"], "stars": ["sky", "night", "space"],
    "moon": ["sky", "night", "space"], "rain": ["weather"], "lightning": ["weather", "storm"],
    "rainbow": ["sky", "weather"], "fireworks": ["night", "celebration", "festival"],
    "space": ["astronomy"], "planet": ["space", "astronomy"], "galaxy": ["space", "astronomy"],

    # ── Places & buildings ───────────────────────────────────────────────────
    "city": ["urban"], "street": ["urban", "road"], "road": ["travel"],
    "skyscraper": ["building", "city"], "house": ["building", "home"],
    "temple": ["building", "religion"], "church": ["building", "religion"],
    "mosque": ["building", "religion"], "monument": ["building", "travel"],
    "taj mahal": ["monument", "india", "travel"], "bridge": ["building"],
    "castle": ["building"], "classroom": ["indoor", "school", "college"],
    "office": ["indoor", "work"], "bedroom": ["indoor", "home"],
    "kitchen": ["indoor", "home"], "living room": ["indoor", "home"],
    "restaurant": ["indoor", "food"], "shop": ["indoor"], "library": ["indoor", "books"],
    "hospital": ["indoor"], "airport": ["travel"], "railway station": ["travel", "train"],
    "stadium": ["sports"], "park": ["nature", "outdoor"], "village": ["rural"],
    "farm": ["rural", "nature"], "hotel room": ["indoor", "travel"],
    "swimming pool": ["water", "sports"],

    # ── Food & drink ─────────────────────────────────────────────────────────
    "food": [], "pizza": ["food"], "burger": ["food"], "sandwich": ["food"],
    "noodles": ["food"], "pasta": ["food"], "rice": ["food"], "curry": ["food", "indian food"],
    "biryani": ["food", "indian food"], "dosa": ["food", "indian food"],
    "samosa": ["food", "indian food", "snack"], "bread": ["food"], "salad": ["food"],
    "fruit": ["food"], "vegetables": ["food"], "cake": ["food", "dessert"],
    "birthday cake": ["cake", "birthday", "celebration", "food"],
    "ice cream": ["food", "dessert"], "chocolate": ["food", "dessert"],
    "sweets": ["food", "dessert"], "coffee": ["drink"], "tea": ["drink"],
    "juice": ["drink"], "beer": ["drink", "alcohol"], "wine": ["drink", "alcohol"],
    "breakfast": ["food"], "fast food": ["food"],

    # ── Vehicles ─────────────────────────────────────────────────────────────
    "car": ["vehicle"], "sports car": ["car", "vehicle"], "motorcycle": ["vehicle", "bike"],
    "bicycle": ["vehicle", "bike"], "bus": ["vehicle"], "truck": ["vehicle"],
    "train": ["vehicle", "travel"], "airplane": ["vehicle", "travel"],
    "helicopter": ["vehicle"], "boat": ["vehicle", "water"], "ship": ["vehicle", "sea"],
    "auto rickshaw": ["vehicle", "india"], "tractor": ["vehicle", "farm"],
    "rocket": ["space", "vehicle"], "traffic": ["road", "vehicle", "city"],

    # ── Sports & activities ──────────────────────────────────────────────────
    "football": ["sports"], "football match": ["football", "sports", "match"],
    "soccer": ["football", "sports"], "cricket": ["sports"],
    "cricket match": ["cricket", "sports", "match"], "basketball": ["sports"],
    "tennis": ["sports"], "badminton": ["sports"], "table tennis": ["sports"],
    "volleyball": ["sports"], "baseball": ["sports"], "hockey": ["sports"],
    "chess": ["game", "board game"], "swimming": ["sports", "water"],
    "running": ["sports", "fitness"], "gym": ["fitness", "sports"],
    "yoga": ["fitness"], "cycling": ["sports", "bicycle"], "boxing": ["sports"],
    "martial arts": ["sports"], "skateboarding": ["sports"], "skiing": ["sports", "snow"],
    "hiking": ["nature", "travel"], "camping": ["nature", "travel"],
    "concert": ["music", "event", "crowd"], "dance performance": ["dance", "event"],
    "playing guitar": ["music", "guitar"], "playing piano": ["music", "piano"],
    "singing": ["music"], "drums": ["music"], "festival": ["celebration", "event"],
    "diwali": ["festival", "india", "celebration"], "holi": ["festival", "india", "celebration"],
    "christmas": ["festival", "celebration"], "birthday party": ["party", "birthday", "celebration"],

    # ── Gaming & screens ─────────────────────────────────────────────────────
    "video game": ["gaming"], "gameplay screenshot": ["video game", "gaming", "screenshot"],
    "minecraft": ["video game", "gaming"], "game controller": ["gaming"],
    "screenshot": ["screen"], "desktop screenshot": ["screenshot", "computer"],
    "phone screenshot": ["screenshot", "phone"], "chat screenshot": ["screenshot", "chat", "message"],
    "whatsapp chat": ["chat screenshot", "chat", "message"],
    "website": ["screenshot", "web"], "source code": ["code", "programming", "screenshot"],
    "code editor": ["code", "programming", "screenshot"], "terminal": ["code", "programming", "computer"],
    "error message": ["screenshot", "computer"], "spreadsheet": ["document", "data"],
    "presentation slide": ["document", "slides"], "user interface": ["design", "screenshot"],
    "app icon": ["icon", "logo"], "logo": ["design"], "icon": ["design"],

    # ── Documents & study ────────────────────────────────────────────────────
    "document": ["text"], "printed text": ["document", "text"], "handwritten notes": ["notes", "text", "study"],
    "notebook": ["notes", "study"], "whiteboard": ["study", "college"], "blackboard": ["study", "college"],
    "math equations": ["math", "study"], "diagram": ["study"], "flowchart": ["diagram"],
    "chart": ["data", "graph"], "graph": ["data", "math"], "table": ["data"],
    "map": ["travel", "geography"], "receipt": ["document", "bill", "money"],
    "bill": ["document", "money"], "invoice": ["document", "bill", "money"],
    "id card": ["document", "identity"], "aadhaar card": ["id card", "document", "identity"],
    "passport": ["document", "identity", "travel"], "certificate": ["document"],
    "resume": ["document"], "form": ["document"], "ticket": ["document", "travel"],
    "book cover": ["book", "books"], "book": ["books"], "newspaper": ["document", "news"],
    "poster": ["design"], "meme": ["funny", "humor"], "comic": ["drawing", "funny"],
    "qr code": ["code"], "barcode": [],
    "circuit diagram": ["electronics", "diagram", "engineering"],

    # ── Objects ──────────────────────────────────────────────────────────────
    "laptop": ["computer", "electronics"], "computer": ["electronics"],
    "smartphone": ["phone", "electronics"], "keyboard": ["computer"],
    "camera": ["electronics", "photography"], "headphones": ["electronics", "music"],
    "television": ["electronics"], "watch": ["accessory"], "glasses": ["accessory"],
    "shoes": ["clothing", "fashion"], "clothes": ["clothing", "fashion"], "dress": ["clothing", "fashion"],
    "t-shirt": ["clothing"], "bag": ["accessory"], "jewellery": ["fashion", "accessory"],
    "furniture": ["home"], "chair": ["furniture"], "bed": ["furniture", "bedroom"],
    "guitar": ["music", "instrument"], "piano": ["music", "instrument"],
    "money": [], "coins": ["money"], "credit card": ["money", "card"],
    "toy": [], "teddy bear": ["toy"], "balloon": ["party"], "gift": ["celebration"],
    "electronics": [], "robot": ["technology"], "drone": ["technology"],
    "medicine": ["health"], "tools": [], "car engine": ["car", "engineering"],
    "printed circuit board": ["electronics", "engineering"],

    # ── Art & style ──────────────────────────────────────────────────────────
    "drawing": ["art"], "sketch": ["drawing", "art"], "painting": ["art"],
    "anime": ["cartoon", "art"], "cartoon": ["art"], "3d render": ["art", "design"],
    "wallpaper": ["background"], "abstract art": ["art"], "pixel art": ["art", "gaming"],
    "black and white photo": ["photo"], "blurry photo": ["photo"],
    "night photo": ["night", "photo"], "aerial view": ["photo", "drone"],
    "close-up": ["photo"], "food photography": ["food", "photo"],
}

# Prompt ensembles: averaging several phrasings makes CLIP's zero-shot tagging
# more reliable than a single "a photo of X".
PROMPT_TEMPLATES = [
    "a photo of {}.",
    "a picture showing {}.",
    "an image of {}.",
]


def expand_tags(tags: list[str]) -> list[str]:
    """Add parent categories (recursively) and de-duplicate, keeping order."""
    out: list[str] = []
    seen: set[str] = set()

    def add(t: str, depth: int = 0):
        if t in seen or depth > 4:
            return
        seen.add(t)
        out.append(t)
        for p in TAGS.get(t, []):
            add(p, depth + 1)

    for t in tags:
        add(t)
    return out
