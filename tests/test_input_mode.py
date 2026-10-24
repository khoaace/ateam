"""Gõ mục tiêu (không kèm lệnh) đi đâu: trưởng nhóm lập kế hoạch hay một workflow tuỳ chỉnh — ô chọn cạnh ô
nhập (web), nút cạnh ô nhập / F4 (TUI), nút ★ ở mục 🧩 Tuỳ chỉnh. Lựa chọn lưu ở state.json, dùng chung TUI ↔ web."""

from __future__ import annotations

import asyncio

import pytest

STEPS = [{"agent": "lead", "title": "Thiết kế {goal}"}, {"agent": "claude", "title": "Viết code", "after": "1"}]


def test_web_input_mode_runs_custom_workflow(env, project, monkeypatch):
    pytest.importorskip("aiohttp")
    from test_web import _web_app

    from ateam.config import load_project_state
    wa = _web_app(env, project, monkeypatch)

    async def main():
        r = await wa.handle({"op": "custom_save", "kind": "workflows", "name": "nhanh", "review": False,
                             "steps": STEPS})
        assert r[1] == "ok"
        r = await wa.handle({"op": "input_mode", "name": "khong-co"})
        assert r[1] == "warn" and wa.cfg.default_workflow == ""
        r = await wa.handle({"op": "input_mode", "name": "nhanh"})
        assert r[1] == "ok" and r[2]["mode_saved"] and "nhanh" in r[0]
        assert wa.cfg.default_workflow == "nhanh" and load_project_state(project)["default_workflow"] == "nhanh"
        assert wa.snapshot()["workflow"] == "nhanh"
        # gõ thẳng mục tiêu: chạy workflow, không cần /flow
        await wa.handle({"op": "submit", "text": "trang đăng nhập"})
        g = wa.db.goals()[-1]
        assert g.workflow == "nhanh"
        assert [t.title for t in wa.db.tasks() if t.goal_id == g.id] == ["Thiết kế trang đăng nhập", "Viết code"]
        # về trưởng nhóm lập kế hoạch
        r = await wa.handle({"op": "input_mode", "name": ""})
        assert r[1] == "ok" and wa.cfg.default_workflow == "" and load_project_state(project)["default_workflow"] == ""
    asyncio.run(main())


def test_tui_input_mode_picker_and_star_button(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from textual.widgets import Input

    from ateam import wizard
    from ateam.config import ensure_global_config, load_config, load_project_state, load_state, save_custom_item
    from ateam.db import DB
    from ateam.tui import CustomPanel, InputModeScreen, TeamApp

    ensure_global_config()
    cfg = load_config(project)
    save_custom_item("workflows", "nhanh", wizard.workflow_body(cfg, "nhanh", None, "", False, STEPS))

    async def main():
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))

        async def wait(cond, n=300):  # CI chạy song song có thể chậm: chờ tới ~30 giây, xong sớm thì thoát sớm
            for _ in range(n):
                await pilot.pause(0.1)
                if cond():
                    return True
            return False

        def label() -> str:
            return str(app.query_one("#cmd-mode").label)

        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.3)
            assert "Trưởng nhóm" in label()
            await pilot.press("f4")
            assert await wait(lambda: isinstance(app.screen, InputModeScreen))
            await pilot.press("down", "enter")  # dòng 2: workflow "nhanh"
            assert await wait(lambda: app.cfg.default_workflow == "nhanh")
            assert load_project_state(project)["default_workflow"] == "nhanh" and "⚙ nhanh" in label()
            assert "nhanh" in app.query_one("#cmd", Input).placeholder
            # bấm nút cạnh ô nhập: chọn lại trưởng nhóm
            app.query_one("#cmd-mode").press()
            assert await wait(lambda: isinstance(app.screen, InputModeScreen))
            await pilot.press("up", "enter")
            assert await wait(lambda: app.cfg.default_workflow == "" and "Trưởng nhóm" in label())
            # nút ★ Mặc định ở tab 🧩 Tuỳ chỉnh
            app.run_command("/custom")
            panel = app.query_one("#custom-tab", CustomPanel)
            def star():  # id nút có trong panel.ids trước khi nút vào DOM (CI chậm): chờ nút thật
                bid = next((b for b, (a, n) in panel.ids.items() if a == "default-flow" and n == "nhanh"), None)
                return bid if bid and panel.query("#" + bid) else None
            assert await wait(star)
            bid = star()
            panel.query_one("#" + bid).press()
            assert await wait(lambda: app.cfg.default_workflow == "nhanh" and "⚙ nhanh" in label())
            # /custom dựng lại bảng vai trò ở tab Agents: thoát giữa chừng thì Textual gỡ Select chưa mount xong
            roles = app.query_one("#roles-table")
            assert await wait(lambda: not roles._lock.locked() and roles.base is not None)
            await pilot.press("ctrl+q")
    asyncio.run(main())
