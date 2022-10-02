from __future__ import annotations
import curses
import time

from lib.base import E_RESIZE, E_KEY, E_TICK, Quit, Style, Widget


def _init_styles(styles: StyleDict) -> None:
    cnum = 102
    colors: dict[tuple[int, int, int], int] = {}

    curses.init_color(curses.COLOR_WHITE, 1000, 1000, 1000)
    curses.init_color(curses.COLOR_BLACK, 0, 0, 0)
    colors[1000, 1000, 1000] = curses.COLOR_WHITE
    colors[0, 0, 0] = curses.COLOR_BLACK

    def add_color(rgb: tuple[int, int, int]) -> int:
        nonlocal cnum
        if rgb in colors:
            return colors[rgb]
        cnum += 1
        colors[rgb] = cnum
        curses.init_color(cnum, *rgb)
        return cnum

    for style, (fg, bg) in styles.items():
        curses.init_pair(style.value, add_color(fg), add_color(bg))


def _loop(win: curses._CursesWindow, root: Widget, styles: StyleDict, fps: int) -> None:
    _init_styles(styles)

    curses.curs_set(0)
    ms = 1000 // fps
    win.timeout(ms)

    my, mx = win.getmaxyx()
    root.dispatch(E_RESIZE, (my, mx))

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
                    root.dispatch(E_KEY, (key,))

            root.dispatch(E_TICK, ())
        except Quit:
            return

        cells = root.cells(my, mx)
        for rect in cells:
            y1 = rect.y
            x1 = rect.x
            y2 = y1 + rect.height - 1
            x2 = x1 + rect.width - 1
            y1 = min(max(0, y1), my)
            x1 = min(max(0, x1), mx)
            y2 = min(max(0, y2), my)
            x2 = min(max(0, x2), mx)

            for y in range(y1, y2+1):
                pad.addstr(y, x1, rect.char * (x2 - x1 + 1), curses.color_pair(rect.style.value))

        pad.refresh(0, 0, 0, 0, my - 1, mx - 1)
        end = time.monotonic()
        to_sleep = ms/1000 - (end - start)
        if to_sleep > 0:
            time.sleep(to_sleep)




StyleDict = dict[Style, tuple[tuple[int, int, int], tuple[int, int, int]]]


_default_styles: StyleDict = {
    Style.default: ((1000, 1000, 1000), (0, 0, 0)),
    Style.red: ((1000, 1000, 1000), (1000, 0, 0)),
    Style.green: ((0, 0, 0), (0, 1000, 0)),
    Style.blue: ((1000, 1000, 1000), (0, 0, 1000)),
    Style.cyan: ((0, 0, 0), (0, 420, 1000)),
    Style.white: ((0, 0, 0, ), (1000, 1000, 1000)),
}


def run(root_widget: Widget, *, fps: int = 30, styles: StyleDict = {}) -> None:
    styles = {**_default_styles, **styles}
    curses.wrapper(_loop, root_widget, styles, fps)
