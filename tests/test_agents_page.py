"""Trang 🤖 Agents (thay tab Đội) và 🔀 Workflows (thay tab Tuỳ chỉnh): agent tuỳ chỉnh ở Agents, workflow ở
Workflows; thứ tự sidebar web khớp thứ tự tab TUI (Alt+số giống nhau)."""

from __future__ import annotations

import asyncio
import importlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_web_sidebar_order_matches_tui_tabs():
    from ateam.tui import TeamApp
    html = (ROOT / "ateam/webui/index.html").read_text(encoding="utf-8")
    nav = html[html.index('id="nav"'):html.index("</nav>")]
    views = re.findall(r'data-view="(\w+)"', nav)
    web_to_tui = {"board": "board", "team": "team", "custom": "custom", "code": "code", "git": "git",
                  "term": "term", "grid": "grid", "todo": "todo", "notes": "notes", "dash": "dash"}
    assert ["tab-" + web_to_tui[v] for v in views] == TeamApp.TAB_ORDER
    js = (ROOT / "ateam/webui/app.js").read_text(encoding="utf-8")
    assert "agent-card" not in js and "\"agent-chat\"" in js  # danh sách gọn, chat qua popup


def test_tui_agents_and_workflows_tabs(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    xdg = Path(env["XDG_CONFIG_HOME"]) / "ateam"
    xdg.mkdir(parents=True, exist_ok=True)
    (xdg / "custom.toml").write_text('[agents.mine]\ncommand = ["mycli", "{prompt}"]\nrole = "Việc vặt"\n')
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import CustomPanel, TeamApp

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(160, 48)) as pilot:
            app.query_one("#tabs").active = "tab-team"
            await pilot.pause(0.5)
            agents = app.query_one("#agents-custom", CustomPanel)
            assert agents.query("#custom-add-agent") and not agents.query("#custom-add-flow")
            assert any(a == "edit-agent" and n == "mine" for a, n in agents.ids.values())
            assert "[tuỳ chỉnh]" in str(app.pane("mine").head.render())
            # danh sách: chỉ phần đầu; bấm vào agent mở log + ô chat của nó
            assert not app.pane("mine").body.display
            await pilot.click(app.pane("codex").head, offset=(2, 0))
            await pilot.pause(0.2)
            assert app.focus_agent == "codex" and app.pane("codex").body.region.height > 10
            app.set_focus_agent(None)
            app.query_one("#tabs").active = "tab-custom"
            await pilot.pause(0.3)
            flows = app.query_one("#custom-tab", CustomPanel)
            assert flows.query("#custom-add-flow") and not flows.query("#custom-add-agent")
            app.run_command("/agent-moi")
            await pilot.pause(0.1)
            assert app.query_one("#tabs").active == "tab-team"
            await pilot.press("ctrl+q")
    asyncio.run(main())
