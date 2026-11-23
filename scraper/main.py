"""Command-line interface for the desktop screen scraper."""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Sequence

from PIL import Image

from scraper import capture, config, export, ocr
from scraper.models import ScrapedProduct


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scraper.main",
        description="Capture a browser window and scrape products with OCR.",
    )
    parser.add_argument(
        "--url",
        default=config.DEFAULT_URL,
        help="URL of the product page",
    )
    parser.add_argument(
        "--window-hint",
        action="append",
        default=None,
        help="substring of browser window title (repeatable)",
    )
    parser.add_argument(
        "--region",
        default=None,
        help='capture region "left,top,width,height"',
    )
    parser.add_argument(
        "--max-scrolls",
        type=int,
        default=config.DEFAULT_MAX_SCROLLS,
        help="maximum number of screen captures",
    )
    parser.add_argument(
        "--scroll-delay",
        type=float,
        default=config.DEFAULT_SCROLL_DELAY,
        help="seconds to wait after each scroll",
    )
    parser.add_argument(
        "--scroll-clicks",
        type=int,
        default=config.DEFAULT_SCROLL_CLICKS,
        help="mouse wheel clicks per scroll (negative scrolls down)",
    )
    parser.add_argument(
        "--no-focus",
        action="store_true",
        help="do not focus the browser window",
    )
    parser.add_argument(
        "--open-url",
        action="store_true",
        help="open --url in the default browser before capture",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=2.0,
        help="seconds to wait after opening the URL / before the first capture",
    )
    parser.add_argument(
        "--output-dir",
        default=str(config.OUTPUT_DIR),
        help="directory for screenshots and exported files",
    )
    parser.add_argument(
        "--tesseract",
        default=None,
        help="path to tesseract.exe",
    )
    parser.add_argument(
        "--parse-image",
        default=None,
        help="path to an existing screenshot to OCR/parse instead of live capture",
    )
    parser.add_argument(
        "--list-windows",
        action="store_true",
        help="list open window titles and exit",
    )
    return parser


def validate_region(
    parser: argparse.ArgumentParser,
    text: str,
) -> tuple[int, int, int, int]:
    parts = text.split(",")
    if len(parts) != 4:
        parser.error("--region must be four comma-separated integers: left,top,width,height")
    try:
        left, top, width, height = (int(part.strip()) for part in parts)
    except ValueError:
        parser.error("--region values must be integers: left,top,width,height")
    if width <= 0 or height <= 0:
        parser.error("--region width and height must be positive")
    return left, top, width, height


def window_title(window: object) -> str:
    title = getattr(window, "title", None)
    if title is not None:
        return str(title)
    return str(window)


def print_results(
    products: Sequence[ScrapedProduct],
    paths: dict[str, Path],
) -> None:
    print("TITLE | PRICE | RATING")
    print("-" * 80)
    for product in products:
        title = product.title[:60]
        rating = "-" if product.rating is None else f"{product.rating:g}"
        print(f"{title} | {product.price:.2f} | {rating}")
    print("-" * 80)
    print(f"Total unique products: {len(products)}")
    print(f"JSON: {paths['json']}")
    print(f"CSV: {paths['csv']}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    capture.configure_safety()
    ocr.configure_tesseract(args.tesseract)

    if args.list_windows:
        windows = capture.list_windows()
        if windows:
            for title in windows:
                print(title)
        else:
            print("No windows found.")
        return 0

    if args.parse_image:
        image_path = Path(args.parse_image)
        if not image_path.exists():
            parser.error(f"--parse-image file not found: {image_path}")
        with Image.open(image_path) as handle:
            image = handle.convert("RGB")
        products = ocr.extract_products_from_image(image, screen_index=0)
        unique_products = export.dedupe_products(products)
        paths = export.save_all(unique_products, args.output_dir)
        print_results(unique_products, paths)
        return 0 if unique_products else 1

    try:
        region: tuple[int, int, int, int] | None
        if args.region:
            region = validate_region(parser, args.region)
        else:
            window = capture.pick_browser_window(args.window_hint)
            if window is not None:
                if not args.no_focus and not capture.focus_window(window):
                    logging.warning("Could not focus window: %s", window_title(window))
                region = capture.get_content_region(window)
                logging.info("Window: %s", window_title(window))
                logging.info("Capture region: %s", region)
            else:
                logging.warning(
                    "No browser window found; capturing the full screen. "
                    "Use --region to limit the capture area."
                )
                region = None

        scroll_position: tuple[int, int] | None = None
        if region is not None:
            scroll_position = (
                region[0] + region[2] // 2,
                region[1] + region[3] // 2,
            )

        if args.open_url:
            if capture.open_url(args.url):
                logging.info("Opened URL: %s", args.url)
            else:
                logging.warning("Could not open URL: %s", args.url)

        if args.wait > 0:
            time.sleep(args.wait)

        capture.scroll_to_top(scroll_position)
        time.sleep(1.2)

        screenshot_dir = Path(args.output_dir) / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        all_products: list[ScrapedProduct] = []
        seen: set[tuple[str, float]] = set()
        empty_streak = 0
        previous_image: Image.Image | None = None

        for index in range(args.max_scrolls):
            image = capture.grab_screen(region)
            if (
                index > 0
                and previous_image is not None
                and capture.images_similar(previous_image, image)
            ):
                logging.info("Reached bottom of page")
                break
            previous_image = image

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            capture.save_image(image, screenshot_dir / f"scan_{index:02d}_{stamp}.png")

            products = ocr.extract_products_from_image(image, screen_index=index)
            count_new = 0
            for product in products:
                key = product.key()
                if key in seen:
                    continue
                seen.add(key)
                count_new += 1
            all_products.extend(products)

            logging.info(
                "Scan %d/%d: %d product(s), %d new",
                index + 1,
                args.max_scrolls,
                len(products),
                count_new,
            )

            if count_new == 0:
                empty_streak += 1
            else:
                empty_streak = 0
            if empty_streak >= config.STOP_AFTER_EMPTY_SCANS:
                logging.info("No new products after %d scan(s); stopping", empty_streak)
                break

            capture.scroll_page(args.scroll_clicks, scroll_position)
            time.sleep(args.scroll_delay)
    except KeyboardInterrupt:
        logging.warning("Interrupted by user.")
        return 130
    except Exception as exc:
        logging.error("Capture failed: %s", exc)
        return 1

    unique_products = export.dedupe_products(all_products)
    paths = export.save_all(unique_products, args.output_dir)
    print_results(unique_products, paths)
    return 0 if unique_products else 1


if __name__ == "__main__":
    raise SystemExit(main())
