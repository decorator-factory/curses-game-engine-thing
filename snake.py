from __future__ import annotations
import math
import random
import time
from typing_extensions import Unpack
from lib.entrypoint import run
from lib.base import E_KEY, EventKey, Widget, Var, Reactive, SimpleText, Rect, Style, Event, E_RESIZE, E_TICK, Cell, Quit
from typing import Callable, Iterable, Sequence

void_event = EventKey[Unpack[tuple[()]]]

E_QUIT = void_event("snake.quit")


class QuitHandler(Widget):
    def __init__(self) -> None:
        super().__init__()
        self.register(E_QUIT, self.on_quit)

    def on_quit(self) -> None:
        raise Quit


class OnKey(Widget):
    def __init__(self, keys: Iterable[str], event: EventKey[()], wrapped: Widget) -> None:
        super().__init__()
        self._keys = set(keys)
        self._wrapped = wrapped
        self._event = event
        self.register(E_KEY, self.on_key)

    def on_key(self, key: str) -> None:
        if key in self._keys:
            self._wrapped.dispatch(self._event, ())


class Foods(Widget):
    E_NEW_HEAD_POS =  EventKey[int, int]("snake.foods.new_head")

    def __init__(
        self,
        screen_size: Var[int, int],
        head_pos: Var[int, int],
        length: Var[int],
        score: Var[int],
    ) -> None:
        super().__init__()
        self._head_pos = head_pos
        self._length = length
        self._score = score
        self._points: set[tuple[int, int]] = set()

        self._screen_size = screen_size

        head_pos.subscribe(self.E_NEW_HEAD_POS, self)
        self.register(self.E_NEW_HEAD_POS, self._eat)

        self.register(E_TICK, self._on_tick)

    def _on_tick(self) -> None:
        if self._screen_size.value() != (0, 0) and not self._points:
            for _ in range(2):
                self._spawn_food()

    def _spawn_food(self) -> None:
        h, w = self._screen_size.value()
        while True:
            new_point = (random.randrange(5, h - 4), random.randrange(5, w//2 - 5))
            if new_point not in self._points:
                break
        self._points.add(new_point)

    def _eat(self, y: int, x: int) -> None:
        if (y, x) not in self._points:
            return
        self._points.remove((y, x))
        self._length.change(round(self._length.value()[0] * 1.5))
        self._spawn_food()
        self._score.change(self._score.value()[0] + 1)

    def cells(self, h: int, w: int, /) -> Iterable[Cell]:
        for y, x in self._points:
            yield from Rect(y, x*2, 1, 2, Style.green).cells(h, w)


class Snek(Widget):
    E_UP = void_event("snake.up")
    E_DOWN = void_event("snake.down")
    E_RIGHT = void_event("snake.right")
    E_LEFT = void_event("snake.left")
    E_ADVANCE = void_event("snake.advance")
    E_REVERSE = void_event("snake.reverse")

    def __init__(self, y: int, x: int, head_pos: Var[int, int], length: Var[int], dead: Var[bool]) -> None:
        super().__init__()
        self._body = [(y, x - d) for d in range(2)]
        self._dir = (0, 1)  # dy, dx
        self.register(Snek.E_RIGHT, self.on_right)
        self.register(Snek.E_LEFT, self.on_left)
        self.register(Snek.E_UP, self.on_up)
        self.register(Snek.E_DOWN, self.on_down)
        self.register(Snek.E_ADVANCE, self.on_advance)
        self.register(Snek.E_REVERSE, self.on_reverse)
        self._head_pos = head_pos
        self._length = length
        self._resting = False
        self._mq: list[void_event] = []
        length.change(len(self._body))
        head_pos.change(y, x)
        self._dead = dead

    def on_advance(self) -> None:
        self._resting = False
        dy, dx = self._dir
        new_body: list[tuple[int, int]] = []
        last_y, last_x = 0, 0

        for i, (y, x) in enumerate(self._body):
            if i > 0:
                dy, dx = last_y - y, last_x - x
            new_body.append((y + dy, x + dx))
            last_y, last_x = y, x

        if self._length.value()[0] > len(self._body):
            new_body.append(self._body[-1])

        self._body = new_body
        hy, hx = self._body[0]
        self._head_pos.change(hy, hx)

        if len(self._body) != len(set(self._body)):
            self._dead.change(True)

        if self._mq:
            self.dispatch(self._mq.pop(0), ())

    def on_reverse(self) -> None:
        if self._resting:
            self._mq.append(self.E_REVERSE)
            return
        self._body.reverse()
        hy1, hx1 = self._body[0]
        hy2, hx2 = self._body[1]
        self._dir = (hy1 - hy2, hx1 - hx2)

    def on_up(self) -> None:
        if self._resting:
            self._mq.append(self.E_UP)
            return
        if self._dir in {(0, 1), (0, -1)}:
            self._dir = (-1, 0)
            self._resting = True

    def on_down(self) -> None:
        if self._resting:
            self._mq.append(self.E_DOWN)
            return
        if self._dir in {(0, 1), (0, -1)}:
            self._dir = (1, 0)
            self._resting = True

    def on_right(self) -> None:
        if self._resting:
            self._mq.append(self.E_RIGHT)
            return
        if self._dir in {(1, 0), (-1, 0)}:
            self._dir = (0, 1)
            self._resting = True

    def on_left(self) -> None:
        if self._resting:
            self._mq.append(self.E_LEFT)
            return
        if self._dir in {(1, 0), (-1, 0)}:
            self._dir = (0, -1)
            self._resting = True

    def cells(self, h: int, w: int, /) -> Iterable[Cell]:
        for y, x in self._body:
            yield from Rect(y, x*2, 1, 2, Style.red).cells(h, w)


class TickReducer(Widget):
    def __init__(self, n: int, event: EventKey[()], wrapped: Widget) -> None:
        super().__init__()
        if n <= 0:
            raise ValueError(f"{n=}, expected at least 1")
        self._n = n
        self._wrapped = wrapped
        self._event = event
        self._tick = 0
        self.register(E_TICK, self.on_tick)

    def on_tick(self) -> None:
        self._tick += 1
        if self._tick >= self._n:
            self._wrapped.dispatch(self._event, ())
            self._tick = 0


class Boundary(Widget):
    E_UPDATE = EventKey[int, int]("boundary.update")

    def __init__(self, head_pos: Var[int, int], hw: Var[int, int], dead: Var[bool]) -> None:
        super().__init__()
        self._head_pos = head_pos
        self._hw = hw
        self._dead = dead
        head_pos.subscribe(self.E_UPDATE, self)
        hw.subscribe(self.E_UPDATE, self)
        self.register(self.E_UPDATE, self.on_update)

    def on_update(self, *_) -> None:
        head_y, head_x = self._head_pos.value()
        h, w = self._hw.value()

        if head_y < 0 or head_x < 0 or head_y >= h or head_x >= w // 2:
            self._dead.change(True)


class Seqw(Widget):
    E_NEXT = void_event("one_of.next")

    def __init__(self, steps: Sequence[Widget]):
        super().__init__()
        self._steps = list(steps)
        self.register(self.E_NEXT, self.on_next)

    def bubble(self, event: Event, /) -> None:
        active = self._steps[0]
        active.dispatch(event.key, event.payload)

    def on_next(self) -> None:
        self._steps.pop(0)
        if not self._steps:
            raise Quit

    def cells(self, h: int, w: int, /) -> Iterable[Cell]:
        active = self._steps[0]
        yield from active.cells(h, w)


class Group(Widget):
    def __init__(self, widgets: Iterable[Widget]) -> None:
        super().__init__()
        self._children = list(widgets)

    def bubble(self, event: Event, /) -> None:
        for ch in self._children:
            ch.dispatch(event.key, event.payload)

    def cells(self, h: int, w: int, /) -> Iterable[Cell]:
        for ch in self._children:
            yield from ch.cells(h, w)


class Onhw(Widget):
    def __init__(self, fn: Callable[[int, int], Widget]) -> None:
        super().__init__()
        self._fn = fn

    def cells(self, h: int, w: int, /) -> Iterable[Cell]:
        yield from self._fn(h, w).cells(h, w)


class WhenTrue(Widget):
    E_CHANGE = EventKey[bool]("when_true.change")

    def __init__(self, var: Var[bool], event: void_event, widget: Widget) -> None:
        super().__init__()
        self.register(self.E_CHANGE, self.on_change)
        var.subscribe(self.E_CHANGE, self)
        self._e = event
        self._widget = widget

    def on_change(self, value: bool) -> None:
        if value:
            self._widget.dispatch(self._e, ())


class Proxy(Widget):
    def __init__(self) -> None:
        super().__init__()
        self._wrapped = None

    def update(self, widget: Widget) -> None:
        self._wrapped = widget

    def bubble(self, event: Event, /) -> None:
        if self._wrapped:
            self._wrapped.dispatch(event.key, event.payload)

    def cells(self, h: int, w: int, /) -> Iterable[Cell]:
        if self._wrapped:
            yield from self._wrapped.cells(h, w)


def game():
    length = Var("length", (0,))
    head_pos = Var("head_pos", (0, 0))
    score = Var("score", (0,))
    dead = Var("dead", (False,))

    snake = Snek(3, 5, head_pos, length, dead)

    screen_size = Var("screen_size", (0, 0))
    screen_size.register(E_RESIZE, screen_size.change)

    foods = Foods(screen_size, head_pos, length, score)


    seqw = Proxy()

    start_screen = Group([
        Onhw(lambda h, w: SimpleText(h//2, w//2 - 8, "Use arrow keys to turn the snake", Style.default)),
        Onhw(lambda h, w: SimpleText(h//2+2, w//2 - 8, "Press <Q> to give up", Style.default)),
        Onhw(lambda h, w: SimpleText(h//2+4, w//2 - 8, "Press <Enter> to start!", Style.default)),

        OnKey({"^J", "KEY_ENTER"}, Seqw.E_NEXT, seqw),
        OnKey({"q", "Q"}, E_QUIT, QuitHandler()),
        screen_size,
    ])

    main_game = Group([

        Reactive(score, lambda s: SimpleText(3, 3, f"Score: {s}", Style.default)),

        snake,
        TickReducer(1, Snek.E_ADVANCE, snake),
        OnKey({"KEY_LEFT"},  Snek.E_LEFT, snake),
        OnKey({"KEY_RIGHT"},  Snek.E_RIGHT, snake),
        OnKey({"KEY_UP"},  Snek.E_UP, snake),
        OnKey({"KEY_DOWN"}, Snek.E_DOWN, snake),
        OnKey({"KEY_SPACE", " "}, Snek.E_REVERSE, snake),
        WhenTrue(dead, Seqw.E_NEXT, seqw),

        Boundary(head_pos, screen_size, dead),

        foods,
        head_pos,
        length,
        score,
        dead,
        screen_size,

        OnKey({"q", "Q"}, Seqw.E_NEXT, seqw),
    ])

    lost = Group([
        Reactive(score, lambda s: Onhw(lambda h, w: SimpleText(h//2, w//2 - 8, f"Game over! Score: {s}", Style.default))),
        Onhw(lambda h, w: SimpleText(h//2 + 2, w//2 - 8, "Press <Q> to exit", Style.default)),
        OnKey({"q", "Q"}, E_QUIT, QuitHandler()),
        score,
        screen_size,
    ])

    seqw.update(Seqw([start_screen, main_game, lost]))
    return seqw



run(game(), fps=30)
