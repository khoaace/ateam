"""Smoke test giao diện: mở app headless, giao task, chuyển tab, xem diff, thoát."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from conftest import git_init, write_project_config


def test_tui_smoke(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)
    write_project_config(project, 'isolation = "worktree"\nmerge = "review"\n')

    import importlib

    import ateam.config
    importlib.reload(ateam.config)  # đọc XDG_CONFIG_HOME của test
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import AgentPane, DiffScreen, TeamApp

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.3)
            app.run_command("/effort claude high")
            app.run_command("/task grok tạo b")
            for _ in range(60):
                await pilot.pause(0.25)
                t = app.db.tasks()
                if t and t[0].status == "review":
                    break
            assert app.db.tasks()[0].status == "review"
            await pilot.press("ctrl+t")
            await pilot.pause(0.3)
            assert len(app.query(AgentPane)) == 4
            await pilot.press("ctrl+t")
            app.show_task(1)
            await pilot.press("ctrl+d")
            await pilot.pause(0.5)
            # màn hình diff: danh sách file của nhánh task, hai cột ↔ một cột, Ctrl+Y merge rồi đóng
            assert isinstance(app.screen, DiffScreen) and app.view_task == 1
            files = app.screen.ds.files
            assert [(f.status, f.path) for f in files] == [("A", "b.txt")]
            assert app.screen.is_split()  # màn hình 160 cột: mặc định hai cột
            await pilot.press("s")
            await pilot.pause(0.2)
            assert not app.screen.is_split()
            await pilot.press("ctrl+y")
            await pilot.pause(0.5)
            assert app.db.tasks()[0].status == "done"
            assert not isinstance(app.screen, DiffScreen)
            app.run_command("/usage")
            await pilot.press("ctrl+q")

    asyncio.run(main())
    assert (project / "b.txt").exists()
    assert os.environ.get("XDG_CONFIG_HOME") == env["XDG_CONFIG_HOME"]


def test_tui_file_mention_popup(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)
    (project / "src").mkdir()
    (project / "src" / "app.py").write_text("")
    (project / "my docs").mkdir()
    (project / "my docs" / "plan.md").write_text("")

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import CommandInput, MentionList, TeamApp

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.3)
            box = app.query_one("#cmd", CommandInput)
            popup = app.query_one("#mention", MentionList)
            await pilot.press(*"/task codex@high sửa @ap")
            await pilot.pause(0.5)
            assert popup.display
            await pilot.press("tab")
            await pilot.pause(0.2)
            assert box.value == "/task codex@high sửa @src/app.py "
            assert not popup.display
            await pilot.press(*"và @my")
            await pilot.pause(0.3)
            await pilot.press("enter")          # chọn thư mục: đi vào trong, danh sách vẫn mở
            await pilot.pause(0.2)
            assert box.value.endswith('@"my docs/') and popup.display
            await pilot.press("down", "up", "enter")
            await pilot.pause(0.2)
            assert box.value.endswith('và @"my docs/plan.md" ')
            await pilot.press(*"@")
            await pilot.pause(0.2)
            assert popup.display
            await pilot.press("escape")
            assert not popup.display
            await pilot.press("enter")          # danh sách đóng: Enter gửi lệnh như cũ
            await pilot.pause(0.3)
            assert box.value == ""
            t = app.db.tasks()[0]
            assert t.agent == "codex" and '@src/app.py và @"my docs/plan.md"' in t.prompt
            await pilot.press("ctrl+q")

    asyncio.run(main())


def test_tui_model_effort_picker(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from ateam.config import ensure_global_config, load_config, load_state
    from ateam.db import DB
    from ateam.tui import ChoiceScreen, TeamApp

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.5)
            claude = app.cfg.agents["claude"]
            app.run_command("/model claude")
            await pilot.pause(0.2)
            assert isinstance(app.screen, ChoiceScreen)
            await pilot.press("home", "down", "enter")  # đầu danh sách là "opus", xuống 1 = "sonnet"
            await pilot.pause(0.2)
            assert claude.model == "sonnet"
            assert load_state()["agents"]["claude"]["model"] == "sonnet"
            app.run_command("/effort claude")
            await pilot.pause(0.2)
            await pilot.press("up", "enter")  # từ "mặc định" (cuối) lên 1 = "max"
            await pilot.pause(0.2)
            assert claude.effort == "max"
            argv = claude.argv("x")
            assert argv[argv.index("--model") + 1] == "sonnet" and "max" in argv
            app.run_command("/effort claude")
            await pilot.pause(0.2)
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert not isinstance(app.screen, ChoiceScreen) and claude.effort == "max"
            # tab Đội hiện danh sách model/effort, mục đang dùng nằm trong đó
            await pilot.press("ctrl+t")
            await pilot.pause(0.8)
            head = str(app.pane("claude").head.render())
            assert "effort:" in head and "sonnet" in head and "haiku" in head
            # lần đầu mở app tự hỏi opencode/agy danh sách model
            for _ in range(20):
                if "xai/grok-5-fast" in app.cfg.agents["grok"].models:
                    break
                await pilot.pause(0.25)
            assert "xai/grok-5-fast" in app.cfg.agents["grok"].models
            app.run_command("/models grok")
            await pilot.press("ctrl+q")

    asyncio.run(main())


def test_tui_setup_screen(env, project, monkeypatch):
    """Màn hình thiết lập lần đầu: hỏi sẵn model từ CLI, chọn trưởng nhóm/model/effort, tắt agent,
    sửa vai trò, chọn workflow mặc định (gõ mục tiêu là chạy theo nó; /goal vẫn để trưởng nhóm)."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)
    write_project_config(project, 'approve_plan = true\n[workflows.nhanh]\ndescription = "làm nhanh"\n'
                                  '[[workflows.nhanh.steps]]\nagent = "grok"\ntitle = "Làm {goal}"\n')

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from textual.widgets import Checkbox, Select

    from ateam.config import ensure_global_config, load_config, load_state, needs_setup
    from ateam.db import DB
    from ateam.tui import RESET, AgentPane, SetupScreen, TeamApp, TextInput

    async def main():
        ensure_global_config()
        assert needs_setup()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"), setup=True)
        async with app.run_test(size=(160, 48)) as pilot:
            for _ in range(80):
                await pilot.pause(0.25)
                if isinstance(app.screen, SetupScreen) and app.screen.ready:
                    break
            scr = app.screen
            assert isinstance(scr, SetupScreen) and scr.ready
            await pilot.pause(0.3)
            # model hỏi được từ CLI giả lập đã có sẵn trong bảng chọn
            grok = scr.query_one("#setup-model-grok", Select)
            assert "xai/grok-5-fast" in [v for _, v in grok._options]
            agy = scr.query_one("#setup-model-antigravity", Select)
            assert "gemini-3-pro" in [v for _, v in agy._options]
            scr.query_one("#setup-lead", Select).value = "codex"
            scr.query_one("#setup-effort-claude", Select).value = "high"
            codex = scr.query_one("#setup-model-codex", Select)
            assert "gpt-6-luna" in [v for _, v in codex._options]  # từ `codex debug models`
            codex.value = "gpt-6-luna"
            grok.value = "xai/grok-5-fast"
            scr.query_one("#setup-on-antigravity", Checkbox).value = False
            role = scr.query_one("#setup-role-codex", TextInput)
            assert role.value == app.cfg.agents["codex"].role
            role.value = "Chỉ làm backend"
            flow = scr.query_one("#setup-flow", Select)
            assert [v for _, v in flow._options] == [RESET, "nhanh"] and flow.value == RESET
            flow.value = "nhanh"
            await pilot.press("ctrl+s")
            await pilot.pause(0.5)
            assert not isinstance(app.screen, SetupScreen)
            assert app.cfg.lead == "codex"
            assert app.cfg.agents["claude"].effort == "high"
            assert app.cfg.agents["grok"].model == "xai/grok-5-fast"
            assert not app.cfg.agents["antigravity"].enabled
            assert len(app.query(AgentPane)) == 3
            assert app.cfg.agents["codex"].role == "Chỉ làm backend"
            assert app.cfg.default_workflow == "nhanh"
            assert "workflow 'nhanh'" in app.query_one("#cmd").placeholder
            # gõ mục tiêu thường -> theo workflow mặc định; /goal -> trưởng nhóm lập kế hoạch
            box = app.query_one("#cmd")
            box.value = "đăng nhập"
            await pilot.press("enter")
            await pilot.pause(0.3)
            g = app.db.goals()[-1]
            assert g.workflow == "nhanh" and app.db.tasks(goal_id=g.id)[0].title == "Làm đăng nhập"
            app.run_command("/goal thêm trang hồ sơ")
            await pilot.pause(0.3)
            assert app.db.goals()[-1].workflow is None
            # mở lại bằng /setup, rồi Esc = giữ nguyên
            app.run_command("/setup")
            for _ in range(40):
                await pilot.pause(0.25)
                if isinstance(app.screen, SetupScreen) and app.screen.ready:
                    break
            assert app.screen.query_one("#setup-lead", Select).value == "codex"
            assert app.screen.query_one("#setup-model-claude", Select).value == RESET
            await pilot.press("escape")
            await pilot.pause(0.3)
            assert app.cfg.lead == "codex"
            await pilot.press("ctrl+q")

    asyncio.run(main())
    st = load_state()
    assert st["onboarded"] and st["lead"] == "codex"
    assert st["agents"]["antigravity"] == {"enabled": False}
    assert st["agents"]["claude"] == {"effort": "high"}
    assert st["agents"]["codex"]["role"] == "Chỉ làm backend" and st["default_workflow"] == "nhanh"
    assert "grok" in st["models_found"] and "antigravity" in st["models_found"]
    cfg = load_config(project)
    assert cfg.lead == "codex" and not cfg.agents["antigravity"].enabled
    assert not needs_setup()


def test_tui_paste_image(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    shot = project / "outside shot.png"
    shot.write_bytes(b"\x89PNG\r\n\x1a\n")

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from textual import events

    from ateam import clipboard
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import CommandInput, TeamApp

    async def fake_grab(folder):
        folder.mkdir(parents=True, exist_ok=True)
        p = folder / "paste-1.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n")
        return p, ""

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.3)
            box = app.query_one("#cmd", CommandInput)
            await pilot.press(*"sửa theo")
            monkeypatch.setattr(clipboard, "grab_image", fake_grab)
            await pilot.press("ctrl+v")
            await pilot.pause(0.3)
            assert box.value == "sửa theo @.ateam/images/paste-1.png ", box.value
            box.post_message(events.Paste(str(shot).replace(" ", "\\ ")))  # kéo-thả ảnh vào terminal
            await pilot.pause(0.3)
            assert box.value.endswith('paste-1.png @"outside shot.png" '), box.value
            box.post_message(events.Paste("chữ"))                       # dán chữ thường như cũ
            await pilot.pause(0.2)
            assert box.value.endswith(" chữ")

            async def no_image(folder):
                return None, "clipboard không có ảnh"
            monkeypatch.setattr(clipboard, "grab_image", no_image)
            before = box.value
            await pilot.press("ctrl+v")
            await pilot.pause(0.3)
            assert box.value == before
            await pilot.press("ctrl+q")

    asyncio.run(main())


def test_tui_custom_agents_and_workflows(env, project, monkeypatch, tmp_path):
    """/custom: thêm agent từ mẫu, thêm workflow từ mẫu, đội cập nhật ngay; /flow chạy workflow;
    nút ở màn hình thiết lập mở cùng màn hình và form thiết lập có agent mới."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from textual.widgets import Button, Checkbox, Input, Select

    from ateam.config import ensure_global_config, load_config, load_custom
    from ateam.db import DB
    from ateam.tui import AgentEditScreen, AgentPane, CustomScreen, SetupScreen, TeamApp, WorkflowEditScreen

    async def wait_for(pilot, cond, n=40):
        for _ in range(n):
            await pilot.pause(0.1)
            if cond():
                return True
        return False

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.3)
            app.run_command("/custom")
            assert await wait_for(pilot, lambda: isinstance(app.screen, CustomScreen))
            await pilot.click("#custom-add-agent")
            assert await wait_for(pilot, lambda: isinstance(app.screen, AgentEditScreen))
            ed = app.screen
            ed.query_one("#ag-template", Select).value = "trống"
            await pilot.pause(0.2)
            assert ed.query_one("#ag-name", Input).value == "my-agent"
            ed.query_one("#ag-name", Input).value = "codex"  # trùng agent có sẵn -> không lưu
            await pilot.press("ctrl+s")
            await pilot.pause(0.2)
            assert isinstance(app.screen, AgentEditScreen)
            ed.query_one("#ag-name", Input).value = "mine"
            ed.query_one("#ag-command", Input).value = "mycli --headless {prompt}"
            ed.query_one("#ag-role", Input).value = "Việc vặt"
            ed.query_one("#ag-efforts", Input).value = "low, high"
            ed.query_one("#ag-effort-args", Input).value = "--think {effort}"
            ed.query_one("#ag-file-args", Input).value = "-"
            await pilot.pause(0.2)
            assert "mycli --headless <prompt>" in str(ed.query_one("#agent-preview").render())
            await pilot.press("ctrl+s")
            assert await wait_for(pilot, lambda: isinstance(app.screen, CustomScreen))
            await pilot.pause(0.3)
            assert load_custom()["agents"]["mine"] == {
                "command": ["mycli", "--headless", "{prompt}"], "role": "Việc vặt",
                "efforts": ["low", "high"], "effort_args": ["--think", "{effort}"], "file_args": []}

            await pilot.click("#custom-add-flow")
            assert await wait_for(pilot, lambda: isinstance(app.screen, WorkflowEditScreen))
            wf = app.screen
            wf.query_one("#wf-template", Select).value = "review-code"
            await pilot.pause(0.3)
            assert wf.query_one("#wf-name", Input).value == "review-code"
            assert len(wf.query(".step-row")) == 2
            await pilot.click("#wf-add")
            await pilot.pause(0.3)
            rows = list(wf.query(".step-row"))
            assert len(rows) == 3
            k = rows[2].id[len("wf-step-"):]
            wf.query_one(f"#wf-agent-{k}", Select).value = "mine"
            wf.query_one(f"#wf-title-{k}", Input).value = "Tóm tắt"
            wf.query_one(f"#wf-after-{k}", Input).value = "5"  # sai -> báo lỗi, không lưu
            await pilot.press("ctrl+s")
            await pilot.pause(0.2)
            assert isinstance(app.screen, WorkflowEditScreen)
            wf.query_one(f"#wf-after-{k}", Input).value = "0"
            wf.query_one(f"#wf-effort-{k}", Input).value = "high"
            wf.query_one("#wf-review", Checkbox).value = False
            app.save_screenshot(str(tmp_path / "workflow.svg"))
            await pilot.press("ctrl+s")
            assert await wait_for(pilot, lambda: isinstance(app.screen, CustomScreen))
            await pilot.pause(0.3)
            app.save_screenshot(str(tmp_path / "custom.svg"))
            await pilot.press("escape")
            assert await wait_for(pilot, lambda: "mine" in app.cfg.agents and not isinstance(app.screen, CustomScreen))
            await pilot.pause(0.3)
            assert app.cfg.custom_agents == {"mine"}
            assert "review-code" in app.cfg.workflows
            assert any(p.agent == "mine" for p in app.query(AgentPane))
            steps = app.cfg.workflows["review-code"].steps
            assert [s.agent for s in steps] == ["lead", "codex", "mine"]
            assert steps[2].after == [] and steps[2].effort == "high"
            assert app.cfg.workflows["review-code"].review is False

            app.run_command("/flow review-code kiểm tra utils")
            await pilot.pause(0.3)
            ts = app.db.tasks()
            assert [(t.agent, t.status) for t in ts] == [("claude", "draft"), ("codex", "draft"),
                                                        ("mine", "draft")]
            assert ts[0].title == "Review" and ts[2].depends_on == [] and ts[1].depends_on == [ts[0].id]
            assert app.db.goal(1).workflow == "review-code"
            app.run_command("/go")
            assert await wait_for(pilot, lambda: app.db.goal(1).status in ("done", "incomplete"), 150)
            assert app.db.goal(1).status == "done"
            assert "Tóm tắt" in (project / "steps.txt").read_text()

            # màn hình thiết lập: nút mở cùng màn hình; xoá agent tuỳ chỉnh (bấm 2 lần) -> form dựng lại
            app.open_setup()
            assert await wait_for(pilot, lambda: isinstance(app.screen, SetupScreen) and app.screen.ready, 200)
            assert app.screen.query("#setup-on-mine")
            app.save_screenshot(str(tmp_path / "setup.svg"))
            await pilot.click("#setup-custom")
            assert await wait_for(pilot, lambda: isinstance(app.screen, CustomScreen))
            await pilot.pause(0.3)
            dels = [b for b in app.screen.query(Button) if str(b.label) == "Xoá"]
            await pilot.click("#" + dels[0].id)
            await pilot.pause(0.2)
            assert "mine" in load_custom().get("agents", {})
            await pilot.click("#" + dels[0].id)
            await pilot.pause(0.3)
            assert "mine" not in load_custom().get("agents", {})
            await pilot.press("escape")
            assert await wait_for(pilot, lambda: isinstance(app.screen, SetupScreen) and app.screen.ready)
            assert not app.screen.query("#setup-on-mine") and "mine" not in app.cfg.agents
            await pilot.press("escape")
            await pilot.press("ctrl+q")

    asyncio.run(main())


def test_tui_command_popup_help_and_empty_state(env, project, monkeypatch):
    """Gõ / hiện danh sách lệnh; F1 / /help mở trợ giúp; bảng việc trống có hướng dẫn."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import CommandInput, HelpScreen, MentionList, TeamApp

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.5)
            empty = app.query_one("#tasks-empty")
            assert empty.display and not app.query_one("#tasks").display
            assert "Chưa có task" in str(empty.render())
            box = app.query_one("#cmd", CommandInput)
            popup = app.query_one("#mention", MentionList)
            await pilot.press("/", "s", "e")
            await pilot.pause(0.2)
            assert popup.display and popup.border_title == "/ lệnh"
            ids = [popup.get_option_at_index(i).id for i in range(popup.option_count)]
            assert ids == ["set", "setup", "pause"]  # bắt đầu bằng "se" trước, rồi chứa "se"
            await pilot.press("tab")                # chèn lệnh có tham số, chờ gõ tiếp
            assert box.value == "/set " and not popup.display
            box.value = ""
            await pilot.press(*"/pau", "enter")     # lệnh không tham số: Enter chạy luôn
            await pilot.pause(0.2)
            assert app.orch.paused and box.value == ""
            await pilot.press(*"/help", "enter")    # gõ đủ tên lệnh: Enter chạy, không chèn
            await pilot.pause(0.3)
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("f1")
            await pilot.pause(0.2)
            assert not isinstance(app.screen, HelpScreen)
            await pilot.press("f1")
            await pilot.pause(0.2)
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert not isinstance(app.screen, HelpScreen)
            app.run_command("/resume")
            app.run_command("/task codex tạo a")
            await pilot.pause(0.6)
            assert app.query_one("#tasks").display and not empty.display
            await pilot.press("ctrl+q")

    asyncio.run(main())


def test_tui_task_agent_popup_and_raw_prompt(env, project, monkeypatch, tmp_path):
    """/task: gõ xong lệnh thì hiện danh sách agent; prompt gửi agent đúng nguyên văn."""
    full = tmp_path / "full.log"
    for k, v in dict(env, ATEAM_FAKE_FULL_LOG=str(full)).items():
        monkeypatch.setenv(k, v)
    git_init(project)

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import CommandInput, MentionList, TeamApp

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.5)
            box = app.query_one("#cmd", CommandInput)
            popup = app.query_one("#mention", MentionList)
            await pilot.press(*"/tas", "tab")           # chọn lệnh /task -> mở luôn danh sách agent
            await pilot.pause(0.2)
            assert box.value == "/task " and popup.display
            assert popup.border_title.startswith("/task")
            ids = [popup.get_option_at_index(i).id for i in range(popup.option_count)]
            assert ids == ["claude", "codex", "antigravity", "grok"]
            assert "Viết code" in str(popup.get_option_at_index(1).prompt)  # vai trò
            await pilot.press("c", "o")
            await pilot.pause(0.1)
            assert [popup.get_option_at_index(i).id for i in range(popup.option_count)] == ["codex"]
            await pilot.press("enter")                  # Enter chọn agent, không gửi lệnh
            assert box.value == "/task codex " and not popup.display and not app.db.tasks()
            await pilot.press(*"xin chào", "enter")
            for _ in range(40):
                await pilot.pause(0.25)
                t = app.db.tasks()
                if t and t[0].status == "done":
                    break
            assert app.db.tasks()[0].status == "done"
            # nút Dọn: chỉ xoá task đã kết thúc mà mục tiêu đã xong và không còn ai chờ nó
            db, first = app.db, app.db.tasks()[0].id
            live = db.add_goal("đang review")  # chưa kết thúc ("reviewing": không bị review lại)
            db.update_goal(live, status="reviewing")
            ended = db.add_goal("đã xong")
            db.update_goal(ended, status="done")
            keep_goal = db.add_task("codex", "a", "a", goal_id=live, status="done")
            needed = db.add_task("codex", "b", "b", status="failed")
            db.add_task("codex", "c", "c", status="draft", depends_on=[needed])
            gone = db.add_task("codex", "d", "d", goal_id=ended, status="cancelled")
            app.refresh_view()
            await pilot.pause(0.2)
            clear = app.query_one("#board-clear")
            assert app.query_one("#board-tools").display and "2 task" in str(clear.label)
            await pilot.click("#board-clear")
            await pilot.pause(0.3)
            ids = {t.id for t in db.tasks()}
            assert keep_goal in ids and needed in ids and first not in ids and gone not in ids
            assert [g.id for g in db.goals()] == [live]
            assert first not in app._rows and gone not in app._rows and keep_goal in app._rows
            assert not app.orch.log_path(first).exists()
            assert not app.query_one("#board-tools").display
            await pilot.press("ctrl+q")

    asyncio.run(main())
    sent = full.read_text()
    assert sent.rstrip().endswith("<<codex>> exec --sandbox workspace-write --skip-git-repo-check xin chào"), sent


def test_tui_helpers():
    from rich.text import Text

    from ateam.tui import (COMMANDS, flow_chunks, fmt_tokens, help_text, match_commands,
                           suggest_command)

    assert [fmt_tokens(n) for n in (0, 850, 1234, 37500)] == ["0", "850", "1.2k", "37k"]

    assert suggest_command("stup") == "setup"
    assert suggest_command("hlep") == "help"
    assert suggest_command("mer") == "merge"          # tiền tố duy nhất
    assert suggest_command("workflw") == "custom"     # gần với bí danh -> lệnh thật
    assert suggest_command("xyzxyz") is None
    assert [c[0] for c in match_commands("m")] == ["merge", "model", "models"]
    assert "custom" in [c[0] for c in match_commands("us")]  # chứa chữ, xếp sau
    assert len(match_commands("")) == len(COMMANDS)
    # chỉ xuống dòng giữa các mảnh, không cắt đôi "○ antigravity (mặc định)"
    out = flow_chunks([Text(" ○ claude (mặc định) "), Text(" ○ antigravity (mặc định) ")], 30)
    assert out.plain.split("\n") == [" ○ claude (mặc định) ", " ○ antigravity (mặc định) "]
    assert "\n" not in flow_chunks([Text("ab"), Text("cd")], 0).plain
    h = help_text()
    assert "Giao việc:" in h.plain and "/flow" in h.plain


def test_tui_missing_args_show_usage_and_compact(env, project, monkeypatch):
    """Lỗi cũ: gõ /se Enter (chèn "/set ") rồi Enter -> 'Lỗi: not enough values to unpack'.
    Giờ thiếu/sai tham số chỉ hiện cách dùng (kèm gợi ý /setup); /compact tóm tắt ghi chú."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import CommandInput, TeamApp, command_usage

    assert command_usage("set") == ("Dùng: /set <task> effort|model <giá trị> — effort/model riêng cho "
                                    "1 task · hay ý bạn là /setup?")

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        seen: list[tuple[str, str]] = []
        monkeypatch.setattr(app, "notify", lambda msg, severity="information", **kw: seen.append((severity, msg)))
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.5)
            box = app.query_one("#cmd", CommandInput)
            await pilot.press(*"/se", "enter")      # chèn lệnh đang chọn (/set), chờ gõ tham số
            await pilot.pause(0.2)
            assert box.value == "/set "
            await pilot.press("enter")              # Enter lần nữa khi chưa có tham số
            await pilot.pause(0.2)
            assert seen and seen[-1][0] == "warning" and "/setup" in seen[-1][1], seen
            assert not any(m.startswith("Lỗi") for _s, m in seen)
            await pilot.press(*"/set", "enter")     # gõ đủ tên lệnh cần tham số: chỉ chèn dấu cách
            await pilot.pause(0.2)
            assert box.value == "/set "
            box.value = ""
            for bad in ("/set 1", "/assign 1", "/set abc model x", "/retry", "/t"):
                seen.clear()
                await pilot.press(*bad)
                box.close_popup()
                await pilot.press("enter")
                await pilot.pause(0.1)
                assert seen and seen[-1][1].startswith("Dùng: /"), (bad, seen)
                box.value = ""
            await pilot.press(*"/setup", "enter")
            await pilot.pause(0.3)
            assert type(app.screen).__name__ == "SetupScreen"
            await pilot.press("escape")
            await pilot.pause(0.3)
            seen.clear()
            app.run_command("/compact")
            for _ in range(40):
                await pilot.pause(0.1)
                if seen:
                    break
            assert seen[-1] == ("warning", "Chưa có ghi chú hay mục tiêu nào để thu gọn."), seen
            app.run_command("/note API chạy cổng 8080")
            app.run_command("/compact giữ cổng")
            for _ in range(80):
                await pilot.pause(0.1)
                if app.db.recent_notes()[0][0] == "compact":
                    break
            assert [a for a, _ in app.db.recent_notes()] == ["compact"]
            await pilot.press("ctrl+q")

    asyncio.run(main())


def test_tui_vietnamese_input():
    """Bộ gõ tiếng Việt: dấu tổ hợp gộp về NFC, Backspace của bộ gõ xoá trọn chữ cũ."""
    from textual.app import App
    from textual._xterm_parser import XTermParser

    from ateam.tui import CommandInput, TextInput

    assert issubclass(CommandInput, TextInput)

    class Demo(App):
        def compose(self):
            yield TextInput(id="i")

    async def typed(raw: str, burst: bool = False) -> TextInput:
        app = Demo()
        async with app.run_test() as pilot:
            box = app.query_one(TextInput)
            box.focus()
            await pilot.pause()
            # đi qua bộ đọc phím của Textual như byte thật từ terminal (pilot.press làm rơi dấu tổ hợp);
            # burst: gửi liền mọi phím không chờ, như bộ gõ bắn Backspace + chữ mới trong một lượt
            for event in XTermParser().feed(raw):
                app._driver.send_message(event)
                if not burst:
                    await pilot.pause()
            await pilot.pause(0.2)
            return box

    async def main():
        # dấu gửi thành ký tự riêng (Unicode tổ hợp) -> chữ dựng sẵn
        box = await typed("Việt Nam")
        assert box.value == "Việt Nam" and box.cursor_position == len("Việt Nam")
        # bộ gõ kiểu EVKey/OpenKey: xoá chữ cũ bằng Backspace rồi gửi chữ mới
        box = await typed("Vie\x7fê\x7fệt")
        assert box.value == "Việt"
        # như trên nhưng chữ mới ở dạng tổ hợp: một Backspace phải xoá cả chữ lẫn dấu
        box = await typed("Vie\x7fê\x7fệt")
        assert box.value == "Việt"
        # dấu không gộp được vào chữ trước vẫn bị xoá cùng chữ đó
        box = await typed("ax́\x7f")
        assert box.value == "a"
        # OpenKey (byte thật ghi trên Terminal.app): gửi U+202F làm ký tự mồi rồi tính luôn nó vào
        # số Backspace; Textual không chèn U+202F nên Backspace thừa xoá mất chữ thật ("cà", "càoiệt")
        box = await typed("xin cha \x7f\x7fào vie \x7f\x7fê \x7f\x7f\x7fiệt nam")
        assert box.value == "xin chào việt nam" and box.cursor_position == len(box.value)
        # gõ nhanh: Backspace và chữ mới tới dồn một lượt -> vẫn phải xử lý đúng thứ tự
        # (trước đây Backspace đi qua binding nên chạy sau chữ mới: "toi" thành "to")
        box = await typed("toi \x7f\x7f\x7fôi muo \x7f\x7fô \x7f\x7f\x7fuốn", burst=True)
        assert box.value == "tôi muốn"
        box = await typed("toi\x7f\x7fôi\x7f\x7fx", burst=True)
        assert box.value == "tx"

    asyncio.run(main())


def test_tui_plan_approval_bar(env, project, monkeypatch):
    """Kế hoạch nháp hiện khung duyệt ở cả hai tab, focus vào nút duyệt; sửa/bỏ/duyệt từ khung."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from textual.widgets import Button, OptionList

    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import CommandInput, PlanBar, TeamApp

    async def wait_awaiting(app, pilot, gid):
        for _ in range(60):
            await pilot.pause(0.25)
            g = app.db.goal(gid)
            if g and g.status == "awaiting" and app.query_one("#plan", PlanBar).display:
                return
        raise AssertionError("kế hoạch không tới trạng thái chờ duyệt")

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.3)
            bar = app.query_one("#plan", PlanBar)
            box = app.query_one("#cmd", CommandInput)
            assert not bar.display
            gid = app.orch.new_goal("làm a và b")
            await wait_awaiting(app, pilot, gid)
            await pilot.pause(0.3)
            assert bar.goal_id == gid
            assert app.focused is app.query_one("#plan-approve", Button)
            tasks = app.query_one("#plan-tasks", OptionList)
            assert tasks.option_count == 3
            text = str(tasks.get_option_at_index(2).prompt)
            assert "antigravity" in text and "Tổng hợp" in text and "#1" in text
            # vẫn thấy khung khi sang tab Đội
            await pilot.press("ctrl+t")
            await pilot.pause(0.2)
            assert bar.display and bar.region.height > 0
            # chọn 1 task → điền sẵn /edit vào ô nhập
            tasks.focus()
            await pilot.press("down", "enter")
            await pilot.pause(0.2)
            tid = app.db.tasks(goal_id=gid)[1].id
            assert box.value == f"/edit {tid} tạo file b.txt" and app.focused is box
            box.insert_text_at_cursor(" kèm test")
            await pilot.press("enter")
            await pilot.pause(0.2)
            assert app.db.task(tid).prompt == "tạo file b.txt kèm test"
            # nút đổi agent
            app.query_one("#plan-assign", Button).press()
            await pilot.pause(0.2)
            assert box.value.startswith("/assign ")
            box.value = ""
            # F2 (thay Ctrl+G, bị terminal VS Code trên Mac chặn) duyệt & chạy từ ô nhập
            await pilot.press("f2")
            await pilot.pause(0.3)
            assert app.db.goal(gid).status == "running"
            assert not app.db.tasks(goal_id=gid, status="draft")
            assert not bar.display and app.focused is box
            # kế hoạch khác: bỏ bằng nút
            for _ in range(80):
                await pilot.pause(0.25)
                if app.db.goal(gid).status in ("done", "incomplete", "awaiting"):
                    break
            gid2 = app.orch.new_goal("làm tiếp")
            await wait_awaiting(app, pilot, gid2)
            if bar.goal_id != gid2:          # vòng review của mục tiêu đầu có thể tới trước
                app.run_command(f"/drop {bar.goal_id}")
                await pilot.pause(0.3)
            assert bar.goal_id == gid2
            app.query_one("#plan-discard", Button).press()
            await pilot.pause(0.3)
            assert app.db.goal(gid2).status == "cancelled"
            assert all(t.status == "cancelled" for t in app.db.tasks(goal_id=gid2))
            await pilot.press("ctrl+q")

    asyncio.run(main())


def test_tui_team_tab_layout_stays_fixed(env, project, monkeypatch):
    """Tab Đội: cuộn chuột chỉ cuộn log trong từng ô; màn hình, tiêu đề và ô agent đứng yên,
    log tự xuống dòng theo bề rộng ô (không có cuộn ngang)."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from textual import events
    from textual.widget import Widget
    from textual.widgets import Header, RichLog

    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.runner import clean_line
    from ateam.tui import AgentPane, TeamApp

    def scroll(w, cls):
        r = w.region
        w.post_message(cls(w, r.x + 1, r.y + 1, 0, 0, 0, False, False, False,
                           screen_x=r.x + 1, screen_y=r.y + 1))

    async def main(size):
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=size) as pilot:
            await pilot.pause(0.3)
            await pilot.press("ctrl+t")
            await pilot.pause(0.2)
            panes = list(app.query(AgentPane))
            for p in panes:
                for i in range(200):
                    p.body.write('{"prompt": "' + "dòng log rất dài không xuống dòng " * 6 + f'{i}"}}')
            await pilot.pause(0.3)
            before = {p.agent: p.region for p in panes}
            targets = [w for p in panes for w in (p.head, p.body)]
            targets += [app.query_one("#timeline"), app.query_one("#team-grid"), app.screen]
            for w in targets:
                for cls in (events.MouseScrollUp, events.MouseScrollDown,
                            events.MouseScrollLeft, events.MouseScrollRight):
                    for _ in range(5):
                        scroll(w, cls)
                await pilot.pause(0.02)
            await pilot.pause(0.3)
            w, h = size
            assert app.query_one(Header).region.y == 0
            assert {p.agent: p.region for p in panes} == before
            for p in panes:
                r = p.region
                assert r.y >= 1 and r.bottom <= h - 3, (size, p.agent, r)
                log = p.body
                assert log.virtual_size.width <= log.scrollable_content_region.width, (size, log)
                assert log.scroll_x == 0
            for node in app.screen.walk_children(Widget):
                if not isinstance(node, RichLog):
                    assert node.scroll_y == 0 and node.scroll_x == 0, (size, node)
            assert app.screen.scroll_y == 0
            await pilot.press("ctrl+q")

    for size in ((80, 24), (150, 45), (150, 132), (220, 60)):
        asyncio.run(main(size))
    # ký tự điều khiển C1 (NEL, RI…) trong output agent không được lọt ra terminal
    assert clean_line("a\x85b\x8dc\x7fd\x1b[2Je") == "abcde"


def test_tui_diff_screen_shared_mode_and_vscode(env, project, monkeypatch, tmp_path):
    """Chế độ shared: diff gồm cả file chưa track; phím o mở `code --diff cũ mới`; Esc đóng."""
    code_log = tmp_path / "code.log"
    for k, v in dict(env, ATEAM_FAKE_CODE_LOG=str(code_log)).items():
        monkeypatch.setenv(k, v)
    git_init(project)  # base.txt = "base\n"
    (project / "base.txt").write_text("base đã sửa\n")
    (project / "mới.py").write_text("x = 1\n")

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import DiffScreen, TeamApp

    async def main():
        ensure_global_config()
        db = DB(project / ".ateam/team.db")
        tid = db.add_task("codex", "sửa base", "x", status="done")
        app = TeamApp(project, load_config(project), db)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause(0.3)
            app.run_command(f"/diff {tid}")
            for _ in range(20):
                await pilot.pause(0.1)
                if isinstance(app.screen, DiffScreen):
                    break
            scr = app.screen
            assert isinstance(scr, DiffScreen)
            assert {(f.status, f.path) for f in scr.ds.files} == {("M", "base.txt"), ("A", "mới.py")}
            assert not scr.is_split()  # màn hình hẹp (< 120 cột): một cột
            body = str(scr.query_one("#diff-body").render())
            assert "base đã sửa" in body
            await pilot.press("o")
            for _ in range(30):
                await pilot.pause(0.1)
                if code_log.exists():
                    break
            args = code_log.read_text().split()
            assert args[0] == "--diff"
            assert Path(args[1]).read_text() == "base\n" and Path(args[2]).read_text() == "base đã sửa\n"
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert not isinstance(app.screen, DiffScreen)
            await pilot.press("ctrl+q")

    asyncio.run(main())
