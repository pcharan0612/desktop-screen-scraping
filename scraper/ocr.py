"""OCR extraction helpers for turning screenshots into product records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
import pytesseract
from PIL import Image

from scraper import config
from scraper.models import ScrapedProduct, TextLine, Word

UI_NOISE = frozenset(
    {
        "add to cart",
        "our styles",
        "home",
        "products",
        "search products",
        "all categories",
        "all prices",
        "all ratings",
        "your cart",
        "no product in the cart",
        "order summary",
        "order confirmed",
        "checkout",
        "sorry, no results",
        "fashion that speaks",
        "©",
        "notifications",
        "all rights reserved",
        "email",
        "full name",
        "address",
        "payment",
        "menu",
    }
)

_COMMA_VARIANTS = ",:;，：；、"


@dataclass
class _Column:
    min_left: int
    max_right: int
    mean_center_x: float
    count: int = 1


def configure_tesseract(cmd: str | None = None) -> None:
    path = Path(cmd or config.TESSERACT_CMD)
    if not path.is_file():
        raise RuntimeError(
            f"Tesseract executable not found at '{path}'. "
            "Install Tesseract or set TESSERACT_CMD to the tesseract.exe path."
        )
    pytesseract.pytesseract.tesseract_cmd = str(path)


def tesseract_version() -> str:
    return str(pytesseract.get_tesseract_version())


def words_from_image(
    img: Image.Image, conf_threshold: int = config.OCR_CONF_THRESHOLD
) -> list[Word]:
    array = np.asarray(img.convert("RGB"))
    darkness = np.min(array, axis=2).astype(np.uint8)
    gray = Image.fromarray(darkness)
    scale = max(1, int(config.OCR_UPSCALE))
    if scale > 1:
        gray = gray.resize(
            (gray.width * scale, gray.height * scale), Image.Resampling.LANCZOS
        )
    data = pytesseract.image_to_data(
        gray,
        lang=config.OCR_LANG,
        config=f"--psm {config.OCR_PSM}",
        output_type=pytesseract.Output.DICT,
    )
    words: list[Word] = []
    for index in range(len(data["text"])):
        text = str(data["text"][index]).strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][index])
        except (TypeError, ValueError):
            continue
        if conf < conf_threshold:
            continue
        words.append(
            Word(
                text=text,
                conf=conf,
                left=int(round(float(data["left"][index]) / scale)),
                top=int(round(float(data["top"][index]) / scale)),
                width=int(round(float(data["width"][index]) / scale)),
                height=int(round(float(data["height"][index]) / scale)),
                block_num=int(float(data["block_num"][index])),
                par_num=int(float(data["par_num"][index])),
                line_num=int(float(data["line_num"][index])),
            )
        )
    return words


def lines_from_image(
    img: Image.Image, conf_threshold: int = config.OCR_CONF_THRESHOLD
) -> list[TextLine]:
    groups: dict[tuple[int, int, int], list[Word]] = {}
    for word in words_from_image(img, conf_threshold):
        groups.setdefault(word.line_key, []).append(word)

    lines: list[TextLine] = []
    for group in groups.values():
        ordered = sorted(group, key=lambda word: (word.left, word.top))
        left = min(word.left for word in ordered)
        top = min(word.top for word in ordered)
        right = max(word.right for word in ordered)
        bottom = max(word.bottom for word in ordered)
        text = " ".join(word.text for word in ordered)
        conf = round(sum(word.conf for word in ordered) / len(ordered), 1)
        lines.append(
            TextLine(
                text=text,
                conf=conf,
                left=left,
                top=top,
                width=right - left,
                height=bottom - top,
            )
        )
    lines.sort(key=lambda line: (line.top, line.left))
    return lines


def normalize_text(text: str) -> str:
    normalized = text.replace("₹", "Rs.")
    normalized = re.sub(
        r"(?i)\brs\s*[" + re.escape(_COMMA_VARIANTS) + r"]\s*", "Rs.", normalized
    )
    normalized = re.sub(r"(?i)\brs\s*\.\s*", "Rs.", normalized)
    return " ".join(normalized.split())


def parse_price(text: str) -> float | None:
    match = re.search(config.PRICE_PATTERN, normalize_text(text), re.IGNORECASE)
    if match is None:
        return None
    try:
        value = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    if value <= 0 or value > 1_000_000:
        return None
    return value


def parse_rating(text: str) -> float | None:
    match = re.search(config.RATING_PATTERN, normalize_text(text))
    if match is None:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    if 0.0 <= value <= 5.0:
        return value
    return None


def _is_noise_text(text: str) -> bool:
    normalized = " ".join(text.split()).lower().strip(" \t\r\n.:;!-_|")
    if not normalized:
        return True
    if normalized.startswith("©"):
        return True
    return normalized in UI_NOISE


def _clean_title(text: str) -> str:
    cleaned = text.strip("|-.;&=_ \t\r\n")
    cleaned = " ".join(cleaned.split())
    return cleaned.strip("|-.;&=_ ")


_BARE_RATING_RE = re.compile(r"^[^0-9]{0,3}\s*([0-5](?:[.,][0-9]+)?)\s*$")


def _bare_rating(text: str) -> float | None:
    match = _BARE_RATING_RE.match(normalize_text(text))
    if match is None:
        return None
    try:
        value = float(match.group(1).replace(",", "."))
    except ValueError:
        return None
    if 0.0 < value <= 5.0:
        return value
    return None


def extract_products(
    lines: Sequence[TextLine],
    screen_index: int = 0,
    column_gap: int = 100,
    title_gap: int = 220,
    rating_gap: int = 90,
    rating_resolver: (
        Callable[[TextLine, tuple[float, float], int], float | None] | None
    ) = None,
) -> list[ScrapedProduct]:
    prices: dict[int, float] = {}
    ratings: dict[int, float] = {}
    for line in lines:
        price = parse_price(line.text)
        if price is not None:
            prices[id(line)] = price
        rating = parse_rating(line.text)
        if rating is not None:
            ratings[id(line)] = rating

    price_lines = [line for line in lines if id(line) in prices]
    rating_lines = [line for line in lines if id(line) in ratings]

    deduped: list[TextLine] = []
    for line in sorted(price_lines, key=lambda item: item.conf, reverse=True):
        if any(
            abs(line.center_x - kept.center_x) <= column_gap
            and abs(line.top - kept.top) < 15
            for kept in deduped
        ):
            continue
        deduped.append(line)
    price_lines = deduped

    columns: list[_Column] = []
    column_index: dict[int, int] = {}
    for line in sorted(price_lines, key=lambda item: item.center_x):
        for index, column in enumerate(columns):
            if abs(line.center_x - column.mean_center_x) <= column_gap:
                column.min_left = min(column.min_left, line.left)
                column.max_right = max(column.max_right, line.right)
                column.mean_center_x = (
                    column.mean_center_x * column.count + line.center_x
                ) / (column.count + 1)
                column.count += 1
                column_index[id(line)] = index
                break
        else:
            columns.append(
                _Column(
                    min_left=line.left,
                    max_right=line.right,
                    mean_center_x=line.center_x,
                )
            )
            column_index[id(line)] = len(columns) - 1

    price_ids = {id(line) for line in price_lines}
    rating_ids = {id(line) for line in rating_lines}

    extra_ratings: dict[int, float] = {}
    for other in lines:
        if id(other) in price_ids or id(other) in rating_ids:
            continue
        value = _bare_rating(other.text)
        if value is not None:
            extra_ratings[id(other)] = value

    ordered_columns = sorted(columns, key=lambda item: item.mean_center_x)

    def column_band(index: int) -> tuple[float, float]:
        column = columns[index]
        position = ordered_columns.index(column)
        margin = max(column_gap * 2, 200)
        center = column.mean_center_x
        left = (
            center - margin
            if position == 0
            else (ordered_columns[position - 1].mean_center_x + center) / 2
        )
        right = (
            center + margin
            if position == len(ordered_columns) - 1
            else (center + ordered_columns[position + 1].mean_center_x) / 2
        )
        return left, right

    def in_band(other: TextLine, band: tuple[float, float]) -> bool:
        return other.right >= band[0] and other.left <= band[1]

    records: list[tuple[int, float, str, float, float | None]] = []
    for line in price_lines:
        price = prices[id(line)]
        band = column_band(column_index[id(line)])
        candidates = [
            other
            for other in lines
            if id(other) not in price_ids
            and id(other) not in rating_ids
            and id(other) not in extra_ratings
            and not _is_noise_text(other.text)
            and other.height <= 80
            and in_band(other, band)
            and other.top < line.top + 5
            and line.top - other.bottom <= title_gap
        ]
        candidates.sort(key=lambda item: line.top - item.bottom)
        selected: list[TextLine] = []
        for candidate in candidates:
            if line.top - candidate.bottom >= 0:
                selected.append(candidate)
                break
        if selected:
            selected_ids = {id(selected[0])}
            current = selected[0]
            while len(selected) < 2:
                above = [
                    candidate
                    for candidate in candidates
                    if id(candidate) not in selected_ids
                    and candidate.bottom <= current.top + 2
                ]
                if not above:
                    break
                above.sort(key=lambda item: current.top - item.bottom)
                next_line = above[0]
                if current.top - next_line.bottom > 60:
                    break
                selected.append(next_line)
                selected_ids.add(id(next_line))
                current = next_line
        if not selected:
            continue
        title = _clean_title(
            " ".join(item.text for item in reversed(selected))
        )
        if len(title) < 3:
            continue

        rating: float | None = None
        rating_candidates: list[tuple[float, TextLine]] = []
        for other in rating_lines:
            if (
                in_band(other, band)
                and other.top >= line.top - 5
                and other.top - line.bottom <= rating_gap
            ):
                rating_candidates.append((ratings[id(other)], other))
        for other in lines:
            if (
                id(other) in extra_ratings
                and in_band(other, band)
                and other.top >= line.top - 5
                and other.top - line.bottom <= rating_gap
            ):
                rating_candidates.append((extra_ratings[id(other)], other))
        if rating_candidates:
            rating = min(
                rating_candidates,
                key=lambda item: abs(item[1].center_y - line.center_y),
            )[0]
        if rating is None and rating_resolver is not None:
            rating = rating_resolver(line, band, rating_gap)

        row = int(line.center_y // 100)
        records.append((row, line.center_x, title, price, rating))

    records.sort(key=lambda item: (item[0], item[1]))
    return [
        ScrapedProduct(
            title=title,
            price=price,
            rating=rating,
            screen_index=screen_index,
        )
        for _, _, title, price, rating in records
    ]


def _rating_from_crop(
    img: Image.Image,
    price_line: TextLine,
    band: tuple[float, float],
    rating_gap: int,
) -> float | None:
    top = max(0, price_line.bottom + 2)
    bottom = min(img.height, price_line.bottom + rating_gap)
    left = max(0, int(band[0]))
    right = min(img.width, int(band[1]))
    if right - left < 20 or bottom - top < 8:
        return None
    crop = img.crop((left, top, right, bottom)).convert("RGB")
    array = np.asarray(crop)
    gray = Image.fromarray(np.min(array, axis=2).astype(np.uint8))
    scale = 4
    gray = gray.resize(
        (gray.width * scale, gray.height * scale), Image.Resampling.LANCZOS
    )
    text = pytesseract.image_to_string(
        gray,
        lang=config.OCR_LANG,
        config=f"--psm {config.OCR_PSM}",
    )
    for line_text in text.splitlines():
        if not line_text.strip():
            continue
        value = parse_rating(line_text)
        if value is None:
            value = _bare_rating(line_text)
        if value is not None:
            return value
    return None


def extract_products_from_image(
    img: Image.Image, screen_index: int = 0
) -> list[ScrapedProduct]:
    lines = lines_from_image(img)

    def resolver(
        price_line: TextLine, band: tuple[float, float], rating_gap: int
    ) -> float | None:
        return _rating_from_crop(img, price_line, band, rating_gap)

    return extract_products(
        lines, screen_index=screen_index, rating_resolver=resolver
    )
