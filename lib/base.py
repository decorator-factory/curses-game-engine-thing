from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Generic, Iterable, Iterator, Sequence, TypeVar
from typing_extensions import Never, TypeVarTuple, Unpack
import weakref

if TYPE_CHECKING:
    from curses import _CursesWindow as Win
else:
    Win = object


P = TypeVarTuple("P")
Q = TypeVarTuple("Q")


class Style(Enum):
    default = 100
    red = 200
    blue = 202
    green = 204

    cyan = 206



@dataclass(frozen=True)
class Cell:
    y: int
    x: int
    char: Char


class EventKey(Generic[Unpack[P]]):
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name


E_TICK = EventKey[Unpack[tuple[()]]]("base.tick")
E_RESIZE = EventKey[int, int]("base.resize")
E_KEY = EventKey[str]("base.key")
E_NEVER = EventKey[Never]("base.never")

_E_CHANGE = {}

def e_change(_t: type[EventKey[Unpack[P]]], prefix="base._change", /) -> EventKey[Unpack[P]]:
    return _E_CHANGE.setdefault(prefix, _t)  # type: ignore


@dataclass(frozen=True)
class Event(Generic[Unpack[P]]):
    key: EventKey[Unpack[P]]
    payload: tuple[Unpack[P]]


class Quit(BaseException):
    pass


class Widget:
    def __init__(self) -> None:
        self._handlers: dict[EventKey, Callable[..., None]] = {}

    def register(self, key: EventKey[Unpack[P]], handler: Callable[[Unpack[P]], None]) -> None:
        self._handlers[key] = handler

    def dispatch(self, key: EventKey[Unpack[P]], payload: tuple[Unpack[P]]) -> None:
        if h := self._handlers.get(key):
            h(*payload)
        else:
            self.bubble(Event(key, payload))  # type: ignore

    def bubble(self, event: Event, /) -> None:
        pass

    def cells(self, h: int, w: int, /) -> Iterable[Cell]:
        return ()


@dataclass
class SimpleText(Widget):
    y: int
    x: int
    text: str
    style: Style

    def __post_init__(self) -> None:
        super().__init__()

    def cells(self, h: int, w: int) -> Iterator[Cell]:
        if self.y >= h:
            return

        for x, ch in enumerate(self.text, start=self.x):
            if x >= w:
                return
            yield Cell(self.y, x, Char(ch, self.style))


class Reactive(Widget, Generic[Unpack[P]]):
    def __init__(self, var: Var[Unpack[P]], fn: Callable[[Unpack[P]], Widget]) -> None:
        super().__init__()
        self._fn = fn
        self._var = var
        self._widget = fn(*var.value())
        key = e_change(EventKey[Unpack[P]])
        self.register(key, self.on_change)
        var.subscribe(key, self)

    def on_change(self, *new_state: Unpack[P]) -> None:
        self._widget = self._fn(*new_state)

    def bubble(self, event: Event[Any], /) -> None:
        self._widget.dispatch(event.key, event.payload)

    def cells(self, h: int, w: int, /) -> Iterable[Cell]:
        yield from self._widget.cells(h, w)


class Group(Widget):
    def __init__(self, widgets: Sequence[Widget]) -> None:
        self._widgets: list[Widget] = list(widgets)

    def bubble(self, event: Event[Any], /) -> None:
        for widget in self._widgets:
            widget.dispatch(event.key, event.payload)

    def cells(self, h: int, w: int, /) -> Iterable[Cell]:
        for widget in self._widgets:
            yield from widget.cells(h, w)


@dataclass
class Hline(Widget):
    y: int
    text: str
    style: Style

    def __post_init__(self) -> None:
        super().__init__()

    def cells(self, h: int, w: int) -> Iterator[Cell]:
        if self.y >= h:
            return

        if w > len(self.text):
            start_x = (w - len(self.text))//2
        else:
            start_x = 0

        for _, (x, ch) in zip(range(w), enumerate(self.text, start=start_x)):
            if x >= w:
                return
            yield Cell(self.y, x, Char(ch, self.style))


@dataclass
class Rect(Widget):
    y: int
    x: int
    height: int
    width: int
    style: Style

    def __post_init__(self) -> None:
        super().__init__()

    def cells(self, h: int, w: int) -> Iterator[Cell]:
        line = " " * self.width
        for y in range(self.y, self.y + self.height):
            yield from SimpleText(y, self.x, line, self.style).cells(h, w)


T = TypeVar("T")
U = TypeVar("U")


class Var(Widget, Generic[Unpack[P]]):
    def __init__(self, name: str, initial: tuple[Unpack[P]]) -> None:
        super().__init__()
        self._name = name
        self._last_value = initial
        self._new_value = initial
        self._changed = False
        self._subscribers: list[tuple[EventKey[Unpack[tuple[Any, ...]]], weakref.ref[Widget]]] = []
        self._subvars: list[weakref.ref[Var]] = []

        self.register(E_TICK, self.on_tick)

    def derive(self, fn: Callable[[Unpack[P]], tuple[Unpack[Q]]]) -> Var[Unpack[Q]]:
        dv = Var(f"{self._name} >> _", fn(*self._last_value))

        def on_change(*p: Unpack[P]) -> None:
            dv.change(*fn(*p))
            dv.on_tick()

        k = e_change(EventKey[Unpack[P]])
        dv.register(k, on_change)
        self.subscribe(k, dv)
        return dv

    __rshift__ = derive

    def __or__(self: "Var[T]", other: Callable[[T], U]) -> Var[U]:
        return self >> (lambda t: (other(t),))

    def concat(self, other: Var[Unpack[Q]], /) -> Var[Unpack[P], Unpack[Q]]:
        cv = Var(f"{self._name} * {other._name}", (*self._last_value, *other._last_value))
        keyp = e_change(EventKey[Unpack[P]], "base.change_p")
        keyq = e_change(EventKey[Unpack[Q]], "base.change_q")

        def on_p_change(*p: Unpack[P]) -> None:
            pq = list(cv._new_value)
            pq[:len(p)] = p  # type: ignore
            cv.change(*pq)  # type: ignore

        def on_q_change(*q: Unpack[Q]) -> None:
            pq = list(cv._new_value)
            pq[-len(q):] = q  # type: ignore
            cv.change(*pq)  # type: ignore

        cv.register(keyp, on_p_change)
        cv.register(keyq, on_q_change)
        self.subscribe(keyp, cv)
        other.subscribe(keyq, cv)
        self._subvars.append(weakref.ref(cv))
        other._subvars.append(weakref.ref(cv))
        return cv

    __mul__ = concat

    def subscribe(self, key: EventKey[Unpack[P]], widget: Widget) -> None:
        self._subscribers.append((key, weakref.ref(widget)))  # type: ignore
        widget.dispatch(key, self._last_value)

    def value(self) -> tuple[Unpack[P]]:
        return self._last_value

    def change(self, *payload: Unpack[P]) -> None:
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
        for e, ww in self._subscribers:
            if w := ww():
                w.dispatch(e, self._last_value)

    def cells(self, h: int, w: int, /) -> Iterable[Cell]:
        yield from ()


class Char:
    def __init__(self, val: str, style: Style) -> None:
        if len(val) != 1:
            raise ValueError(f"{val=}")
        self.val = val
        self.style = style

    def __repr__(self) -> str:
        return f"Char({self.val!r}, Style.{self.style.name})"
