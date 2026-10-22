"""Tab 🔲 Lưới: bố cục (grid.Layout), bộ giả lập terminal (vterm), GridHub với CLI giả lập, web (grid_*) và TUI."""

from __future__ import annotations

import asyncio
import base64
import importlib
import json
import re

from conftest import write_project_config  # noqa: F401


# ---------------------------------------------------------------- bố cục
def _ids(lay):
    return [[c.agent for c in col.cells] for col in lay.cols]


def test_layout_presets_and_add_remove():
    from ateam.grid import Cell, Layout
    lay = Layout(preset="lead")
    for a in ("lead", "a", "b", "c", "d"):
        lay.add(Cell(a))
    assert _ids(lay) == [["lead"], ["a", "b"], ["c", "d"]]
    assert lay.cols[0].w > lay.cols[1].w  # trưởng nhóm rộng hơn
    lay.apply("cols2")
    assert _ids(lay) == [["lead", "a", "b"], ["c", "d"]] and lay.preset == "cols2"
    lay.apply("auto")
    assert _ids(lay) == [["lead", "a"], ["b", "c"], ["d"]]
    lay.apply("row")
    assert _ids(lay) == [["lead"], ["a"], ["b"], ["c"], ["d"]]
    lay.apply("stack")
    assert _ids(lay) == [["lead", "a", "b", "c", "d"]]
    lay.apply("lead")
    b = lay.cells()[2]
    lay.remove(b.id)  # bố cục có sẵn: xếp lại sau khi đóng
    assert _ids(lay) == [["lead"], ["a", "c"], ["d"]]
    assert lay.remove("khong-co") is None


def test_layout_move_resize_neighbor_roundtrip(tmp_path):
    from ateam.grid import Cell, Layout, load_layout, save_layout
    lay = Layout(preset="lead")
    cells = [Cell(a) for a in ("x", "y", "z")]
    for c in cells:
        lay.add(c)
    x, y, z = (c.id for c in cells)
    assert _ids(lay) == [["x"], ["y", "z"]]
    assert lay.move(z, x, "center") and _ids(lay) == [["z"], ["y", "x"]] and lay.preset == ""
    assert lay.move(x, z, "right") and _ids(lay) == [["z"], ["x"], ["y"]]
    assert lay.move(y, x, "top") and _ids(lay) == [["z"], ["y", "x"]]
    assert lay.move(z, y, "bottom") and _ids(lay) == [["y", "z", "x"]]
    assert not lay.move(x, x, "left") and not lay.move(x, y, "giua")
    lay.apply("auto")  # [[y, z], [x]]
    assert lay.neighbor(y, "right") == x and lay.neighbor(x, "left") in (y, z) and lay.neighbor(y, "down") == z
    assert lay.neighbor(y, "up") is None and lay.neighbor(x, "right") is None
    assert lay.shift(x, "left") and lay.find(x)[0] == 0 and not lay.shift(x, "left")
    before = sum(c.w for c in lay.cols)
    for _ in range(40):  # kéo quá tay vẫn giữ tỉ lệ tối thiểu, tổng không đổi
        lay.resize_col(0, 0.05)
    assert abs(sum(c.w for c in lay.cols) - before) < 1e-9 and min(c.w for c in lay.cols) > 0
    lay.set_sizes([3, 1], {y: 2})
    save_layout(tmp_path, lay)
    back = load_layout(tmp_path)
    assert back.to_dict() == lay.to_dict()
    (tmp_path / ".ateam" / "grid.json").write_text('{"cols": [{"w": "x", "cells": [{"agent": "a", "h": -1}, 5]}, 3]}')
    bad = load_layout(tmp_path)  # file hỏng một phần: bỏ phần sai, giá trị lạ về mặc định
    assert _ids(bad) == [["a"]] and bad.cols[0].w == 1.0 and bad.cols[0].cells[0].h == 1.0
    (tmp_path / ".ateam" / "grid.json").write_text("{không phải json")
    assert load_layout(tmp_path).cols == []


def test_interactive_argv_model_effort():
    from ateam.config import AgentConfig
    a = AgentConfig("claude", ["claude", "-p", "{prompt}"], model_args=["--model", "{model}"],
                    effort_args=["--effort", "{effort}"], efforts=["low", "high"])
    assert a.interactive_argv("s1") == ["claude", "--resume", "s1"]
    assert a.interactive_argv(None, model="opus", effort="high") == ["claude", "--model", "opus", "--effort", "high"]
    assert a.interactive_argv("s1", effort="low") == ["claude", "--resume", "s1", "--effort", "low"]


# ---------------------------------------------------------------- vterm
def test_vterm_basics():
    from ateam.vterm import DEFAULT, Screen
    out = []
    s = Screen(5, 12, reply=out.append)
    s.feed(b"ab\x1b[31mcd\x1b[0m\r\nxin ch")
    s.feed("ào".encode()[:1])  # UTF-8 bị cắt giữa chừng: chờ phần sau
    s.feed("ào".encode()[1:])
    assert s.text().splitlines()[:2] == ["abcd", "xin chào"]
    assert s.lines[0][2][1][0] == 1 and s.lines[0][4][1] == DEFAULT  # màu đỏ (31) rồi reset
    s.feed(b"\x1b[6n\x1b[c")
    assert out == [b"\x1b[2;9R", b"\x1b[?62;22c"]
    s.feed(b"\x1b[2J\x1b[3;4HX\x1b[1;1H\x1b[2KY\x1b[38;5;200mZ\x1b[48;2;1;2;3mW")
    assert s.text().splitlines()[0] == "YZW" and s.lines[2][3][0] == "X"
    assert s.lines[0][1][1][0] == 200 and s.lines[0][2][1][1] == "#010203"
    s.feed("\x1b[4;1H你好abcdefghij".encode())  # chữ rộng chiếm 2 ô, tự xuống dòng ở cuối dòng
    assert s.lines[3][0][0] == "你" and s.lines[3][1][0] == "" and s.text().split("\n")[4] == "ij"
    s.feed(b"\x1b[?1049h\x1b[HALT")
    assert s.in_alt and s.text().startswith("ALT")
    s.feed(b"\x1b[?1049l")
    assert not s.in_alt and "X" in s.text()


def test_vterm_scroll_region_history_resize():
    from ateam.vterm import Screen
    s = Screen(4, 10)
    for i in range(6):
        s.feed(f"l{i}\r\n".encode())
    assert [ln[:2] for ln in s.text().splitlines()] == ["l3", "l4", "l5"] and len(s.history) == 3
    s.feed(b"\x1b[2;3r\x1b[2;1H")  # vùng cuộn dòng 2-3: cuộn trong vùng, không vào lịch sử
    s.feed(b"\x1b[3;1H\nNEW")
    lines = s.text().split("\n")
    assert lines[0] == "l3" and lines[2] == "NEW" and len(s.history) == 3
    s.feed(b"\x1b[r\x1b[1;1H\x1b[2L")  # chèn 2 dòng trống ở đầu
    assert s.text().split("\n")[:3] == ["", "", "l3"]
    s.resize(2, 6)
    assert s.rows == 2 and all(len(ln) == 6 for ln in s.lines)
    s.resize(6, 20)
    assert len(s.lines) == 6 and all(len(ln) == 20 for ln in s.lines)


def test_vterm_keys():
    from ateam.vterm import encode
    assert encode("enter") == b"\r" and encode("backspace") == b"\x7f" and encode("escape") == b"\x1b"
    assert encode("up") == b"\x1b[A" and encode("up", app_cursor=True) == b"\x1bOA"
    assert encode("ctrl+c") == b"\x03" and encode("ctrl+r") == b"\x12" and encode("shift+tab") == b"\x1b[Z"
    assert encode("ctrl+left") == b"\x1b[1;5D" and encode("alt+b", "b") == b"\x1bb"
    assert encode("a", "a") == b"a" and encode("ê", "ê") == "ê".encode() and encode("f13") == b""


# ---------------------------------------------------------------- GridHub + CLI giả lập
async def _until(pred, timeout=10):
    for _ in range(int(timeout / 0.05)):
        if pred():
            return True
        await asyncio.sleep(0.05)
    return False


def test_grid_hub_runs_cli(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import ensure_global_config, load_config
    from ateam.grid import SHELL, GridHub, load_layout
    ensure_global_config()
    cfg = load_config(project)

    async def main():
        hub = GridHub(project, lambda: cfg, lambda a: "phien-1")
        events = []
        hub.listen(lambda cid, kind, p: events.append((cid, kind, p)))
        cid, err = await hub.add("claude", effort="high", rows=20, cols=70)
        assert cid and not err and hub.status(cid) == "run"
        def clean(cell):
            return re.sub(rb"\x1b\[[0-9;]*m", b"", bytes(hub.terms[cell].buf))

        def out():
            return clean(cid)
        assert await _until(lambda: b"gia lap tuong tac" in out())
        assert b"--resume phien-1" in out() and b"--effort high" in out()
        hub.write(cid, b"size\r")
        assert await _until(lambda: b"20 70" in out())
        hub.resize(cid, 25, 90)
        hub.write(cid, b"size\r")
        assert await _until(lambda: b"25 90" in out())
        cid2, _ = await hub.add("codex", resume=False)
        assert await _until(lambda: b"codex" in bytes(hub.terms[cid2].buf))
        hub.bcast = True  # gửi tất cả: gõ ở một ô, mọi ô nhận
        hub.update_cell(cid2, bcast=False)
        hub.write(cid, b"chung\r")
        assert await _until(lambda: b"claude> chung" in out())
        hub.update_cell(cid2, bcast=True)
        hub.write(cid, b"lan2\r")
        assert await _until(lambda: b"codex> lan2" in clean(cid2))
        assert b"codex> chung" not in clean(cid2)
        assert [c.agent for c in load_layout(project).cells()] == ["claude", "codex"]  # đã lưu
        hub.bcast = False
        hub.write(cid, b"exit\r")
        assert await _until(lambda: any(k == "exit" and c == cid for c, k, _ in events))
        assert hub.status(cid) == "exit" and hub.status(cid2) == "run"
        assert await hub.start(cid) == "" and hub.status(cid) == "run"  # mở lại, giữ output cũ
        assert b"20 70" in out()
        st = hub.state()
        assert [c["agent"] for col in st["cols"] for c in col["cells"]] == ["claude", "codex"]
        assert st["cols"][0]["cells"][0]["lead"] and st["cols"][0]["cells"][0]["status"] == "run"
        none, err = await hub.add("khong-co")
        assert none is None and err
        # ô terminal trống: shell của người dùng (SHELL) trong thư mục dự án, không cần agent
        monkeypatch.setenv("SHELL", "/bin/sh")
        sh, err = await hub.add(SHELL, model="x", effort="high")
        assert sh and not err and hub.terms[sh].argv == ["/bin/sh", "-l"]
        hub.write(sh, b"echo xin-$((1+1))\r")
        assert await _until(lambda: b"xin-2" in clean(sh))
        cell = next(c for col in hub.state()["cols"] for c in col["cells"] if c["id"] == sh)
        assert cell["shell"] and not cell["model"] and not cell["effort"] and not cell["resume"]
        hub.close(sh)
        hub.close(cid)
        assert hub.layout.find(cid) is None and cid not in hub.terms
        # mở lại ateam: bố cục còn, CLI chưa chạy cho tới khi người dùng mở
        hub2 = GridHub(project, lambda: cfg, lambda a: None)
        assert [c.agent for c in hub2.layout.cells()] == ["codex"] and hub2.status(cid2) == "off"
        hub.shutdown()
    asyncio.run(main())



def test_attention_signals():
    """Ô cần người dùng: OSC 9 / OSC 777 / BEL, bỏ qua tiêu đề + thanh tiến trình + bíp lúc gõ; đoán "xong lượt"."""
    from ateam.grid import Attention
    a = Attention()
    assert a.feed(b"x\x1b]9;Claude needs", 10) == []  # OSC bị cắt giữa hai chunk
    assert a.feed(b" your permission\x07rest", 10.1) == [("ask", "Claude needs your permission")]
    assert a.feed(b"\x1b]9;4;3;\x07\x1b]0;tieu de\x07\x1b]2;x\x1b\\", 20) == []
    assert a.feed(b"\x1b", 30) == [] and a.feed(b"]777;notify;Codex;Turn complete\x1b\\", 30) == [("ask", "Turn complete")]
    assert a.feed(b"\x07", 31) == []  # dồn dập: một thông báo mỗi QUIET_S giây
    assert a.feed(b"\x07", 40) == [("ask", "")]
    a.typed(b"x", 50)
    assert a.feed(b"\x07", 50.5) == []  # bíp ngay sau phím gõ
    # xong lượt: Enter → output ≥ MIN_TURN_S → im IDLE_S
    a.typed(b"lam di\r", 60)
    a.feed(b"...", 61)
    a.feed(b"...", 66)
    assert a.idle(68) == []  # chưa đủ im
    assert a.idle(71) == []  # chưa đủ IDLE_S
    assert a.idle(73) == [("done", "")] and a.idle(80) == []
    assert a.feed(b"\x1b]9;Claude needs your permission\x07", 74) == [("ask", "Claude needs your permission")]
    a.typed(b"\r", 90)
    a.feed(b">", 90.2)
    assert a.idle(97.2) == []  # lượt ngắn
    a.typed(b"hoi\r", 100)
    a.feed(b"...", 101)
    a.feed(b"\x1b]9;waiting\x07", 106)
    assert a.idle(113) == []  # đã có thông báo thật trong lượt
    shell = Attention(guess=False)
    shell.typed(b"npm run dev\r", 0)
    shell.feed(b"...", 1)
    shell.feed(b"...", 9)
    assert shell.idle(16) == []


def test_grid_hub_attention(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam import grid
    from ateam.config import ensure_global_config, load_config
    monkeypatch.setattr(grid, "IDLE_S", 0.6)
    monkeypatch.setattr(grid, "MIN_TURN_S", 0.4)
    monkeypatch.setattr(grid, "QUIET_S", 0)
    monkeypatch.setenv("SHELL", "/bin/sh")
    monkeypatch.setenv("TERM_PROGRAM", "vscode")
    ensure_global_config()
    cfg = load_config(project)

    async def main():
        hub = grid.GridHub(project, lambda: cfg, lambda a: None)
        notes = []
        hub.listen(lambda cid, kind, p: kind == "notice" and notes.append((cid, p)))
        cid, _ = await hub.add("claude")
        out = lambda: bytes(hub.terms[cid].buf)  # noqa: E731
        assert await _until(lambda: b"gia lap tuong tac" in out())
        hub.write(cid, b"termprog\r")  # Claude Code chỉ gửi OSC 9 khi tưởng đang ở iTerm
        assert await _until(lambda: b"TP=iTerm.app" in out())
        hub.write(cid, b"title\r")
        hub.write(cid, b"notify xin quyen\r")
        assert await _until(lambda: notes)
        assert notes == [(cid, {"kind": "ask", "text": "xin quyen", "agent": "claude"})]
        hub.write(cid, b"work\r")
        assert await _until(lambda: len(notes) == 2)
        assert notes[1] == (cid, {"kind": "done", "text": "", "agent": "claude"})
        sh, _ = await hub.add(grid.SHELL)
        hub.write(sh, b"echo TP=$TERM_PROGRAM-; for i in 1 2 3 4; do sleep 0.2; done; echo xong-$((2+3))\r")
        assert await _until(lambda: b"xong-5" in bytes(hub.terms[sh].buf))
        assert b"TP=vscode-" in bytes(hub.terms[sh].buf)  # ô shell giữ env thật
        await asyncio.sleep(1.2)
        assert len(notes) == 2  # ô shell không đoán "xong lượt"
        hub.shutdown()
    asyncio.run(main())

# ---------------------------------------------------------------- web
def test_web_grid_ops(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from aiohttp.test_utils import TestClient, TestServer
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.web import WebApp
    from test_web import _free_port
    ensure_global_config()
    port = _free_port()
    wa = WebApp(project, load_config(project), DB(project / ".ateam/team.db"), port)
    hello = wa.hello()
    assert "lead" in hello["grid_presets"] and {a["name"]: a["tty"] for a in hello["agents"]}["claude"]

    async def recv_until(ws, pred, n=300):
        for _ in range(n):
            m = await ws.receive_json(timeout=10)
            if pred(m):
                return m
        raise AssertionError("không nhận được tin mong đợi")

    async def main():
        c = TestClient(TestServer(wa.make_app(), host="127.0.0.1", port=port))
        await c.start_server()
        try:
            hdr = {"Origin": f"http://127.0.0.1:{port}"}
            ws = await c.ws_connect("/ws", headers=hdr)
            await ws.send_json({"op": "grid_attach"})
            st = await recv_until(ws, lambda m: m["t"] == "grid")
            assert st["cols"] == []
            await ws.send_json({"op": "grid_add", "agent": "claude", "rows": 22, "cols": 77, "ref": 1})
            r = await recv_until(ws, lambda m: m["t"] == "toast" and m.get("ref") == 1)
            cid = r["grid_cell"]
            await ws.send_json({"op": "grid_in", "id": cid, "data": "size\r"})
            await recv_until(ws, lambda m: m["t"] == "gpty" and b"22 77" in base64.b64decode(m["data"]))
            await ws.send_json({"op": "grid_add", "agent": "grok", "ref": 2})
            cid2 = (await recv_until(ws, lambda m: m["t"] == "toast" and m.get("ref") == 2))["grid_cell"]
            await ws.send_json({"op": "grid_move", "src": cid2, "dst": cid, "where": "left"})
            st = await recv_until(ws, lambda m: m["t"] == "grid" and m["cols"][0]["cells"][0]["id"] == cid2)
            await ws.send_json({"op": "grid_preset", "preset": "stack"})
            st = await recv_until(ws, lambda m: m["t"] == "grid" and m["preset"] == "stack")
            assert len(st["cols"]) == 1 and len(st["cols"][0]["cells"]) == 2
            await ws.send_json({"op": "grid_sizes", "heights": {cid: 3}})
            st = await recv_until(ws, lambda m: m["t"] == "grid" and m["preset"] == "")
            assert {x["id"]: x["h"] for x in st["cols"][0]["cells"]}[cid] == 3
            await ws.send_json({"op": "grid_bcast", "on": True})
            await recv_until(ws, lambda m: m["t"] == "grid" and m["bcast"])
            # ô cần người dùng: thông báo tới cả tab không mở mục Lưới
            other = await c.ws_connect("/ws", headers=hdr)
            await ws.send_json({"op": "grid_in", "id": cid, "data": "notify can ban\r"})
            n = await recv_until(other, lambda m: m["t"] == "notice" and m["cell"] == cid)  # "gửi tất cả": ô grok cũng báo
            assert (n["kind"], n["cell"], n["body"], n["title"]) == ("grid_ask", cid, "can ban", "🔔 claude cần bạn")
            await other.close()
            # tab thứ hai mở sau: nhận lại bố cục + output gần nhất của từng ô
            ws2 = await c.ws_connect("/ws", headers=hdr)
            await ws2.send_json({"op": "grid_attach"})
            rep = await recv_until(ws2, lambda m: m["t"] == "gpty" and m.get("replay") and m["id"] == cid)
            assert b"22 77" in base64.b64decode(rep["data"])
            await ws2.close()
            await ws.close()  # đóng tab không dừng CLI
            await asyncio.sleep(0.2)
            assert wa.grid.status(cid) == "run"
            ws = await c.ws_connect("/ws", headers=hdr)
            await ws.send_json({"op": "grid_attach"})
            await recv_until(ws, lambda m: m["t"] == "grid")
            await ws.send_json({"op": "grid_close", "id": cid})
            st = await recv_until(ws, lambda m: m["t"] == "grid" and len(m["cols"][0]["cells"]) == 1)
            assert cid not in wa.grid.terms
            await ws.send_json({"op": "submit", "text": "/grid codex", "ref": 3})
            r = await recv_until(ws, lambda m: m["t"] == "toast" and m.get("ref") == 3)
            assert r["open"] == {"view": "grid"} and "codex" in [x.agent for x in wa.grid.layout.cells()]
            await ws.close()
        finally:
            wa.grid.shutdown()
            await c.close()
    asyncio.run(main())
    saved = json.loads((project / ".ateam" / "grid.json").read_text())
    assert [x["agent"] for col in saved["cols"] for x in col["cells"]] == ["grok", "codex"]


# ---------------------------------------------------------------- TUI
def test_tui_grid_tab(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import ConfirmScreen, TeamApp
    from ateam.tui_grid import GridAddScreen, GridCell, TermView

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.3)
            app.run_command("/grid claude")
            await _until(lambda: len(app.query(GridCell)) == 1)
            assert app.query_one("#tabs").active == "tab-grid"
            app.query_one("#grid-add").press()
            await pilot.pause(0.3)
            assert isinstance(app.screen, GridAddScreen)
            await pilot.press("down")  # codex
            await pilot.pause(0.1)
            app.screen.query_one("#ga-ok").press()
            assert await _until(lambda: len(app.query(GridCell)) == 2)
            await pilot.pause(0.5)
            assert isinstance(app.focused, TermView)
            cid = app.focused.cell_id
            assert app.grid.layout.cell(cid).agent == "codex"
            assert await _until(lambda: "gia lap tuong tac" in app.grid_screen(cid).text())
            for ch in "xin":
                await pilot.press(ch)
            await pilot.press("enter")
            assert await _until(lambda: "codex> xin" in app.grid_screen(cid).text())
            await pilot.press("ctrl+t")  # phím Ctrl của ateam nhường cho CLI khi đang gõ trong ô
            await pilot.pause(0.3)
            assert app.query_one("#tabs").active == "tab-grid"
            # macOS: Ctrl+T là VSTATUS của tty (in tải hệ thống, không echo) — kiểm byte tới CLI bằng Ctrl+G (^G)
            await pilot.press("ctrl+g")
            assert await _until(lambda: "^G" in app.grid_screen(cid).text())
            await pilot.press("enter")
            # F10: chế độ sắp xếp — Shift+← đổi chỗ với ô bên trái, 2 = bố cục "Hai cột"
            await pilot.press("f10")
            assert app.grid_arrange
            await pilot.press("shift+left")
            await pilot.pause(0.4)
            assert [c.agent for c in app.grid.layout.cells()] == ["codex", "claude"]
            await pilot.press("2")
            await pilot.pause(0.3)
            assert app.grid.layout.preset == "cols2"
            await pilot.press("escape")
            assert not app.grid_arrange
            await pilot.press("e", "x", "i", "t", "enter")
            assert await _until(lambda: app.grid.status(cid) == "exit")
            await pilot.pause(0.2)
            await pilot.press("enter")  # CLI đã thoát: Enter mở lại
            assert await _until(lambda: app.grid.status(cid) == "run")
            app.query_one(f"GridCell .gc-close").press()  # ô đầu (codex, đang chạy): hỏi lại trước khi dừng
            await pilot.pause(0.3)
            assert isinstance(app.screen, ConfirmScreen)
            await pilot.press("y")
            assert await _until(lambda: len(app.query(GridCell)) == 1)
            assert [c.agent for c in app.grid.layout.cells()] == ["claude"]
            await pilot.press("ctrl+q")
    asyncio.run(main())
