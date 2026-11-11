"""Hiệu năng: đọc DB / file ít hơn, gom output, không giữ dòng trùng — kiểm hành vi, không đo giờ."""

from __future__ import annotations

import asyncio
import importlib

from ateam import config
from ateam.logtail import read_tail


def test_read_tail_reads_only_end(tmp_path):
    p = tmp_path / "a.log"
    p.write_text("".join(f"dòng {i}\n" for i in range(100_000)))
    assert read_tail(p, 3) == ["dòng 99997", "dòng 99998", "dòng 99999"]
    assert read_tail(tmp_path / "chua-co.log", 3) == []


def test_db_indexes_and_task_index(project):
    from ateam.db import DB
    db = DB(project / ".ateam/team.db")
    names = {r["name"] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"tasks_status", "tasks_goal", "runs_started", "notes_author"} <= names
    tid = db.add_task("codex", "x", "x", status="queued")
    assert db.task_index() == {tid: ("queued", "codex")}
    sig = db.change_sig()
    assert db.change_sig() == sig
    db.update_task(tid, status="done", finished=1.0)
    assert db.change_sig() != sig


def test_which_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(config.shutil, "which", lambda b: calls.append(b) or "/bin/" + b)
    config._WHICH.clear()
    assert config.which("zz") == config.which("zz") == "/bin/zz"
    assert calls == ["zz"]
    config._WHICH.clear()


def test_system_log_rotates(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam import orchestrator
    from ateam.config import load_config
    from ateam.db import DB
    monkeypatch.setattr(orchestrator, "SYSTEM_LOG_MAX", 2000)
    o = orchestrator.Orchestrator(project, load_config(project), DB(project / ".ateam/team.db"))
    for i in range(100):
        o.log(f"dòng số {i} " + "x" * 40)
    assert (o.logs / "system.log").stat().st_size <= 2100
    assert (o.logs / "system.log.1").exists()


def test_reflow_log_hidden_pane_keeps_lines_once():
    from textual.app import App
    from ateam.tui import ReflowLog

    class A(App):
        def compose(self):
            log = ReflowLog(id="log", max_lines=50)
            log.display = False  # như ô agent khi tab Đội chưa mở
            yield log

    async def main():
        app = A()
        async with app.run_test(size=(80, 20)) as pilot:
            log = app.query_one(ReflowLog)
            for i in range(120):
                log.write(f"dòng {i}")
            assert len(log._items) == 50 and not log._deferred_renders  # có giới hạn, không hàng đợi riêng
            log.display = True
            await pilot.pause()
            await pilot.pause()
            assert len(log._items) == 50  # trước đây phát lại qua write() → dòng đôi
            assert len(log.lines) == 50 and "dòng 119" in log.lines[-1].text
    asyncio.run(main())


def test_reflow_log_written_while_tab_hidden_not_vertical():
    """Ghi log lúc tab bị ẩn (bề rộng 0) từng thành mỗi ký tự một dòng khi quay lại."""
    from textual.app import App
    from textual.widgets import Static, TabbedContent, TabPane
    from ateam.tui import ReflowLog

    class A(App):
        def compose(self):
            with TabbedContent(id="tc"):
                with TabPane("a", id="a"):
                    yield ReflowLog(id="log", wrap=True, min_width=1)
                with TabPane("b", id="b"):
                    yield Static("x")

    async def main():
        app = A()
        async with app.run_test(size=(80, 20)) as pilot:
            log = app.query_one(ReflowLog)
            log.write("trước khi ẩn")
            await pilot.pause()
            app.query_one("#tc").active = "b"
            await pilot.pause()
            log.write("ghi lúc tab đang ẩn")
            app.query_one("#tc").active = "a"
            await pilot.pause()
            await pilot.pause()
            assert [s.text.rstrip() for s in log.lines] == ["trước khi ẩn", "ghi lúc tab đang ẩn"]
    asyncio.run(main())


def test_board_reads_db_only_on_change_and_lazy_text(project):
    """DB.board(): vòng vẽ 0,5 giây không đọc lại bảng khi DB chưa đổi; task dạng nhẹ nạp prompt/kết quả khi cần."""
    from ateam.db import DB
    db = DB(project / ".ateam/team.db")
    tid = db.add_task("codex", "tiêu đề", "prompt rất dài", status="queued")
    db.update_task(tid, result="kết quả", error="lỗi")
    tasks, goals = db.board()
    assert goals == [] and [t.id for t in tasks] == [tid]
    t = tasks[0]
    assert "prompt" not in t.__dict__ and "result" not in t.__dict__ and t.error == "lỗi"
    assert db.board()[0][0] is t  # DB chưa đổi: dùng lại, không đọc lại
    tasks.clear()                 # danh sách trả về là bản sao: nơi gọi sửa không hỏng cache
    assert db.board()[0][0] is t
    assert db.lazy_loads == 0
    assert (t.prompt, t.result) == ("prompt rất dài", "kết quả") and db.lazy_loads == 1
    assert t.prompt and db.lazy_loads == 1  # nạp một lần
    db.update_task(tid, status="done")       # chính kết nối này ghi
    t2 = db.board()[0][0]
    assert t2 is not t and t2.status == "done"
    other = DB(project / ".ateam/team.db")   # tiến trình khác ghi (TUI ↔ web ↔ `ateam add`)
    other.add_task("claude", "khác", "p")
    assert len(db.board()[0]) == 2
    try:
        t2.khong_co
    except AttributeError:
        pass
    else:
        raise AssertionError("thuộc tính lạ phải báo AttributeError")


def test_web_snapshot_does_not_load_task_text(env, project, monkeypatch):
    """Ảnh chụp bảng việc của web không nạp prompt/kết quả từng task (mỗi lần là một truy vấn); task nháp thì có."""
    import pytest
    pytest.importorskip("aiohttp")
    from tests.test_web import _web_app
    wa = _web_app(env, project, monkeypatch)
    for i in range(30):
        wa.db.update_task(wa.db.add_task("codex", f"t{i}", "p" * 5000, status="done"), result="r" * 5000)
    draft = wa.db.add_task("codex", "nháp", "prompt nháp", status="draft")
    snap = wa.snapshot()
    by = {t["id"]: t for t in snap["tasks"]}
    assert by[draft]["prompt"] == "prompt nháp" and "result" not in by[draft]
    assert all("prompt" not in t for i, t in by.items() if i != draft)
    assert wa.db.lazy_loads == 1


def test_web_slow_tab_is_dropped_not_queued(env, project, monkeypatch):
    """Tab không nhận kịp: quá SEND_HARD thì đóng kết nối thay vì xếp hàng mãi trong RAM; lagging() hoãn ảnh chụp."""
    import pytest
    pytest.importorskip("aiohttp")
    from ateam import web as webmod
    from tests.test_web import _web_app
    wa = _web_app(env, project, monkeypatch)
    monkeypatch.setattr(webmod, "SEND_SOFT", 100)
    monkeypatch.setattr(webmod, "SEND_HARD", 1000)

    class SlowWS:
        closed = False

        def __init__(self):
            self.gate = asyncio.Event()
            self.got = []

        async def send_str(self, data):
            await self.gate.wait()
            self.got.append(data)

        async def close(self, **kw):
            self.closed = True
            self.gate.set()

    async def main():
        ws = SlowWS()
        jobs = [asyncio.ensure_future(wa._send(ws, "x" * 300)) for _ in range(3)]
        await asyncio.sleep(0)
        assert wa._pending[ws] == 900 and wa.lagging(ws) and not ws.closed
        await wa._send(ws, "x" * 300)  # vượt SEND_HARD
        assert ws.closed
        await asyncio.gather(*jobs)
        assert ws not in wa._pending
        await wa._send(ws, "y")        # đã đóng: bỏ
        assert "y" not in ws.got
        ok = SlowWS()
        ok.gate.set()
        await wa._send(ok, "z" * 300)
        assert ok.got == ["z" * 300] and ok not in wa._pending and not wa.lagging(ok)

    asyncio.run(main())


def test_tui_board_table_is_capped(env, project, monkeypatch):
    """Bảng việc TUI chỉ vẽ BOARD_LIMIT task gần nhất + task còn dở, và vẽ không nạp prompt/kết quả từng task."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from textual.widgets import DataTable
    from ateam import tui
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    monkeypatch.setattr(tui, "BOARD_LIMIT", 20)

    async def main():
        ensure_global_config()
        db = DB(project / ".ateam/team.db")
        old_asking = db.add_task("codex", "còn dở", "p", status="asking")
        for i in range(60):
            db.add_task("codex", f"t{i}", "p", status="done")
        app = tui.TeamApp(project, load_config(project), db)
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.8)
            if app.task_groups:
                app.action_toggle_task_groups()  # bảng phẳng: mỗi task một dòng
            await pilot.pause(0.2)
            assert set(app._rows) == {old_asking} | set(range(42, 62))
            assert app.query_one("#tasks", DataTable).row_count == 21
            before = db.lazy_loads
            app.refresh_view()
            assert db.lazy_loads == before
            await pilot.press("ctrl+q")

    asyncio.run(main())


def test_run_spills_old_output_to_disk(monkeypatch):
    """Lượt agent in rất nhiều: RAM chỉ giữ phần đuôi, `output` vẫn đủ từng dòng (khối DELEGATE ở đầu không mất)."""
    import sys

    from ateam import runner
    monkeypatch.setattr(runner, "SPILL_LINES", 10)
    seen = []
    code = "print('<<<NOTE>>> đầu <<<END>>>');\nfor i in range(95): print('dòng', i)\nprint('SUMMARY: xong')"
    run = runner.Run([sys.executable, "-c", code], ".", {"PYTHONIOENCODING": "utf-8"}, use_pty=False, timeout=0,
                     on_line=seen.append)
    assert asyncio.run(run.start()) == 0
    want = ["<<<NOTE>>> đầu <<<END>>>"] + [f"dòng {i}" for i in range(95)] + ["SUMMARY: xong"]
    assert seen == want
    assert len(run.lines) < 20 and run.spilled + len(run.lines) == len(want)
    assert run.output == "\n".join(want) and run.output is run.output
    # keep_lines (dev server…): chỉ giữ đuôi, không ghi file
    tail = runner.Run([sys.executable, "-c", code], ".", {"PYTHONIOENCODING": "utf-8"}, use_pty=False, timeout=0,
                      on_line=lambda s: None, keep_lines=5)
    assert asyncio.run(tail.start()) == 0
    assert list(tail.lines) == want[-5:] and tail.spilled == 0 and tail._spill is None


def test_vterm_history_shares_cells():
    """Lịch sử terminal: ô giống nhau (cùng ký tự + kiểu chữ) là cùng một tuple — không tạo tuple riêng cho từng ô."""
    from ateam import vterm
    s = vterm.Screen(5, 40)
    for i in range(30):
        s.feed(("\x1b[32mabc abc\x1b[0m %d\r\n" % (i % 3)).encode())
    assert len(s.history) >= 25
    a, b = s.history[0], s.history[3]
    assert "".join(c[0] for c in a).rstrip() == "abc abc 0" and a[0][1] != vterm.DEFAULT
    assert all(x is y for x, y in zip(a, b))          # hai dòng giống nhau: dùng chung từng ô
    assert a[0] is a[4] and a[0] is not a[1]          # 'a' xanh ở hai chỗ là một; 'a' khác 'b'
    assert len({id(c) for ln in s.history for c in ln}) < len(s.history) + 20  # mỗi dòng thêm tối đa một ô trống riêng
    s.feed("\x1b[31ma\x1b[0m".encode())                # đổi kiểu chữ: ô khác
    assert s.lines[s.y][0] is not a[0] and s.lines[s.y][0][0] == "a"
