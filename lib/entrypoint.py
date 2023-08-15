from __future__ import annotations
import curses
import time
from typing import Iterable

from lib.base import E_RESIZE, E_KEY, E_TICK, Quit, Style, Widget


def _loop(win: curses._CursesWindow, root: Widget, styles: Styles, fps: int) -> None:
    curses.curs_set(0)
    ms = 1000 // fps
    win.timeout(ms)

    my, mx = win.getmaxyx()
    root.dispatch(E_RESIZE, (my, mx))

    styles.execute()

    while True:
        start = time.monotonic()
        ch = win.getch()

        my, mx = win.getmaxyx()
        pad = curses.newpad(my + 1, mx + 1)
        try:
            if ch != -1:
                key = curses.keyname(ch).decode("utf-8")
                if key == "KEY_RESIZE":
                    root.dispatch(E_RESIZE, (my, mx))
                else:
                    root.dispatch(E_KEY, key)

            root.dispatch(E_TICK)
        except Quit:
            return

        cells = root.cells(my, mx)
        for rect in cells:
            y1 = rect.y
            x1 = rect.x
            y2 = y1 + rect.height - 1
            x2 = x1 + rect.width - 1
            y1 = min(max(0, y1), my - 1)
            x1 = min(max(0, x1), mx - 1)
            y2 = min(max(0, y2), my - 1)
            x2 = min(max(0, x2), mx - 1)

            for y in range(y1, y2+1):
                pair = curses.color_pair(styles.pair_num(rect.style) or 0)
                pad.addstr(y, x1, rect.char * (x2 - x1 + 1), pair)

        pad.refresh(0, 0, 0, 0, my - 1, mx - 1)
        end = time.monotonic()
        to_sleep = ms/1000 - (end - start)
        if to_sleep > 0:
            time.sleep(to_sleep)


class Styles:
    def __init__(self) -> None:
        self._pair_counter = 1
        self._to_pair: dict[object, int] = {}
        self._pair_colors: dict[int, tuple[int, int]] = {}
        self._color_counter = 33
        self._to_color: dict[tuple[int, int, int], int] = {
            (0, 0, 0): curses.COLOR_BLACK,
            (1000, 1000, 1000): curses.COLOR_WHITE,
        }

    def execute(self) -> None:
        for rgb, color_num in self._to_color.items():
            curses.init_color(color_num, *rgb)
        for pair_num, (fg, bg) in self._pair_colors.items():
            curses.init_pair(pair_num, fg, bg)

    def _color_num(self, r: int, g: int, b: int) -> int:
        if (r, g, b) not in self._to_color:
            self._to_color[r, g, b] = self._color_counter
            self._color_counter += 1

        return self._to_color[r, g ,b]

    def add(self, key: object, fg: tuple[int, int, int], bg: tuple[int, int, int]) -> None:
        fgnum = self._color_num(*fg)
        bgnum = self._color_num(*bg)
        self._to_pair[key] = self._pair_counter
        self._pair_colors[self._pair_counter] = (fgnum, bgnum)
        self._pair_counter += 1

    def pair_num(self, key: object) -> int | None:
        return self._to_pair.get(key)


Rgb = tuple[int, int, int]


_default_styles: list[tuple[Style, Rgb, Rgb]] = [
    (Style.default, (1000, 1000, 1000), (0, 0, 0)),
    (Style.red, (1000, 1000, 1000), (1000, 0, 0)),
    (Style.green, (0, 0, 0), (0, 1000, 0)),
    (Style.blue, (1000, 1000, 1000), (0, 0, 1000)),
    (Style.cyan, (0, 0, 0), (0, 420, 1000)),
    (Style.white, (0, 0, 0), (1000, 1000, 1000)),
    (Style.dim, (1000, 1000, 1000), (200, 200, 200)),
]


def run(root_widget: Widget, *, fps: int = 30, extra_styles: Iterable[tuple[object, Rgb, Rgb]] = ()) -> None:
    styles = Styles()
    for style in _default_styles:
        styles.add(*style)
    for style in extra_styles:
        styles.add(*style)
    curses.wrapper(_loop, root_widget, styles, fps)
