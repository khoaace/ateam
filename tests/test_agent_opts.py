"""Chọn nhanh model / effort ngay trên ô agent (tab Đội): bấm chip là đổi, danh sách effort theo model đang dùng."""

from __future__ import annotations

import asyncio
import importlib


def _load(env, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import ensure_global_config, load_config
    ensure_global_config()
    return load_config


def test_choice_line_chips_are_clickable():
    from rich.console import Console

    from ateam.tui import choice_line

    def actions(t):
        return [s.style.meta["@click"] for s in t.render(Console()) if s.style and s.style.meta.get("@click")]
    assert "app.set_agent_opt('codex', 'effort', 'low')" in actions(choice_line("effort", ["low", "high"], "high",
                                                                               agent="codex"))
    assert "app.pick_agent_opt('x', 'model')" in actions(choice_line("model", ["a", "b", "c"], "a", limit=2, agent="x"))
    assert actions(choice_line("effort", ["low"], "low")) == []  # không có agent: chỉ để xem


def test_tui_click_effort_chip(env, project, monkeypatch):
    load_config = _load(env, monkeypatch)
    from ateam.db import DB
    from ateam.tui import TeamApp

    async def main():
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(160, 48)) as pilot:
            app.query_one("#tabs").active = "tab-team"
            await pilot.pause(0.3)
            pane = app.pane("codex")
            efforts = app.cfg.agents["codex"].efforts_for()
            assert "high" in efforts
            # dòng 3 của tiêu đề ô: "effort: low medium high …" (padding trái 1)
            x = 1 + len("effort: ") + sum(len(e) + 1 for e in efforts[:efforts.index("high")]) + 1
            await pilot.click(pane.head, offset=(x, 2))
            await pilot.pause(0.2)
            assert app.cfg.agents["codex"].effort == "high"
            assert not app.screen_stack[1:]  # không mở bảng chọn
            await pilot.press("ctrl+q")
    asyncio.run(main())


def test_web_agent_option_returns_efforts_of_model(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    load_config = _load(env, monkeypatch)
    from ateam.db import DB
    from ateam.web import WebApp
    wa = WebApp(project, load_config(project), DB(project / ".ateam/team.db"), 8125)
    wa.cfg.agents["codex"].model_efforts = {"gpt-6-luna": ["low", "medium", "high", "xhigh", "max"]}
    r = asyncio.run(wa.handle({"op": "agent_option", "agent": "codex", "key": "model", "value": "gpt-6-luna"}))
    assert r[2]["agent"]["efforts"][-1] == "max"
    r = asyncio.run(wa.handle({"op": "agent_option", "agent": "codex", "key": "effort", "value": "ultra"}))
    assert r[2]["agent"]["effort"] == "max"  # luna không có ultra: mức gần nhất
    a = next(x for x in wa.snapshot()["agents"] if x["name"] == "codex")
    assert a["efforts"] == ["low", "medium", "high", "xhigh", "max"] and a["model"] == "gpt-6-luna"
    assert "gpt-6-luna" in a["models"]
