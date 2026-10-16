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
            assert len(app.query(AgentPane)) == 5
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
                if "xai/grok-5-fast" in app.cfg.agents["opencode"].models:
                    break
                await pilot.pause(0.25)
            assert "xai/grok-5-fast" in app.cfg.agents["opencode"].models
            assert "grok-4.7-build-fast" in app.cfg.agents["grok"].models  # grok models (Grok Build)
            app.run_command("/models grok")
            await pilot.press("ctrl+q")

    asyncio.run(main())


def test_tui_setup_screen(env, project, monkeypatch):
    """Wizard thiết lập: chọn CLI → kiểu làm việc → mức → vai trò (CLI · model · effort, cùng CLI 2 model
    thành 2 agent) → an toàn & duyệt code → lệnh kiểm tra → xem lại & lưu. Esc = bước trước; Esc ở dropdown
    chỉ đóng dropdown; mở lại /setup giữ đội hiện tại."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from textual.widgets import Input, OptionList, Select, SelectionList

    from ateam.config import ensure_global_config, load_config, load_custom, load_project_state, needs_setup
    from ateam.db import DB
    from ateam.tui import RESET, AgentPane, OnboardScreen, TeamApp

    async def wait(pilot, cond, n=60):
        for _ in range(n):
            if cond():
                return True
            await pilot.pause(0.1)
        return cond()

    async def choose(pilot, scr, oid, key):
        ol = scr.query_one(f"#{oid}", OptionList)
        ol.focus()
        ol.highlighted = next(i for i in range(ol.option_count) if ol.get_option_at_index(i).id == key)
        await pilot.press("enter")
        await pilot.pause(0.3)

    def step(scr):
        return scr.STEPS[scr.step][0]

    async def main():
        ensure_global_config()
        assert needs_setup()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"), setup=True)
        async with app.run_test(size=(160, 48)) as pilot:
            assert await wait(pilot, lambda: isinstance(app.screen, OnboardScreen))
            scr = app.screen
            await pilot.pause(0.3)
            # 1. CLI: bỏ OpenCode
            sl = scr.query_one("#ob-cli", SelectionList)
            assert set(sl.selected) == {"claude", "codex", "agy", "grok", "opencode"}
            sl.deselect("opencode")
            await pilot.click("#ob-next")
            await pilot.pause(0.3)
            # 2. kiểu làm việc, 3. mức: Enter chọn và sang bước kế
            assert step(scr) == "style"
            await choose(pilot, scr, "ob-style", "flow")
            assert step(scr) == "tier"
            await choose(pilot, scr, "ob-tier", "max")
            assert step(scr) == "roles"
            assert await wait(pilot, lambda: not scr.discovering)
            await pilot.pause(0.3)
            # model hỏi được từ CLI giả lập có sẵn trong bảng chọn; OpenCode đã bỏ thì không có trong CLI
            opts = lambda sid: [v for _, v in scr.query_one(sid, Select)._options]
            assert "opencode" not in opts("#ob-cli-lead") and RESET not in opts("#ob-cli-lead")
            assert "gemini-3-pro" in opts("#ob-model-ui")
            assert "grok-4.7-build-fast" in opts("#ob-model-test")
            assert scr.query_one("#ob-model-lead", Select).value == "opus"  # mức Tối đa, trưởng nhóm
            # Esc ở dropdown đang mở chỉ đóng dropdown, không lùi bước / đóng wizard
            sel = scr.query_one("#ob-cli-code", Select)
            sel.focus()
            await pilot.press("enter")
            await pilot.pause(0.2)
            assert sel.expanded
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert not sel.expanded and app.screen is scr and step(scr) == "roles"
            # trưởng nhóm = codex (model gpt-6-luna); review = claude sonnet (khác model của claude ở UI)
            scr.query_one("#ob-cli-lead", Select).value = "codex"
            await pilot.pause(0.3)
            assert "gpt-6-luna" in opts("#ob-model-lead")  # từ `codex debug models`
            scr.query_one("#ob-model-lead", Select).value = "gpt-6-luna"
            scr.query_one("#ob-cli-review", Select).value = "claude"
            scr.query_one("#ob-cli-ui", Select).value = "claude"
            await pilot.pause(0.3)
            scr.query_one("#ob-model-review", Select).value = "sonnet"
            scr.query_one("#ob-model-ui", Select).value = "opus"
            scr.query_one("#ob-cli-research", Select).value = RESET  # không dùng
            await pilot.pause(0.2)
            await pilot.click("#ob-next")
            await pilot.pause(0.3)
            # 5. an toàn: toàn quyền + mỗi task 1 nhánh, duyệt diff
            assert step(scr) == "safety"
            await choose(pilot, scr, "ob-access", "full")
            await choose(pilot, scr, "ob-apply", "worktree-review")
            # 6. lệnh kiểm tra: gõ tay
            assert step(scr) == "verify"
            scr.query_one("#ob-verify-input", Input).value = "pytest -q"
            await pilot.click("#ob-next")
            await pilot.pause(0.3)
            assert step(scr) == "review"
            text = str(scr.query_one("#ob-body").query("Static").first().render())
            assert "claude-review" in text or "claude-ui" in text
            await pilot.press("ctrl+s")
            assert await wait(pilot, lambda: not isinstance(app.screen, OnboardScreen))
            await pilot.pause(0.3)
            c = app.cfg
            assert c.lead == "codex" and c.agents["codex"].model == "gpt-6-luna"
            assert "--sandbox danger-full-access" in " ".join(c.agents["codex"].argv("x"))
            extra = [n for n in c.agents if n.startswith("claude-")]
            assert len(extra) == 1 and c.agents[extra[0]].model in ("sonnet", "opus")
            assert not c.agents["opencode"].enabled and not c.agents["antigravity"].enabled
            # codex vừa làm trưởng nhóm (gpt-6-luna) vừa code chính (model khác) -> thêm codex-code
            assert c.agents["codex-code"].binary == "codex" and c.agents["codex-code"].model != "gpt-6-luna"
            assert {p.agent for p in app.query(AgentPane)} == {"codex", "codex-code", "claude", "grok", extra[0]}
            assert c.default_workflow == "tinh-nang" and c.isolation == "worktree" and c.merge == "review"
            assert c.verify.command == "pytest -q" and c.approve_plan
            assert "workflow 'tinh-nang'" in app.query_one("#cmd").placeholder
            # gõ mục tiêu -> chạy theo workflow mặc định
            box = app.query_one("#cmd")
            box.value = "đăng nhập"
            await pilot.press("enter")
            await pilot.pause(0.3)
            g = app.db.goals()[-1]
            assert g.workflow == "tinh-nang" and app.db.tasks(goal_id=g.id)[0].title == "Thiết kế"
            # mở lại /setup: giữ đội hiện tại; Esc lùi bước, ở bước 1 cần Esc 2 lần mới đóng
            app.run_command("/setup")
            assert await wait(pilot, lambda: isinstance(app.screen, OnboardScreen))
            scr = app.screen
            await pilot.pause(0.3)
            for _ in range(3):
                await pilot.click("#ob-next")
                await pilot.pause(0.3)
            assert step(scr) == "roles"
            assert scr.query_one("#ob-cli-lead", Select).value == "codex"
            assert scr.query_one("#ob-model-lead", Select).value == "gpt-6-luna"
            app.set_focus(None)
            for _ in range(3):
                await pilot.press("escape")
                await pilot.pause(0.3)
            assert step(scr) == "cli" and app.screen is scr
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert app.screen is scr  # Esc đầu ở bước 1 chỉ nhắc
            await pilot.press("escape")
            await pilot.pause(0.3)
            assert not isinstance(app.screen, OnboardScreen) and app.cfg.lead == "codex"
            await pilot.press("ctrl+q")

    asyncio.run(main())
    assert not needs_setup()
    assert load_custom()["agents"][[n for n in load_custom()["agents"]][0]]["wizard"] is True
    assert load_project_state(project)["verify_command"] == "pytest -q"


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
    from ateam.tui import (AgentEditScreen, AgentPane, AgentQuickScreen, CustomScreen, OnboardScreen, TeamApp,
                           WorkflowEditScreen)

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
            # form đơn giản: chọn nhà cung cấp, model, effort, quyền — cờ CLI lấy từ mẫu
            await pilot.click("#custom-add-agent")
            assert await wait_for(pilot, lambda: isinstance(app.screen, AgentQuickScreen))
            q = app.screen
            q.query_one("#q-provider", Select).value = "agy"
            await pilot.pause(0.2)
            assert q.query_one("#q-name", Input).value == "antigravity-2"
            assert [v for _, v in q.query_one("#q-effort", Select)._options][:2] == ["low", "medium"]
            q.query_one("#q-effort", Select).value = "high"
            q.query_one("#q-access", Select).value = "full"
            await pilot.pause(0.2)
            preview = str(q.query_one("#quick-preview").render())
            assert "agy --dangerously-skip-permissions" in preview and "accept-edits" not in preview, preview
            await pilot.press("ctrl+s")
            assert await wait_for(pilot, lambda: isinstance(app.screen, CustomScreen))
            saved = load_custom()["agents"]["antigravity-2"]
            assert saved["command"][0] == "agy" and saved["pty"] and saved["full_access"] is True
            assert saved["effort"] == "high" and "model" not in saved
            # "Nâng cao…" mở form đầy đủ cho CLI khác
            await pilot.click("#custom-add-agent")
            assert await wait_for(pilot, lambda: isinstance(app.screen, AgentQuickScreen))
            await pilot.click("#q-advanced")
            assert await wait_for(pilot, lambda: isinstance(app.screen, AgentEditScreen))
            ed = app.screen
            ed.query_one("#ag-template", Select).value = "trống"
            await pilot.pause(0.2)
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
            assert await wait_for(pilot, lambda: wf.query_one("#wf-name", Input).value == "review-code")
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
            assert app.cfg.custom_agents == {"mine", "antigravity-2"}
            assert app.cfg.agents["antigravity-2"].full_access
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

            # wizard thiết lập: bước Xem lại liệt kê agent tuỳ chỉnh được giữ, có nút mở /custom; xoá agent
            # tuỳ chỉnh (bấm 2 lần) -> quay lại wizard thấy ngay
            app.open_setup()
            assert await wait_for(pilot, lambda: isinstance(app.screen, OnboardScreen), 200)
            wiz = app.screen
            await wiz.show_step(len(wiz.STEPS) - 1)
            await pilot.pause(0.3)
            assert "mine" in str(wiz.query_one("#ob-body").query("Static").first().render())
            app.save_screenshot(str(tmp_path / "setup.svg"))
            await pilot.click("#ob-custom")
            assert await wait_for(pilot, lambda: isinstance(app.screen, CustomScreen))
            await pilot.pause(0.3)
            del_mine = next(bid for bid, act in app.screen.ids.items() if act == ("del-agent", "mine"))
            await pilot.click("#" + del_mine)
            await pilot.pause(0.2)
            assert "mine" in load_custom().get("agents", {})
            await pilot.click("#" + del_mine)
            await pilot.pause(0.3)
            assert "mine" not in load_custom().get("agents", {})
            await pilot.press("escape")
            assert await wait_for(pilot, lambda: app.screen is wiz)
            await pilot.pause(0.3)
            assert "mine" not in str(wiz.query_one("#ob-body").query("Static").first().render())
            assert "mine" not in app.cfg.agents
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
            assert ids == ["claude", "codex", "antigravity", "grok", "opencode"]
            assert "Viết code" in str(popup.get_option_at_index(1).prompt)  # vai trò
            await pilot.press("c", "o")
            await pilot.pause(0.1)
            # bắt đầu bằng "co" đứng trước, chứa "co" sau
            assert [popup.get_option_at_index(i).id for i in range(popup.option_count)] == ["codex", "opencode"]
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
            assert type(app.screen).__name__ == "OnboardScreen"
            await pilot.press("escape", "escape")  # bước 1: Esc lần 2 mới thoát
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
            # DiffScreen vẽ diff ở lượt vẽ kế tiếp (call_after_refresh): máy chậm (CI macOS) cần chờ
            for _ in range(30):
                body = str(scr.query_one("#diff-body").render())
                if body:
                    break
                await pilot.pause(0.1)
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


def test_tui_usage_and_update_commands(env, project, monkeypatch):
    """/usage in thêm hạn mức do từng CLI báo; /update có bản mới thì chạy lệnh cài và nhắc mở lại app."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from textual.widgets import RichLog

    from ateam import update
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import TeamApp

    async def newer():
        return "99.0.0"
    monkeypatch.setattr(update, "latest_version", newer)
    monkeypatch.setattr(update, "editable_source", lambda: None)
    monkeypatch.setattr(update, "UPDATE_CMD", ["bash", "-c", "echo '→ Tải ateam (main)'"])

    def log_text(app) -> str:
        return "\n".join("".join(seg.text for seg in strip) for strip in app.query_one("#log", RichLog).lines)

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.3)
            app.run_command("/usage")
            for _ in range(60):
                await pilot.pause(0.25)
                if all(f"📊 {n}" in log_text(app) for n in ("claude", "codex", "antigravity", "opencode")):
                    break
            text = log_text(app)
            assert "Hôm nay:" in text and "Current session: 41% used" in text, text
            assert "Weekly Limit Remaining" in text and "Chưa có phiên codex" in text
            app.run_command("/update")
            for _ in range(40):
                await pilot.pause(0.25)
                if "Đã cập nhật lên 99.0.0" in (project / ".ateam/logs/system.log").read_text():
                    break
            sys_log = (project / ".ateam/logs/system.log").read_text()
            assert "→ Tải ateam (main)" in sys_log and "Đã cập nhật lên 99.0.0" in sys_log
            assert "mở lại" in sys_log
            await pilot.press("ctrl+q")

    asyncio.run(main())


def test_tui_terminal_tab(env, project, monkeypatch):
    """!lệnh chạy trong tab Terminal: gợi ý script, output trực tiếp, dừng / lỗi / chạy lại / xoá,
    thoát app dừng mọi lệnh đang chạy."""
    import json
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("SHELL", "/bin/sh")
    git_init(project)
    (project / "package.json").write_text(json.dumps({"scripts": {"dev": "echo dev"}}))
    (project / "yarn.lock").write_text("")

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from textual.widgets import OptionList, RichLog, TabbedContent

    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import CommandInput, MentionList, TeamApp

    def job_log(app) -> str:
        return "\n".join("".join(seg.text for seg in strip) for strip in app.query_one("#job-log", RichLog).lines)

    async def wait(pilot, cond, n=60):
        for _ in range(n):
            await pilot.pause(0.1)
            if cond():
                return True
        return False

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(150, 40)) as pilot:
            await pilot.pause(0.3)
            box = app.query_one("#cmd", CommandInput)
            popup = app.query_one("#mention", MentionList)
            await pilot.press("!")
            await pilot.pause(0.2)
            assert popup.display and popup.get_option_at_index(0).id == "yarn dev"
            await pilot.press("escape")
            box.value = ""
            # gõ đúng lệnh trùng một phần với gợi ý: Enter chạy lệnh đã gõ, không chạy gợi ý
            await pilot.press(*"!yarn")
            await pilot.pause(0.1)
            assert popup.display
            await pilot.press("tab")                     # Tab: điền gợi ý để sửa
            assert box.value == "!yarn dev" and not popup.display
            box.value = ""
            # lệnh chạy lâu: sang tab Terminal, thấy output, bắt port
            box.value = "!echo 'xin chào'; echo 'Local: http://localhost:4321'; sleep 30"
            await pilot.press("enter")
            assert await wait(pilot, lambda: "xin chào" in job_log(app))
            assert app.query_one("#tabs", TabbedContent).active == "tab-term"
            job = app.selected_job()
            assert job.alive and job.ports == [4321]
            # dòng trạng thái ở tab Bảng việc (tab ẩn không vẽ lại — vẽ ngay khi chuyển sang)
            app.query_one("#tabs", TabbedContent).active = "tab-board"
            assert await wait(pilot, lambda: "1 lệnh đang chạy (:4321)" in str(app.query_one("#agents").render()))
            app.query_one("#tabs", TabbedContent).active = "tab-term"
            app.run_command("/stop")
            assert await wait(pilot, lambda: job.rc is not None)
            assert job.status == "stopped"
            # lệnh lỗi
            app.run_command("/sh exit 3")
            assert await wait(pilot, lambda: app.selected_job().rc is not None)
            failed = app.selected_job()
            await pilot.pause(0.2)
            head = str(app.query_one("#job-head").render())
            assert (failed.status, failed.rc) == ("failed", 3) and "lỗi (mã 3)" in head, (failed.status, failed.rc, head)
            # chạy lại -> job mới; xoá job đã xong
            await pilot.click("#job-restart")
            assert await wait(pilot, lambda: len(app.shell.jobs) == 3 and app.selected_job().rc is not None)
            removed = app.selected_job()
            await pilot.click("#job-remove")
            assert await wait(pilot, lambda: removed.id not in app.shell.jobs)
            assert await wait(pilot, lambda: app.query_one("#jobs", OptionList).option_count == 2)
            # thoát app: dừng mọi lệnh đang chạy
            box.focus()  # vừa bấm nút Xoá: focus đang ở nút
            box.value = "!sleep 30"
            await pilot.press("enter")
            assert await wait(pilot, lambda: any(j.cmd == "sleep 30" and j.alive for j in app.shell.jobs.values()))
            sleeper = next(j for j in app.shell.jobs.values() if j.cmd == "sleep 30")
            await pilot.press("ctrl+q")
        return sleeper

    sleeper = asyncio.run(main())
    assert sleeper.status == "stopped"
    assert (project / ".ateam" / "logs" / "sh1.log").read_text().startswith("$ echo 'xin chào'")


def test_tui_full_access_from_custom_survives_setup(env, project, monkeypatch):
    """Lỗi người dùng gặp (0.5.6): bật Toàn quyền cho agent tuỳ chỉnh ở /custom (mở từ /setup) rồi lưu
    /setup thì bị đè về "sửa file". Wizard chỉ đổi agent có sẵn và agent nó tự tạo — agent tuỳ chỉnh của
    người dùng giữ nguyên quyền, kể cả khi wizard chọn "Chỉ sửa file"."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from textual.widgets import Select

    from ateam.config import (ensure_global_config, load_config, load_custom, load_state, save_custom_item,
                              save_state)
    from ateam.db import DB
    from ateam.tui import AgentQuickScreen, CustomScreen, OnboardScreen, TeamApp

    async def wait_for(pilot, cond, n=80):
        for _ in range(n):
            await pilot.pause(0.1)
            if cond():
                return True
        return False

    async def main():
        ensure_global_config()
        save_custom_item("agents", "gehihi", {"command": ["agy", "--mode", "accept-edits", "--print-timeout", "0",
                                                          "-p", "{prompt}"], "pty": True, "role": "Việc nhỏ"})
        st = load_state()
        st.setdefault("agents", {})["gehihi"] = {"full_access": False, "role": "Lint, build"}
        st["onboarded"] = 1
        save_state(st)
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(160, 48)) as pilot:
            await pilot.pause(0.3)
            app.open_setup()
            assert await wait_for(pilot, lambda: isinstance(app.screen, OnboardScreen))
            wiz = app.screen
            await wiz.show_step(len(wiz.STEPS) - 1)
            await pilot.pause(0.2)
            await pilot.click("#ob-custom")
            assert await wait_for(pilot, lambda: isinstance(app.screen, CustomScreen))
            await pilot.pause(0.3)
            edit = next(bid for bid, act in app.screen.ids.items() if act == ("edit-agent", "gehihi"))
            await pilot.click("#" + edit)
            assert await wait_for(pilot, lambda: isinstance(app.screen, AgentQuickScreen))
            app.screen.query_one("#q-access", Select).value = "full"
            await pilot.press("ctrl+s")
            assert await wait_for(pilot, lambda: isinstance(app.screen, CustomScreen))
            assert "full_access" not in load_state()["agents"].get("gehihi", {})   # state cũ đã bỏ
            await pilot.press("escape")
            assert await wait_for(pilot, lambda: app.screen is wiz)
            assert wiz.access == "safe"
            await pilot.press("ctrl+s")
            assert await wait_for(pilot, lambda: not isinstance(app.screen, OnboardScreen))
            assert app.cfg.agents["gehihi"].full_access
            assert "--dangerously-skip-permissions" in app.cfg.agents["gehihi"].argv("x")
            assert not app.cfg.agents["claude"].full_access
            await pilot.press("ctrl+q")

    asyncio.run(main())
    assert load_custom()["agents"]["gehihi"]["full_access"] is True
    assert load_state()["agents"].get("gehihi", {}).get("full_access") is not False
    assert load_config(project).agents["gehihi"].full_access


def test_tui_continue_goal_and_thread(env, project, monkeypatch, tmp_path):
    """Tiếp tục: /continue có gợi ý + dòng giải thích, F6 trên task, nút ↪ Tiếp tục ở khung mục tiêu."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from rich.cells import cell_len

    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import CommandInput, MentionList, TeamApp

    db = DB(project / ".ateam/team.db")
    gid = db.add_goal("Thêm trang đăng nhập")
    db.add_task("codex", "Tạo form", "tạo form", goal_id=gid, status="done")
    db.update_goal(gid, status="done", summary="Đã có form đăng nhập")
    alone = db.add_task("codex", "viết hàm cộng", "viết hàm cộng", status="done")

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), db)
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.5)
            box = app.query_one("#cmd", CommandInput)
            popup = app.query_one("#mention", MentionList)
            hint = app.query_one("#continue-hint")
            # gõ /continue -> danh sách mục tiêu & thread đã xong
            await pilot.press(*"/continue ")
            await pilot.pause(0.2)
            ids = [popup.get_option_at_index(i).id for i in range(popup.option_count)]
            assert popup.display and ids == ["m1", f"t{alone}"], ids
            await pilot.press("tab")
            await pilot.pause(0.2)
            assert box.value == "/continue m1 " and not popup.display
            assert hint.display and "Thêm trang đăng nhập" in str(hint.render())
            await pilot.press("escape")  # Esc huỷ
            await pilot.pause(0.1)
            assert box.value == "" and not hint.display

            # F6 trên task /task -> hỏi tiếp thread đó
            app.show_task(alone)
            await pilot.press("f6")
            await pilot.pause(0.2)
            assert box.value == f"/continue t{alone} " and "Hỏi tiếp codex" in str(hint.render())
            box.value = ""

            # nút ↪ Tiếp tục trong khung mục tiêu
            goals = app.query_one("#goals")
            lines = goals.render().plain.splitlines()
            y = next(i for i, ln in enumerate(lines) if "↪ Tiếp tục" in ln)
            x = cell_len(lines[y][:lines[y].index("↪ Tiếp tục")]) + 2
            await pilot.click("#goals", offset=(x, y))
            await pilot.pause(0.2)
            assert box.value == "/continue m1 "

            # gửi -> mục tiêu mở lại, trưởng nhóm lập kế hoạch tiếp
            await pilot.press(*"thêm quên mật khẩu", "enter")
            for _ in range(40):
                await pilot.pause(0.25)
                if app.db.goal(gid).status not in ("planning",):
                    break
            g = app.db.goal(gid)
            assert g.followups == ["thêm quên mật khẩu"] and g.status in ("awaiting", "running", "done")
            assert any(t.source == "followup" for t in app.db.tasks(goal_id=gid))
            await pilot.press("ctrl+q")

    asyncio.run(main())


def test_tui_log_folds_echoed_prompt_and_clear_button(env, project, monkeypatch):
    """Prompt ateam bị CLI in lại (opencode "File not found: <prompt>") được gập; nút 🗑 Xoá log."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from ateam import prompts as P
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import LogStyler, TeamApp, styled_lines

    cfg = load_config(project)
    prompt = P.task_prompt(cfg, agent="grok", task_id=1, title="t", prompt="làm X", goal="G", deps=[],
                           notes="", cwd="/x", can_delegate=True)
    raw = "$ grok · task · /x\nError: File not found: " + prompt + "\nsau prompt"
    lines = [t.plain for t in styled_lines(raw, LogStyler())]
    assert lines[1].startswith("Error: File not found:") and "đã ẩn" in lines[1]
    styled = [t for t in styled_lines(raw, LogStyler())][1]
    assert any("red" in str(sp.style) and sp.start == 0 for sp in styled.spans)  # lỗi vẫn màu đỏ
    assert lines[2:] == ["sau prompt"], lines  # luật DELEGATE/NOTE trong prompt không lọt ra

    async def main():
        ensure_global_config()
        db = DB(project / ".ateam/team.db")
        tid = db.add_task("grok", "t", "p", status="failed")
        app = TeamApp(project, load_config(project), db)
        log_file = app.orch.log_path(tid)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text("dòng cũ 1\ndòng cũ 2\n")
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause(0.3)
            app.show_task(tid)
            await pilot.pause(0.1)
            log = app.query_one("#log")
            assert any("dòng cũ 1" in ln.text for ln in log.lines)
            await pilot.click("#log-clear")
            await pilot.pause(0.2)
            assert not any("dòng cũ" in ln.text for ln in log.lines)
            with open(log_file, "a") as f:
                f.write("dòng mới\n")
            app.show_task(tid)  # chọn lại task: vẫn chỉ hiện phần sau khi xoá
            await pilot.pause(0.1)
            text = [ln.text for ln in log.lines]
            assert any("dòng mới" in t for t in text) and not any("dòng cũ" in t for t in text)
            assert log_file.read_text().startswith("dòng cũ 1")  # file trên đĩa giữ nguyên
            await pilot.press("ctrl+q")

    asyncio.run(main())


def test_tui_popup_close_narrow_layout_and_log_reflow(env, project, monkeypatch):
    """Popup có nút ✕; form đang sửa dở cần Esc 2 lần; terminal hẹp thì bảng việc và log xếp dọc; đổi bề rộng
    thì log vẽ lại (không còn mỗi chữ một dòng); log lớn chỉ đọc phần cuối."""
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    import importlib

    import ateam.config
    importlib.reload(ateam.config)
    from textual.widgets import Input

    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import LOG_SHOW_LINES, AgentQuickScreen, CustomScreen, HelpScreen, TeamApp

    async def main():
        ensure_global_config()
        db = DB(project / ".ateam/team.db")
        tid = db.add_task("codex", "t", "p", status="done")
        app = TeamApp(project, load_config(project), db)
        big = app.orch.log_path(tid)
        big.parent.mkdir(parents=True, exist_ok=True)
        big.write_text("".join(f"dòng {i} " + "chữ " * 70 + "\n" for i in range(20000)))  # ~6MB
        async with app.run_test(size=(70, 40)) as pilot:
            await pilot.pause(0.3)
            board = app.query_one("#board")
            assert board.has_class("narrow")
            log = app.query_one("#log")
            assert log.size.width >= 60  # xếp dọc: log rộng gần hết màn hình
            app.show_task(tid)
            await pilot.pause(0.2)
            text = [ln.text for ln in log.lines]
            assert any("dòng 19999 " in t for t in text) and not any("dòng 0 " in t for t in text)
            assert len(log._items) <= LOG_SHOW_LINES + 1  # chỉ phần cuối
            # ghi khi cửa sổ hẹp, rồi kéo rộng: dòng được vẽ lại theo bề rộng mới
            narrow_lines, narrow_w = len(log.lines), max(s.cell_length for s in log.lines)
            assert narrow_w <= log.scrollable_content_region.width
            await pilot.resize_terminal(200, 40)
            await pilot.pause(0.5)
            assert not board.has_class("narrow")
            assert max(s.cell_length for s in log.lines) > narrow_w and len(log.lines) < narrow_lines

            # ✕ đóng popup chỉ xem
            app.action_help()
            await pilot.pause(0.2)
            assert isinstance(app.screen, HelpScreen)
            await pilot.click(".m-close")
            await pilot.pause(0.2)
            assert not isinstance(app.screen, HelpScreen)
            # form sửa dở: Esc lần 1 chỉ nhắc, lần 2 mới đóng; popup lồng nhau Esc chỉ đóng lớp trên
            app.open_custom()
            await pilot.pause(0.3)
            await pilot.click("#custom-add-agent")
            await pilot.pause(0.4)
            assert isinstance(app.screen, AgentQuickScreen)
            app.screen.query_one("#q-role", Input).value = "vai trò mới"
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert isinstance(app.screen, AgentQuickScreen)
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert isinstance(app.screen, CustomScreen)
            await pilot.press("escape")
            await pilot.pause(0.2)
            assert not isinstance(app.screen, CustomScreen)
            await pilot.press("ctrl+q")

    asyncio.run(main())
