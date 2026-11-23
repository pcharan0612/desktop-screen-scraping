from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional, Tuple


@dataclass
class Word:
    text: str
    conf: float
    left: int
    top: int
    width: int
    height: int
    block_num: int
    par_num: int
    line_num: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.top + self.height / 2.0

    @property
    def line_key(self) -> Tuple[int, int, int]:
        return (self.block_num, self.par_num, self.line_num)


@dataclass
class TextLine:
    text: str
    conf: float
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2.0

    @property
    def center_y(self) -> float:
        return self.top + self.height / 2.0


@dataclass
class ScrapedProduct:
    title: str
    price: float
    rating: Optional[float] = None
    category: Optional[str] = None
    screen_index: int = 0
    source_url: Optional[str] = None

    def key(self) -> Tuple[str, float]:
        normalized = "".join(self.title.lower().split())
        return (normalized, round(float(self.price), 2))

    def to_dict(self) -> dict:
        return asdict(self)
