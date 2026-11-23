from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"
PRODUCTS_JSON = OUTPUT_DIR / "products.json"
PRODUCTS_CSV = OUTPUT_DIR / "products.csv"

TESSERACT_CMD = os.environ.get(
    "TESSERACT_CMD",
    r"C:\Users\FL_LPT-370\AppData\Local\Tesseract-OCR\tesseract.exe",
)

DEFAULT_URL = "http://localhost:5173/Ecommerce/#/products"
BROWSER_TITLE_HINTS = ("localhost", "ecommerce", "vite + react")
BROWSER_CHROME_HEIGHT = 90

DEFAULT_MAX_SCROLLS = 15
DEFAULT_SCROLL_DELAY = 1.0
DEFAULT_SCROLL_CLICKS = -700
STOP_AFTER_EMPTY_SCANS = 2

OCR_CONF_THRESHOLD = 35
OCR_LANG = "eng"
OCR_PSM = 11
OCR_UPSCALE = 2

PRICE_PATTERN = r"Rs\.?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)"
RATING_PATTERN = r"(?:⭐|★|✩|\*)\s*([0-9](?:\.[0-9]+)?)"
