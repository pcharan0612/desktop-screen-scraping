"""Screen capture, window discovery, and scrolling helpers."""

from __future__ import annotations

import time
import webbrowser
from pathlib import Path
from typing import Sequence, Tuple

import numpy as np
import pyautogui
import pygetwindow as gw
from PIL import Image

from . import config

Region = Tuple[int, int, int, int]

_COMMON_BROWSER_KEYWORDS = ("Chrome", "Edge", "Firefox", "Brave", "Opera", "Vivaldi", "localhost")


def configure_safety(failsafe: bool = True, pause: float = 0.2) -> None:
    pyautogui.FAILSAFE = failsafe
    pyautogui.PAUSE = pause


def list_windows() -> list[str]:
    lines: list[str] = []
    try:
        windows = list(gw.getAllWindows())
    except Exception:
        return lines
    for win in windows:
        if len(lines) >= 50:
            break
        title = _window_title(win)
        if not title:
            continue
        left = _window_int(win, "left", 0)
        top = _window_int(win, "top", 0)
        width = _window_int(win, "width", 0)
        height = _window_int(win, "height", 0)
        line = f"{title} | {left},{top} {width}x{height}"
        if _window_minimized(win):
            line += " | minimized"
        lines.append(line)
    return lines


def find_browser_windows(hints: Sequence[str] | None = None) -> list[gw.Window]:
    try:
        selected = config.BROWSER_TITLE_HINTS if hints is None else hints
        matchers = [str(hint).strip().lower() for hint in selected if str(hint).strip()]
        windows = list(gw.getAllWindows())
    except Exception:
        return []
    found: list[gw.Window] = []
    for win in windows:
        title = _window_title(win).lower()
        if title and any(matcher in title for matcher in matchers):
            found.append(win)
    return found


def pick_browser_window(hints: Sequence[str] | None = None) -> gw.Window | None:
    try:
        matches = find_browser_windows(hints)
        if matches:
            return matches[0]
        fallback = find_browser_windows(_COMMON_BROWSER_KEYWORDS)
        return fallback[0] if fallback else None
    except Exception:
        return None


def focus_window(win: gw.Window) -> bool:
    try:
        if _window_minimized(win):
            win.restore()
        win.activate()
        time.sleep(0.4)
        return True
    except Exception:
        return False


def get_content_region(win: gw.Window, chrome_height: int | None = None) -> Region:
    try:
        chrome = config.BROWSER_CHROME_HEIGHT if chrome_height is None else int(chrome_height)
    except Exception:
        chrome = 0
    try:
        screen_w, screen_h = (int(value) for value in pyautogui.size())
    except Exception:
        screen_w, screen_h = 1920, 1080
    left = _window_int(win, "left", 0)
    top = _window_int(win, "top", 0)
    width = _window_int(win, "width", screen_w)
    height = _window_int(win, "height", screen_h)
    left = max(0, min(left, screen_w))
    top = max(0, min(top + chrome, screen_h))
    width = max(0, min(width, screen_w - left))
    height = max(0, min(height - chrome, screen_h - top))
    if width < 200:
        width = min(200, screen_w)
        left = max(0, min(left, screen_w - width))
    if height < 200:
        height = min(200, screen_h)
        top = max(0, min(top, screen_h - height))
    return (left, top, width, height)


def grab_screen(region: Region | None = None) -> Image.Image:
    return pyautogui.screenshot(region=region).convert("RGB")


def save_image(img: Image.Image, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    img.save(target)
    return target


def scroll_page(
    clicks: int = config.DEFAULT_SCROLL_CLICKS,
    position: Tuple[int, int] | None = None,
) -> None:
    if position is not None:
        pyautogui.moveTo(position[0], position[1])
    pyautogui.scroll(clicks)


def scroll_to_top(
    position: Tuple[int, int] | None = None,
    steps: int = 40,
    clicks: int = 600,
) -> None:
    if position is not None:
        pyautogui.moveTo(position[0], position[1])
    for _ in range(max(1, steps)):
        pyautogui.scroll(abs(clicks))
        time.sleep(0.02)


def images_similar(a: Image.Image, b: Image.Image, tolerance: float = 2.0) -> bool:
    try:
        if a.size != b.size:
            b = b.resize(a.size, Image.Resampling.LANCZOS)
        arr_a = np.asarray(a.convert("RGB"), dtype=np.float32)
        arr_b = np.asarray(b.convert("RGB"), dtype=np.float32)
        if arr_a.shape != arr_b.shape or arr_a.size == 0:
            return False
        return float(np.mean(np.abs(arr_a - arr_b))) <= float(tolerance)
    except Exception:
        return False


def open_url(url: str) -> bool:
    try:
        webbrowser.open(url)
        return True
    except Exception:
        return False


def _window_title(win: gw.Window) -> str:
    try:
        return str(win.title).strip()
    except Exception:
        return ""


def _window_int(win: gw.Window, attr: str, default: int) -> int:
    try:
        return int(getattr(win, attr))
    except Exception:
        return default


def _window_minimized(win: gw.Window) -> bool:
    try:
        return bool(win.isMinimized)
    except Exception:
        return False
