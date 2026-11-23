"""Export scraped products to JSON and CSV files."""

import csv
import json
import re
from pathlib import Path
from typing import Iterable, Sequence

from scraper import config
from scraper.models import ScrapedProduct

CSV_FIELDS = ("title", "price", "rating", "category", "screen_index", "source_url")

_TOKEN_SPLIT = re.compile(r"[^0-9a-z]+")


def _title_tokens(title: str) -> list[str]:
    return [token for token in _TOKEN_SPLIT.split(title.lower()) if len(token) >= 3]


def _tokens_match(left: str, right: str) -> bool:
    if left == right:
        return True
    if left.startswith(right) or right.startswith(left):
        return True
    return abs(len(left) - len(right)) <= 3 and (left in right or right in left)


def _is_fragment(shorter: str, longer: str) -> bool:
    short_tokens = _title_tokens(shorter)
    if not short_tokens:
        return False
    long_tokens = _title_tokens(longer)
    long_set = set(long_tokens)
    matches = 0
    for token in short_tokens:
        if token in long_set or any(_tokens_match(token, other) for other in long_tokens):
            matches += 1
    return matches >= max(1, int(len(short_tokens) * 0.8))


def dedupe_products(products: Iterable[ScrapedProduct]) -> list[ScrapedProduct]:
    unique: list[ScrapedProduct] = []
    seen: set[tuple[str, float]] = set()
    for product in products:
        if len(product.title) < 3:
            continue
        key = product.key()
        if key in seen:
            continue
        merged = False
        for index, kept in enumerate(unique):
            if round(kept.price, 2) != round(product.price, 2):
                continue
            if not (
                _is_fragment(product.title, kept.title)
                or _is_fragment(kept.title, product.title)
            ):
                continue
            if len(product.title) > len(kept.title):
                unique[index] = ScrapedProduct(
                    title=product.title,
                    price=product.price,
                    rating=product.rating if product.rating is not None else kept.rating,
                    category=product.category or kept.category,
                    screen_index=product.screen_index,
                    source_url=product.source_url or kept.source_url,
                )
                seen.add(key)
            elif kept.rating is None and product.rating is not None:
                kept.rating = product.rating
            merged = True
            break
        if merged:
            continue
        seen.add(key)
        unique.append(product)
    return unique


def save_json(
    products: Sequence[ScrapedProduct],
    path: str | Path = config.PRODUCTS_JSON,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump([product.to_dict() for product in products], handle, ensure_ascii=False, indent=2)
    return target


def save_csv(
    products: Sequence[ScrapedProduct],
    path: str | Path = config.PRODUCTS_CSV,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for product in products:
            writer.writerow(product.to_dict())
    return target


def save_all(
    products: Sequence[ScrapedProduct],
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    directory = Path(output_dir) if output_dir is not None else config.OUTPUT_DIR
    return {
        "json": save_json(products, directory / "products.json"),
        "csv": save_csv(products, directory / "products.csv"),
    }
