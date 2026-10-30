import json
import re
import unicodedata
import uuid

from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "dataset" / "raw"
CATEGORIES_FILE = Path(__file__).parent / "categories.json"


def slugify(value):
    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9_-]+", "_", value)
    return value.strip("_")


def load_categories():
    if not CATEGORIES_FILE.exists():
        return []

    with open(CATEGORIES_FILE, "r", encoding="utf-8") as file:
        return json.load(file).get("categories", [])


def add_category(name):
    category = slugify(name)

    if not category:
        raise ValueError("Nom de catégorie invalide.")

    categories = load_categories()

    if category not in categories:
        categories.append(category)

        CATEGORIES_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with open(CATEGORIES_FILE, "w", encoding="utf-8") as file:
            json.dump(
                {"categories": categories},
                file,
                indent=4,
                ensure_ascii=False
            )

    return category


def category_counts():
    result = {}

    for category in load_categories():
        folder = DATASET_DIR / category

        if folder.exists():
            result[category] = len(
                list(folder.glob("*.jpg"))
            )
        else:
            result[category] = 0

    return result


def save_image(frame, category):
    category = slugify(category)

    if category not in load_categories():
        raise ValueError("Catégorie inconnue.")

    folder = DATASET_DIR / category
    folder.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{timestamp}_{uuid.uuid4().hex[:6]}.jpg"

    destination = folder / filename

    import cv2

    success = cv2.imwrite(str(destination), frame)

    if not success:
        raise IOError("Impossible d'enregistrer l'image.")

    return destination
