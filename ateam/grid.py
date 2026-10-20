"""Tab 🔲 Lưới (TUI + web): mỗi ô là CLI thật của một agent chạy trong pty, gõ trực tiếp được.

Bố cục là danh sách cột, mỗi cột xếp các ô từ trên xuống — đủ cho các bố cục có sẵn (`PRESETS`) và cho việc thả một
ô vào trên/dưới/trái/phải/giữa (đổi chỗ) của ô khác. Lưu ở `.ateam/grid.json` theo dự án; mở lại ateam thì lưới
hiện lại nhưng CLI chưa chạy (mỗi ô có nút mở lại) để không bật hàng loạt CLI một lúc.

`GridHub` giữ `PtySession` của từng ô, bộ đệm output gần nhất (tab web mở sau vẫn thấy lại màn hình) và báo cho
người nghe (TUI vẽ bằng `vterm.Screen`, web đẩy byte cho xterm.js)."""

from __future__ import annotations

import json
import math
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .i18n import tr
from .pty_session import PtySession

GRID_FILE = "grid.json"
BUFFER_MAX = 256 * 1024  # byte output gần nhất của mỗi ô, phát lại cho tab web mới mở
MIN_SIZE = 0.15          # cột / ô không nhỏ hơn tỉ lệ này so với ô bên cạnh khi kéo đổi kích thước
WHERE = ("center", "left", "right", "top", "bottom")
DIRS = ("left", "right", "up", "down")


def preset_names() -> dict[str, str]:
    return {
        "stack": tr("Một cột"),
        "cols2": tr("Hai cột"),
        "auto": tr("Lưới đều"),
        "lead": tr("Lead + đội"),
        "row": tr("Một hàng"),
    }


@dataclass
class Cell:
    agent: str
    model: str = ""
    effort: str = ""
    resume: bool = True      # mở CLI tiếp tục phiên gần nhất của agent (như ⌨ ở tab Đội), False = phiên mới
    bcast: bool = True       # nhận phím khi bật "gửi tới tất cả"
    h: float = 1.0           # chiều cao tương đối trong cột
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    @classmethod
    def from_dict(cls, d: dict) -> "Cell":
        c = cls(agent=str(d.get("agent") or ""))
        for k in ("model", "effort"):
            c.__dict__[k] = str(d.get(k) or "")
        c.resume = bool(d.get("resume", True))
        c.bcast = bool(d.get("bcast", True))
        c.h = _pos(d.get("h"))
        if d.get("id"):
            c.id = str(d["id"])[:32]
        return c


@dataclass
class Column:
    cells: list = field(default_factory=list)
    w: float = 1.0           # độ rộng tương đối


def _pos(v, default: float = 1.0) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) and f > 0 else default


class Layout:
    def __init__(self, cols: list | None = None, preset: str = "lead"):
        self.cols: list[Column] = cols or []
        self.preset = preset  # "" = người dùng đã tự sắp xếp: ô mới vào cột ít ô nhất

    # ---- tra cứu
    def cells(self) -> list[Cell]:
        return [c for col in self.cols for c in col.cells]

    def find(self, cid: str) -> tuple[int, int] | None:
        for i, col in enumerate(self.cols):
            for j, c in enumerate(col.cells):
                if c.id == cid:
                    return i, j
        return None

    def cell(self, cid: str) -> Cell | None:
        pos = self.find(cid)
        return self.cols[pos[0]].cells[pos[1]] if pos else None

    def neighbor(self, cid: str, direction: str) -> str | None:
        """Ô bên cạnh theo hướng (phím mũi tên): trái/phải chọn ô cột bên có vị trí dọc gần nhất."""
        pos = self.find(cid)
        if not pos:
            return None
        i, j = pos
        if direction in ("up", "down"):
            k = j + (-1 if direction == "up" else 1)
            cells = self.cols[i].cells
            return cells[k].id if 0 <= k < len(cells) else None
        k = i + (-1 if direction == "left" else 1)
        if not 0 <= k < len(self.cols):
            return None
        mid = self._mid(i, j)
        other = self.cols[k].cells
        best = min(range(len(other)), key=lambda r: abs(self._mid(k, r) - mid))
        return other[best].id

    def _mid(self, i: int, j: int) -> float:
        cells = self.cols[i].cells
        total = sum(c.h for c in cells) or 1.0
        return (sum(c.h for c in cells[:j]) + cells[j].h / 2) / total

    # ---- sửa
    def add(self, cell: Cell, near: str | None = None, where: str = "") -> None:
        """Thêm ô: theo bố cục có sẵn đang chọn, hoặc chia ô `near` theo `where` (left/right/top/bottom)."""
        if near and where in WHERE[1:] and self.find(near):
            self.cols.append(Column([cell]))  # tạm, _place lấy ra rồi đặt lại
            self._place(cell.id, near, where)
            self.preset = ""
            return
        if self.preset in PRESET_SHAPES:
            self.cols.append(Column([cell]))
            self.apply(self.preset)
            return
        if not self.cols:
            self.cols.append(Column([cell]))
            return
        col = min(self.cols, key=lambda c: len(c.cells))
        cell.h = sum(x.h for x in col.cells) / len(col.cells) if col.cells else 1.0  # cao bằng ô khác trong cột
        col.cells.append(cell)

    def remove(self, cid: str) -> Cell | None:
        pos = self.find(cid)
        if not pos:
            return None
        i, j = pos
        cell = self.cols[i].cells.pop(j)
        if not self.cols[i].cells:
            del self.cols[i]
        if self.preset in PRESET_SHAPES and self.cols:
            self.apply(self.preset)
        return cell

    def move(self, src: str, dst: str, where: str) -> bool:
        """Thả ô `src` lên ô `dst`: center = đổi chỗ hai ô, left/right = cột mới bên cạnh cột của dst,
        top/bottom = chen vào cột của dst."""
        if src == dst or where not in WHERE or not self.find(src) or not self.find(dst):
            return False
        if where == "center":
            (si, sj), (di, dj) = self.find(src), self.find(dst)
            a, b = self.cols[si].cells[sj], self.cols[di].cells[dj]
            a.h, b.h = b.h, a.h
            self.cols[si].cells[sj], self.cols[di].cells[dj] = b, a
        else:
            self._place(src, dst, where)
        self.preset = ""
        return True

    def _place(self, src: str, dst: str, where: str) -> None:
        si, sj = self.find(src)
        cell = self.cols[si].cells.pop(sj)
        if not self.cols[si].cells:
            del self.cols[si]
        di, dj = self.find(dst)
        col = self.cols[di]
        if where in ("top", "bottom"):
            target = col.cells[dj]
            target.h = cell.h = target.h / 2
            col.cells.insert(dj if where == "top" else dj + 1, cell)
        else:
            col.w = w = col.w / 2
            cell.h = 1.0
            self.cols.insert(di if where == "left" else di + 1, Column([cell], w))

    def shift(self, cid: str, direction: str) -> bool:
        """Shift+mũi tên (TUI): đổi chỗ với ô bên cạnh."""
        other = self.neighbor(cid, direction)
        return self.move(cid, other, "center") if other else False

    def apply(self, preset: str) -> None:
        """Xếp lại mọi ô (giữ thứ tự) theo bố cục có sẵn, chia đều kích thước."""
        cells = self.cells()
        shape = PRESET_SHAPES.get(preset)
        if shape is None:
            return
        counts = shape(len(cells))
        self.cols, k = [], 0
        for n in counts:
            col = Column([], 1.0)
            for c in cells[k:k + n]:
                c.h = 1.0
                col.cells.append(c)
            k += n
            if col.cells:
                self.cols.append(col)
        if preset == "lead" and len(self.cols) > 1:
            self.cols[0].w = 1.3
        self.preset = preset

    def resize_col(self, i: int, delta: float) -> None:
        """Đổi độ rộng cột i (delta tính theo tỉ lệ cả lưới); cột bên phải (hoặc trái nếu i là cột cuối) bù lại."""
        if not 0 <= i < len(self.cols) or len(self.cols) < 2:
            return
        k = i + 1 if i + 1 < len(self.cols) else i - 1
        self._trade(self.cols, i, k, delta, "w")
        self.preset = ""

    def resize_cell(self, cid: str, delta: float) -> None:
        pos = self.find(cid)
        if not pos:
            return
        i, j = pos
        cells = self.cols[i].cells
        if len(cells) < 2:
            return
        k = j + 1 if j + 1 < len(cells) else j - 1
        self._trade(cells, j, k, delta, "h")
        self.preset = ""

    @staticmethod
    def _trade(items: list, i: int, k: int, delta: float, attr: str) -> None:
        total = sum(getattr(x, attr) for x in items)
        a, b = getattr(items[i], attr), getattr(items[k], attr)
        pair = a + b
        lo = MIN_SIZE * pair
        na = min(max(a + delta * total, lo), pair - lo)
        setattr(items[i], attr, na)
        setattr(items[k], attr, pair - na)

    def set_sizes(self, widths: list | None = None, heights: dict | None = None) -> None:
        """Kéo khe ở web: đặt thẳng tỉ lệ cột / ô."""
        if widths and len(widths) == len(self.cols):
            for col, w in zip(self.cols, widths):
                col.w = _pos(w)
        for cid, hs in (heights or {}).items():
            pos = self.find(str(cid))
            if pos is not None and isinstance(hs, (int, float)):
                self.cols[pos[0]].cells[pos[1]].h = _pos(hs)
        self.preset = ""

    # ---- lưu
    def to_dict(self) -> dict:
        return {"preset": self.preset, "cols": [{"w": c.w, "cells": [asdict(x) for x in c.cells]} for c in self.cols]}

    @classmethod
    def from_dict(cls, d: dict) -> "Layout":
        cols = []
        for c in d.get("cols") or []:
            if not isinstance(c, dict):
                continue
            cells = [Cell.from_dict(x) for x in c.get("cells") or [] if isinstance(x, dict) and x.get("agent")]
            if cells:
                cols.append(Column(cells, _pos(c.get("w"))))
        preset = str(d.get("preset") or "")
        return cls(cols, preset if preset in PRESET_SHAPES else "")


def _shape_stack(n: int) -> list:
    return [n]


def _shape_cols2(n: int) -> list:
    return [math.ceil(n / 2), n // 2]


def _shape_auto(n: int) -> list:
    k = max(1, math.ceil(math.sqrt(n)))
    base, extra = divmod(n, k)
    return [base + (1 if i < extra else 0) for i in range(k)]


def _shape_lead(n: int) -> list:
    if n <= 1:
        return [n]
    rest = n - 1
    if rest <= 2:
        return [1, rest]
    return [1, math.ceil(rest / 2), rest // 2]


def _shape_row(n: int) -> list:
    return [1] * n


PRESET_SHAPES: dict[str, Callable[[int], list]] = {
    "stack": _shape_stack, "cols2": _shape_cols2, "auto": _shape_auto, "lead": _shape_lead, "row": _shape_row,
}


def grid_path(root: Path) -> Path:
    return Path(root) / ".ateam" / GRID_FILE


def load_layout(root: Path) -> Layout:
    try:
        d = json.loads(grid_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Layout()
    return Layout.from_dict(d) if isinstance(d, dict) else Layout()


def save_layout(root: Path, layout: Layout) -> None:
    p = grid_path(root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(layout.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, p)
    except OSError:
        pass


class Term:
    """CLI của một ô: phiên pty + output gần nhất."""

    def __init__(self, cell_id: str, argv: list):
        self.cell_id, self.argv = cell_id, argv
        self.session: PtySession | None = None
        self.buf = bytearray()
        self.rc: int | None = None

    @property
    def alive(self) -> bool:
        return self.session is not None and self.session.alive

    def keep(self, data: bytes) -> None:
        self.buf += data
        if len(self.buf) > BUFFER_MAX:
            del self.buf[:len(self.buf) - BUFFER_MAX]


class GridHub:
    """Bố cục + CLI của các ô cho một dự án. Người nghe nhận (cell_id, kind, payload):
    kind "data" (bytes), "exit" (mã thoát), "layout" (None — bố cục / trạng thái đổi)."""

    def __init__(self, root: Path, cfg_getter: Callable, session_for: Callable[[str], str | None]):
        self.root = Path(root)
        self.cfg_getter = cfg_getter        # trả Config hiện tại (đổi sau /setup)
        self.session_for = session_for      # agent -> id phiên CLI gần nhất (Orchestrator.terminal_session)
        self.layout = load_layout(self.root)
        self.terms: dict[str, Term] = {}
        self.listeners: list[Callable] = []
        self.bcast = False                  # "gửi tới tất cả": phím gõ ở một ô đi tới mọi ô có cell.bcast

    # ---- người nghe
    def listen(self, fn: Callable) -> None:
        self.listeners.append(fn)

    def unlisten(self, fn: Callable) -> None:
        if fn in self.listeners:
            self.listeners.remove(fn)

    def _emit(self, cid: str, kind: str, payload=None) -> None:
        for fn in list(self.listeners):
            try:
                fn(cid, kind, payload)
            except Exception:
                pass

    def changed(self, save: bool = True) -> None:
        if save:
            save_layout(self.root, self.layout)
        self._emit("", "layout")

    # ---- trạng thái
    def status(self, cid: str) -> str:
        """run = CLI đang chạy; exit = đã thoát; off = chưa mở (vừa mở lại ateam)."""
        t = self.terms.get(cid)
        if t and t.alive:
            return "run"
        return "exit" if t else "off"

    def argv_for(self, cell: Cell) -> list | None:
        a = self.cfg_getter().active_agents().get(cell.agent)
        if not a:
            return None
        session = self.session_for(cell.agent) if cell.resume else None
        return a.interactive_argv(session, model=cell.model or None, effort=cell.effort or None)

    def state(self) -> dict:
        """Ảnh chụp cho web: bố cục + trạng thái từng ô."""
        cfg = self.cfg_getter()
        cols = []
        for col in self.layout.cols:
            cells = []
            for c in col.cells:
                a = cfg.agents.get(c.agent)
                t = self.terms.get(c.id)
                cells.append(dict(asdict(c), status=self.status(c.id), rc=t.rc if t else None,
                                  label=a.label(c.model or None, c.effort or None) if a else "",
                                  lead=c.agent == cfg.lead, cmd=" ".join(t.argv) if t else ""))
            cols.append({"w": col.w, "cells": cells})
        return {"preset": self.layout.preset, "cols": cols, "bcast": self.bcast}

    # ---- thao tác
    async def add(self, agent: str, *, model: str = "", effort: str = "", resume: bool = True,
                  near: str | None = None, where: str = "", rows: int = 24, cols: int = 80) -> tuple[str | None, str]:
        """Thêm ô và mở CLI. Trả (id ô, lỗi)."""
        cfg = self.cfg_getter()
        if agent not in cfg.active_agents():
            return None, tr("Không có agent '{agent}'", agent=agent)
        cell = Cell(agent, model, effort, resume)
        if not self.argv_for(cell):
            return None, tr("Không biết cách mở {agent} ở chế độ tương tác (agent tuỳ chỉnh) — tự mở trong terminal khác",
                            agent=agent)
        self.layout.add(cell, near, where)
        err = await self.start(cell.id, rows, cols)
        self.changed()
        return cell.id, err

    async def start(self, cid: str, rows: int = 24, cols: int = 80) -> str:
        """Mở (lại) CLI của ô. Trả lỗi hoặc ""."""
        cell = self.layout.cell(cid)
        if not cell:
            return tr("Không có ô này")
        old = self.terms.get(cid)
        if old and old.alive:
            return ""
        argv = self.argv_for(cell)
        if not argv:
            return tr("Không biết cách mở {agent} ở chế độ tương tác (agent tuỳ chỉnh) — tự mở trong terminal khác",
                      agent=cell.agent)
        t = Term(cid, argv)
        if old:
            t.buf = old.buf  # mở lại: giữ output cũ phía trên

        def on_data(b: bytes) -> None:
            t.keep(b)
            self._emit(cid, "data", b)

        def on_exit(rc: int) -> None:
            t.rc = rc
            self._emit(cid, "exit", rc)
            self._emit(cid, "layout")

        t.session = PtySession(argv, str(self.root), dict(os.environ), on_data=on_data, on_exit=on_exit,
                               rows=max(2, int(rows)), cols=max(10, int(cols)))
        self.terms[cid] = t
        try:
            await t.session.start()
        except OSError as e:
            t.session = None
            t.rc = -1
            msg = tr("Không chạy được {cmd}: {e}", cmd=" ".join(argv), e=e)
            t.keep(("\r\n" + msg + "\r\n").encode())
            self._emit(cid, "layout")
            return msg
        self._emit(cid, "layout")
        return ""

    def write(self, cid: str, data: bytes) -> None:
        """Phím gõ ở ô `cid`; đang "gửi tới tất cả" (và ô này nằm trong nhóm) thì gửi cho cả nhóm."""
        cell = self.layout.cell(cid)
        targets = [c.id for c in self.layout.cells() if c.bcast] if self.bcast and cell and cell.bcast else [cid]
        for x in targets:
            t = self.terms.get(x)
            if t and t.alive:
                t.session.write(data)

    def resize(self, cid: str, rows: int, cols: int) -> None:
        t = self.terms.get(cid)
        if t and t.session and (t.session.rows, t.session.cols) != (rows, cols):
            t.session.resize(max(2, int(rows)), max(10, int(cols)))

    def stop(self, cid: str) -> None:
        t = self.terms.get(cid)
        if t and t.session:
            t.session.close()

    def close(self, cid: str) -> None:
        """Đóng ô: dừng CLI (SIGHUP như đóng cửa sổ terminal) và bỏ khỏi lưới."""
        self.stop(cid)
        self.terms.pop(cid, None)
        if self.layout.remove(cid):
            self.changed()

    def update_cell(self, cid: str, **kw) -> None:
        cell = self.layout.cell(cid)
        if not cell:
            return
        for k in ("model", "effort"):
            if k in kw:
                setattr(cell, k, str(kw[k] or ""))
        for k in ("resume", "bcast"):
            if k in kw:
                setattr(cell, k, bool(kw[k]))
        self.changed()

    def shutdown(self) -> None:
        for t in self.terms.values():
            if t.session:
                t.session.kill_now()
