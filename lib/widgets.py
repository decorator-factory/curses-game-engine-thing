from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Callable, Collection, Iterable, Iterator, Mapping, Sequence, TypeVar
from typing_extensions import TypeVarTuple, Unpack, assert_never
from .base import E_KEY, E_RESIZE, E_TICK, cell, Event, EventKey, Rect, Style, Var, Widget, Quit


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

    def cells(self, h: int, w: int, /) -> Iterable[Rect]:
        if not self._steps:
            return
        active = self._steps[0]
        yield from active.cells(h, w)


@dataclass(frozen=True)
class Row:
    frac: Fraction = Fraction(0)
    min: int | None = None
    max: int | None = None


_ToRow = int | Fraction | tuple[int, int] | tuple[Fraction, int] | tuple[Fraction, int, int]


def _to_row(raw: _ToRow) -> Row:
    # cursed
    match raw:
        case int():
            return Row(min=raw, max=raw)
        case Fraction():
            return Row(raw)
        case (a, b):
            if isinstance(a, int):
                return Row(Fraction(1.0), min=a, max=b)
            else:
                return Row(frac=a, min=b)
        case (frac, minh, maxh):
            return Row(frac, minh, maxh)
        case invalid:
            assert_never(invalid)



class VSplit(Widget):
    def __init__(self, rows: Sequence[tuple[_ToRow, Widget]]) -> None:
        super().__init__()
        self._sizes = [_to_row(size) for size, _ in rows]
        self._widgets = [widget for _, widget in rows]

    def bubble(self, event: Event, /) -> None:
        for widget in self._widgets:
            widget.dispatch(event.key, event.payload)

    def cells(self, h: int, w: int, /) -> Iterable[Rect]:
        for (oy, dh), widget in zip(_split(h, self._sizes), self._widgets):
            for rect in widget.cells(dh, w):
                yield Rect(rect.y + oy, rect.x, rect.height, rect.width, rect.style, rect.char)


def _split(h: int, rows: Sequence[Row]) -> Iterator[tuple[int, int]]:
    left = h
    for row in rows:
        dh = max(1, round(row.frac * h))
        if row.min is not None:
            dh = max(row.min, dh)
        if row.max is not None:
            dh = min(row.max, dh)
        dh = min(left, dh)
        yield (h - left, dh)
        left -= dh
    if left > 0:
        yield (h - left, left)


class VSplitAdvanced(Widget):  # naming = 100
    def __init__(self, mk_heights: Callable[[int, int], Sequence[int]], widgets: Sequence[Widget]) -> None:
        # mk_heights: (h, w) -> (height0, height1, height2, ...)
        super().__init__()
        self._widgets = widgets
        self._mk_heights = mk_heights

    def bubble(self, event: Event, /) -> None:
        for widget in self._widgets:
            widget.dispatch(event.key, event.payload)

    def cells(self, h: int, w: int, /) -> Iterable[Rect]:
        oy = 0
        for dh, widget in zip(self._mk_heights(h, w), self._widgets):
            for rect in widget.cells(dh, w):
                yield Rect(rect.y + oy, rect.x, rect.height, rect.width, rect.style, rect.char)
            oy += dh


class Proxy(Widget):
    def __init__(self) -> None:
        super().__init__()
        self._wrapped = None

    def update(self, widget: Widget) -> None:
        self._wrapped = widget

    def bubble(self, event: Event, /) -> None:
        if self._wrapped:
            self._wrapped.dispatch(event.key, event.payload)

    def cells(self, h: int, w: int, /) -> Iterable[Rect]:
        if self._wrapped:
            yield from self._wrapped.cells(h, w)


class Fill(Widget):
    def __init__(self, style: Style) -> None:
        super().__init__()
        self._style = style

    def cells(self, h: int, w: int, /) -> Iterable[Rect]:
        yield Rect(0, 0, h, w, self._style)


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


class Upscale(Widget):
    def __init__(self, n: int, wrapped: Widget) -> None:
        super().__init__()
        assert n > 0, f"Expected a positive scale factor, got {n!r}"
        self._n = n
        self._wrapped = wrapped

    def bubble(self, event: Event, /) -> None:
        self._wrapped.dispatch(event.key, event.payload)

    def cells(self, h: int, w: int, /) -> Iterable[Rect]:
        n = self._n
        for rect in self._wrapped.cells(h // n, w // n):
            yield Rect(rect.y*n, rect.x*n, n, n, rect.style, rect.char)
