from __future__ import annotations
from enum import Enum
from math import sin, cos
from typing import Iterable, Iterator, NamedTuple, Sequence
from typing_extensions import assert_never
from lib.base import E_TICK, Event, EventKey, Group, Rect, Style, Var, Widget, cell
from lib.entrypoint import run
from lib.widgets import Bus, Fill, GiveUp, KeyMap, VSplitAdvanced


class Point(NamedTuple):
    y: int
    x: int


def fit(*, screen: Point, view_center: Point) -> tuple[Point, Point]:
    py1 = view_center.y - screen.y//2
    px1 = view_center.x - screen.x//2
    py2 = py1 + screen.y
    px2 = px1 + screen.x

    return Point(py1, px1), Point(py2, px2)


class Tile(Enum):
    ground = "ground"
    grass = "grass"
    water = "water"


class Fstyle(Enum):
    grass = ((340, 800, 500), (0, 320, 160))
    ground = ((860, 460, 360), (160, 120, 0))
    water = ((0, 120, 1000), (0, 0, 380))


def render_tile(tick: int, y: int, x: int, tile: Tile) -> Widget:
    match tile:
        case Tile.ground:
            return Rect(y, x, 2, 2, Fstyle.ground, " ")
        case Tile.grass:
            return Group([
                cell(y, x, Fstyle.grass, "^"), cell(y, x + 1, Fstyle.grass, " "),
                cell(y+1, x, Fstyle.grass, " "), cell(y+1, x + 1, Fstyle.grass, "^"),
            ])
        case Tile.water:
            a = sin(tick/20) > cos(y / 6) * sin(x / 8)

            ca = " ~"[a]
            cb = "~ "[a]

            return Group([
                cell(y, x, Fstyle.water, ca), cell(y, x+1, Fstyle.water, cb),
                cell(y+1, x, Fstyle.water, cb), cell(y+1, x+1, Fstyle.water, ca),
            ])

        case invalid:
            assert_never(invalid)


class Map:
    def __init__(self, tiles: Sequence[Sequence[Tile]]) -> None:
        self._height = len(tiles)
        assert len(set(map(len, tiles))) == 1
        self._width = len(tiles[0])
        self._tiles = tiles

    def coords(self) -> Iterator[Point]:
        for x in range(self._width):
            for y in range(self._height):
                yield Point(y, x)

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    def rect(self, top_left: Point, bottom_right: Point) -> Iterator[Point]:
        for x in range(max(top_left.x, 0), min(bottom_right.x, self._width)):
            for y in range(max(top_left.y, 0), min(bottom_right.y, self._height)):
                yield Point(y, x)

    def at(self, y: int, x: int) -> Tile:
        try:
            return self._tiles[y][x]
        except IndexError:
            raise IndexError(f"{x=} {y=}")


class Direction(Enum):
    up = "up"
    down = "down"
    right = "right"
    left = "left"


E_CONTROL = EventKey[Direction]("control")


class Offset(Widget):
    def __init__(self, y: int, x: int, wrapped: Widget) -> None:
        super().__init__()
        self._y = y
        self._x = x
        self._wrapped = wrapped

    def bubble(self, event: Event, /) -> None:
        self._wrapped.dispatch(event.key, event.payload)

    def cells(self, h: int, w: int, /) -> Iterable[Rect]:
        for rect in self._wrapped.cells(h, w):
            yield Rect(rect.y + self._y, rect.x + self._x, rect.height, rect.width, rect.style, rect.char)


class Entities:
    def __init__(self, entities: list[tuple[Widget, int, int]]) -> None:
        self.entities = entities

    def at(self, y: int, x: int) -> Widget | None:
        return next((e for e, ey, ex in self.entities if (y, x) == (ey, ex)), None)


class TileView(Widget):
    def __init__(self, view_pos: Var[int, int], world: Map, e: Entities) -> None:
        super().__init__()
        self._world = world
        self._e = e
        self._view_pos = view_pos
        self._ticks = 0
        self.register(E_TICK, self._on_tick)

    def _on_tick(self) -> None:
        self._ticks += 1

    def cells(self, h: int, w: int, /) -> Iterable[Rect]:
        vy, vx = self._view_pos.value()
        tl, br = fit(screen=Point(h//2, w//2), view_center=Point(vy, vx))
        for y, x in self._world.rect(tl, br):
            e = self._e.at(y, x)
            if e is not None:
                r = Offset((y - tl.y)*2, (x - tl.x)*2, e)
            else:
                tile = self._world.at(y, x)
                r = render_tile(self._ticks, (y - tl.y)*2, (x - tl.x)*2, tile)
            yield from r.cells(h, w)


class Character(Widget):
    def cells(self, h: int, w: int, /) -> Iterable[Rect]:
        y, x = h//2, w//2
        y -= y%2
        x -= x%2
        yield from Group([
            cell(y, x, Style.red, "$"), cell(y, x+1, Style.red, "$"),
            cell(y+1, x, Style.red, "|"), cell(y+1, x+1, Style.red, "|"),
        ]).cells(h, w)


def vsplit(h: int, w: int) -> Sequence[int]:
    h1 = 4
    h3 = 4
    h2 = h - (h1 + h3)
    if h2 % 2 == 1:
        h3 += 1
        h2 -= 1
    return [h1, h2, h3]


g = """
111111111122222222222222222222222222222233333333333333333
111111111111111133333222213333333332222222222222222211111
111111111111111133333333333333322222222223333333331111111
111111111111111133333333333333222221111111111111111111111
222222222333333333222222222222222222222222111111111111111
222222222111111111111111111333333333333311333333333333333
222222222222221111111111111333333333333333333333333333333
222222222222222222222222222333333333333311113333333333333
222222222222222221111111111333333333333311222233333333333
222222222222221111111111111333333333333311112233333333333
111111111122222222222222222333333333333333333333333333333
111111111111111133333222213333333332222222222222222211111
111111111111111133333333333333322222222223333333331111111
111111111111111133333333333333222221111111111111111111111
333333333333333333222222222222222222222222111111111111111
222222222111111111111111111111111111111111333333333333333
111111122222221111111111111111111333333333333333333333333
222222222222222222222222222111111111111111113333333333333
222222222222222221111111111111111111111111222233333333333
222222222222221111111111111111111111111111112233333333333
""".strip()

tiles = [
    [list(Tile)[int(x)-1] for x in row]
    for row in g.split()
]


def game() -> Widget:
    bus = Bus()
    pos = bus.var("pos", (5, 10))

    def on_control(ctl: Direction) -> None:
        y, x = pos.value()
        dy, dx = {
            Direction.up: (-1, 0),
            Direction.down: (1, 0),
            Direction.right: (0, 1),
            Direction.left: (0, -1),
        }[ctl]
        nx, ny = x+dx, y+dy
        if nx < 0 or ny < 0 or nx >= mep.width or ny >= mep.height:
            return
        if mep.at(ny, nx) == Tile.water:
            return
        pos.change(ny, nx)

    pos.register(E_CONTROL, on_control)
    mep = Map(tiles)
    widgets = [
        TileView(pos, mep, Entities([
            (Rect(0, 0, 2, 2, Style.white, "?"), 3, 3),
        ])),
        bus,
        KeyMap({
            "w": Event(E_CONTROL, (Direction.up,)),
            "s": Event(E_CONTROL, (Direction.down,)),
            "d": Event(E_CONTROL, (Direction.right,)),
            "a": Event(E_CONTROL, (Direction.left,)),
        }, bus),
        GiveUp(),
        Character(),
    ]
    return Group(widgets)


main = VSplitAdvanced(vsplit, [
    Fill(Style.dim),
    game(),
    Fill(Style.dim),
])


extra_styles = [(s, *s.value) for s in Fstyle]


run(main, fps=30, extra_styles=extra_styles)
