from __future__ import annotations
from fractions import Fraction
from typing import Any, Collection, Generic, Iterable, Iterator, Mapping, Sequence, TypeVar
from typing_extensions import TypeVarTuple, Unpack
from .base import E_KEY, E_RESIZE, E_TICK, Cell, Event, EventKey, Rect, Style, Var, Widget, Quit


_P = TypeVarTuple("_P")
_T = TypeVar("_T")


class GiveUp(Widget):
    def __init__(self, keys: Collection[str] = ("q", "Q")) -> None:
        super().__init__()
        self._keys = keys
        self.register(E_KEY, self.on_quit)

    def on_quit(self, key: str) -> None:
        if key in self._keys:
            raise Quit


class OnKey(Widget):
    def __init__(self, keys: Iterable[str], event: EventKey[()], target: Widget) -> None:
        super().__init__()
        self._keys = set(keys)
        self._wrapped = target
        self._event = event
        self.register(E_KEY, self.on_key)

    def on_key(self, key: str) -> None:
        if key in self._keys:
            self._wrapped.dispatch(self._event, ())


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


class WidgetSequence(Widget):
    E_NEXT: EventKey[()] = EventKey("sequence.next")
    E_DONE: EventKey[()] = EventKey("sequence.done")

    def __init__(self, steps: Sequence[Widget], on_done_notify: Widget = Widget()):
        super().__init__()
        self._steps = list(steps)
        self._on_done_notify = on_done_notify
        self.register(self.E_NEXT, self.on_next)

    def bubble(self, event: Event, /) -> None:
        if not self._steps:
            return
        active = self._steps[0]
        active.dispatch(event.key, event.payload)

    def on_next(self) -> None:
        if not self._steps:
            return
        self._steps.pop(0)
        if not self._steps:
            self._on_done_notify.dispatch(self.E_DONE, ())

    def cells(self, h: int, w: int, /) -> Iterable[Cell]:
        if not self._steps:
            return
        active = self._steps[0]
        yield from active.cells(h, w)


class VSplit(Widget):
    def __init__(self, rows: Sequence[tuple[Fraction, Widget]]) -> None:
        super().__init__()
        self._sizes = [size for size, _ in rows]
        assert sum(self._sizes) <= 1
        self._widgets = [widget for _, widget in rows]

    def bubble(self, event: Event, /) -> None:
        for widget in self._widgets:
            widget.dispatch(event.key, event.payload)

    def cells(self, h: int, w: int, /) -> Iterable[Cell]:
        for (oy, dh), widget in zip(_split(h, self._sizes), self._widgets):
            for cell in widget.cells(dh, w):
                yield Cell(cell.y + oy, cell.x, cell.char)


def _split(h: int, sizes: Sequence[Fraction]) -> Iterator[tuple[int, int]]:
    left = h
    for f in sizes:
        dh = max(1, round(f * h))
        yield (h - left, dh)
        left -= dh
    if left > 0:
        yield (h - left, left)


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


class Fill(Widget):
    def __init__(self, style: Style) -> None:
        super().__init__()
        self._style = style

    def cells(self, h: int, w: int, /) -> Iterable[Cell]:
        yield from Rect(0, 0, h, w, self._style).cells(h, w)


class WhenTrue(Widget):
    def __init__(self, var: Var[bool], event: EventKey[()], widget: Widget) -> None:
        super().__init__()
        var.watch(self._on_change)
        self._e = event
        self._widget = widget

    def _on_change(self, value: bool) -> None:
        if value:
            self._widget.dispatch(self._e, ())


class Bus(Widget):
    def __init__(self) -> None:
        super().__init__()
        self._widgets: list[Widget] = []

    def listen(self, child: Widget, /) -> None:
        self._widgets.append(child)

    def bubble(self, event: Event, /) -> None:
        for widget in self._widgets:
            widget.dispatch(event.key, event.payload)

    def var(self, name: str, default: tuple[Unpack[_P]]) -> Var[Unpack[_P]]:
        v = Var(name, default)
        self.listen(v)
        return v


class KeyMap(Widget):
    def __init__(self, keymap: Mapping[str, Event[Unpack[tuple[Any, ...]]]], target: Widget) -> None:
        super().__init__()
        self._keymap = {k.lower(): v for k, v in keymap.items()}
        self._target = target
        self.register(E_KEY, self._on_key)

    def _on_key(self, key: str) -> None:
        if control := self._keymap.get(key.lower()):
            self._target.dispatch(control.key, control.payload)  # type: ignore


def screen_size_var() -> Var[int, int]:
    screen_size = Var("screen_size", (24, 80))
    screen_size.register(E_RESIZE, screen_size.change)
    return screen_size
