from __future__ import annotations

import uuid
import weakref
from dataclasses import dataclass
from enum import Enum
from typing import (
    Any,
    Callable,
    Generic,
    Iterable,
    Iterator,
    Sequence,
    overload
)

from typing_extensions import (
    Never,
    TypeVar
)


E = TypeVar("E", default=None)


class Style(Enum):
    default = 100
    white = 200
    red = 201
    blue = 202
    green = 203
    cyan = 204
    dim = 205


class EventKey(Generic[E]):
    def __init__(self, name: str) -> None:
        self._name = name
        self._uid = f"{name}:{uuid.uuid4()}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def unique_id(self) -> str:
        return self._uid


E_TICK = EventKey("base.tick")
E_RESIZE = EventKey[tuple[int, int]]("base.resize")
E_KEY = EventKey[str]("base.key")
E_NEVER = EventKey[Never]("base.never")

_E_CHANGE = {}

def e_change(_t: type[EventKey[E]], prefix="base._change", /) -> EventKey[E]:
    return _E_CHANGE.setdefault(prefix, _t)


@dataclass(frozen=True)
class Event(Generic[E]):
    key: EventKey[E]
    payload: E


class Quit(BaseException):
    pass


class Widget:
    def __init__(self) -> None:
        self._handlers: dict[EventKey[Any], Callable[[Any], None]] = {}

    def register(self, key: EventKey[E], handler: Callable[[E], None]) -> None:
        self._handlers[key] = handler

    @overload
    def dispatch(self, key: EventKey[None], payload: None = ...) -> None:
        ...

    @overload
    def dispatch(self, key: EventKey[E], payload: E) -> None:
        ...

    def dispatch(self, key: EventKey[E], payload: Any = None) -> None:
        if h := self._handlers.get(key):
            h(payload)
        else:
            self.bubble(Event(key, payload))

    def bubble(self, event: Event[Any], /) -> None:
        pass

    def cells(self, h: int, w: int, /) -> Iterable[Rect]:
        return ()


@dataclass
class SimpleText(Widget):
    y: int
    x: int
    text: str
    style: object

    def __post_init__(self) -> None:
        super().__init__()

    def cells(self, h: int, w: int) -> Iterator[Rect]:
        if self.y >= h:
            return

        for x, ch in enumerate(self.text, start=self.x):
            if x >= w:
                return
            yield Rect(self.y, x, 1, 1, self.style, ch)


def cell(y: int, x: int, style: object, char: str) -> Rect:
    return Rect(y, x, 1, 1 ,style, char)


class Reactive(Widget, Generic[E]):
    def __init__(self, var: Var[E], fn: Callable[[E], Widget]) -> None:
        super().__init__()
        self._fn = fn
        self._var = var
        self._widget = fn(var.value())
        key = e_change(EventKey[E])
        self.register(key, self._on_change)
        var.subscribe(key, self)

    def _on_change(self, new_state: E, /) -> None:
        self._widget = self._fn(new_state)

    def bubble(self, event: Event[Any], /) -> None:
        self._widget.dispatch(event.key, event.payload)

    def cells(self, h: int, w: int, /) -> Iterable[Rect]:
        return self._widget.cells(h, w)


class Group(Widget):
    def __init__(self, widgets: Sequence[Widget]) -> None:
        self._widgets: list[Widget] = list(widgets)
        super().__init__()

    def bubble(self, event: Event[Any], /) -> None:
        for widget in self._widgets:
            widget.dispatch(event.key, event.payload)

    def cells(self, h: int, w: int, /) -> Iterable[Rect]:
        for widget in self._widgets:
            yield from widget.cells(h, w)


@dataclass
class Rect(Widget):
    y: int
    x: int
    height: int
    width: int
    style: object
    char: str = " "

    def __post_init__(self) -> None:
        super().__init__()
        assert len(self.char) == 1

    def cells(self, h: int, w: int) -> Iterator[Rect]:
        y = self.y
        x = self.x
        rh = self.height
        rw = self.width
        if x <= 0:
            rw += x
            x = 0
        if y <= 0:
            rh += y
            y = 0
        if x + rw >= w:
            rw = w - x
        if y + rh >= h:
            rh = h - y

        if rw > 0 and rh > 0:
            yield Rect(y, x, rh, rw, self.style, self.char)


T = TypeVar("T")
U = TypeVar("U")


class Var(Widget, Generic[T]):
    def __init__(self, name: str, initial: T) -> None:
        super().__init__()
        self._name = name
        self._last_value = initial
        self._new_value = initial
        self._changed = False
        self._subscribers: list[Callable[[T], None]] = []
        self._subvars: list[weakref.ref[Var]] = []

        self.register(E_TICK, lambda _: self.on_tick())

    def derive(self, fn: Callable[[T], U]) -> Var[U]:
        dv = Var(f"{self._name} >> _", fn(self._last_value))

        def on_change(new_value: T) -> None:
            dv.change(fn(new_value))
            dv.on_tick()

        k = e_change(EventKey[T])
        dv.register(k, on_change)
        self.subscribe(k, dv)
        return dv

    def concat(self, other: Var[U], /) -> Var[tuple[T, U]]:
        tu = (self._last_value, other._last_value)
        cv= Var(f"{self._name} * {other._name}", tu)
        key_t = e_change(EventKey[T], "base.change_t")
        key_u = e_change(EventKey[U], "base.change_u")

        def on_t_change(new_value: T) -> None:
            cv.change((new_value, cv._new_value[1]))

        def on_u_change(new_value: U) -> None:
            cv.change((cv._new_value[0], new_value))

        cv.register(key_t, on_t_change)
        cv.register(key_u, on_u_change)
        self.subscribe(key_t, cv)
        other.subscribe(key_u, cv)
        self._subvars.append(weakref.ref(cv))
        other._subvars.append(weakref.ref(cv))
        return cv

    __mul__ = concat

    def subscribe(self, key: EventKey[T], widget: Widget) -> None:
        ref = weakref.ref(widget)

        def propagate_change(payload: T) -> None:
            if w := ref():
                w.dispatch(key, payload)

        self._subscribers.append(propagate_change)
        widget.dispatch(key, self._last_value)

    def watch(self, cb: Callable[[T], None]) -> None:
        self._subscribers.append(cb)

    def value(self) -> T:
        return self._last_value

    def change(self, payload: T) -> None:
        self._changed = True
        self._new_value = payload

    def on_tick(self) -> None:
        if not self._changed:
            return

        for vv in self._subvars:
            if v := vv():
                v.on_tick()

        self._last_value = self._new_value
        self._changed = False
        for callback in self._subscribers:
            callback(self._last_value)

    def cells(self, h: int, w: int, /) -> Iterable[Rect]:
        return ()


class Char:
    def __init__(self, val: str, style: object) -> None:
        if len(val) != 1:
            raise ValueError(f"{val=}")
        self.val = val
        self.style = style

    def __repr__(self) -> str:
        return f"Char({self.val!r}, {self.style!r})"
