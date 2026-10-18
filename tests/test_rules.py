"""Rule của dự án (/rules): lưu ngoài repo, bật/tắt, chỉ cho vài agent / vai trò; ateam đặt rule ở đầu mỗi prompt
(task, chat, lượt trưởng nhóm), lượt tiếp tục phiên chỉ gửi lại khi bộ rule đổi; popup TUI và web."""

from __future__ import annotations

import asyncio
import importlib

from test_editor import _app


def _orch(env, project, monkeypatch):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(importlib.import_module("ateam.config"))
    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.orchestrator import Orchestrator
    ensure_global_config()
    return Orchestrator(project, load_config(project), DB(project / ".ateam/team.db"))


def test_store_outside_repo_and_ops(env, project, monkeypatch):
    _orch(env, project, monkeypatch)
    from ateam import rules
    assert project not in rules.path_for(project).parents
    assert rules.apply(project, "add", {"text": "  "})  # rỗng: không thêm
    assert rules.apply(project, "add", {"title": "Tiếng Việt", "text": "Trả lời bằng tiếng Việt."}) == ""
    assert rules.apply(project, "add", {"text": "Viết test trước.", "targets": ["agent:codex", "role:test", "rác"]}) == ""
    a, b = rules.load(project)
    assert b["targets"] == ["agent:codex", "role:test"] and a["enabled"] and rules.name_of(b) == "Viết test trước."
    assert rules.apply(project, "toggle", {"id": a["id"]}) == "" and not rules.load(project)[0]["enabled"]
    assert rules.apply(project, "move", {"id": b["id"], "by": -1}) == ""
    assert [r["id"] for r in rules.load(project)] == [b["id"], a["id"]]
    assert rules.apply(project, "update", {"id": b["id"], "text": "Viết test.", "targets": []}) == ""
    assert rules.load(project)[0]["text"] == "Viết test." and rules.targets_label(rules.load(project)[0]) == "mọi agent"
    assert rules.apply(project, "delete", {"id": 999})
    assert rules.apply(project, "delete", {"id": a["id"]}) == "" and len(rules.load(project)) == 1
    # chọn người nhận
    r = {"enabled": True, "targets": ["agent:codex", "role:lead"]}
    assert rules.applies(r, "codex", "code", False) and rules.applies(r, "claude", "code", True)
    assert not rules.applies(r, "agy", "ui", False) and not rules.applies(dict(r, enabled=False), "codex", "", False)
    assert rules.applies({"targets": []}, "bat-ky", "", False)


def test_native_files(project):
    from ateam import rules
    (project / "AGENTS.md").write_text("x")
    (project / ".agents/rules").mkdir(parents=True)
    (project / ".agents/rules/style.md").write_text("x")
    got = {f["path"]: f["readers"] for f in rules.native_files(project)}
    assert set(got) == {"AGENTS.md", ".agents/rules/style.md"} and "codex" in got["AGENTS.md"]


def test_rules_go_with_prompts(env, project, monkeypatch, tmp_path):
    o = _orch(env, project, monkeypatch)
    from ateam import rules
    rules.apply(project, "add", {"text": "RULE-ALL"})
    rules.apply(project, "add", {"text": "RULE-CODEX", "targets": ["agent:codex"]})
    rules.apply(project, "add", {"text": "RULE-LEAD", "targets": ["role:lead"]})
    rules.apply(project, "add", {"text": "RULE-OFF", "enabled": False})
    claude, codex = o.cfg.agents["claude"], o.cfg.agents["codex"]
    p = o.with_rules(claude, "PROMPT", session="s1")
    assert p.startswith("PROJECT RULES") and p.endswith("PROMPT") and "RULE-LEAD" in p  # claude là trưởng nhóm
    assert "RULE-CODEX" not in p and "RULE-OFF" not in p
    q = o.with_rules(codex, "PROMPT")
    assert "RULE-ALL" in q and "RULE-CODEX" in q and "RULE-LEAD" not in q
    assert "RULE-LEAD" in o.with_rules(codex, "PROMPT", lead=True)  # codex làm thay trưởng nhóm
    # tiếp tục phiên: đã có rule -> không gửi lại; rule đổi -> gửi bản mới một lần
    assert o.with_rules(claude, "TIEP", session="s1", resume=True) == "TIEP"
    rules.apply(project, "update", {"id": 1, "text": "RULE-ALL-2"})
    p = o.with_rules(claude, "TIEP", session="s1", resume=True)
    assert "updated" in p and "RULE-ALL-2" in p
    assert o.with_rules(claude, "TIEP", session="s1", resume=True) == "TIEP"
    assert o.with_rules(claude, "X", session="cu", resume=True) == "X"  # phiên từ lần mở app trước
    # chạy thật qua CLI giả lập: /task gửi nguyên văn vẫn kèm rule
    full = tmp_path / "full.log"
    monkeypatch.setenv("ATEAM_FAKE_FULL_LOG", str(full))

    async def main():
        await o.setup()
        o.add_task("codex", "lam viec nay")
        await o.run_until_idle()
    asyncio.run(main())
    sent = full.read_text()
    assert "<<codex>>" in sent and "RULE-ALL-2" in sent and "RULE-CODEX" in sent and "lam viec nay" in sent


def test_tui_rules_screen(env, project, monkeypatch):
    tui, app = _app(env, project, monkeypatch)
    from ateam import rules
    (project / "CLAUDE.md").write_text("# rule")

    async def main():
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.pause(0.2)
            app.run_command("/rules Luôn chạy test")  # kèm nội dung: thêm luôn
            assert rules.load(project)[0]["text"] == "Luôn chạy test"
            app.run_command("/rules")
            await pilot.pause(0.2)
            assert isinstance(app.screen, tui.RulesScreen)
            opts = [str(o.prompt) for o in app.screen.query_one("#rules-list").options]
            assert "Luôn chạy test" in opts[0] and any("CLAUDE.md" in x for x in opts)
            await pilot.press("space")  # tắt
            assert not rules.load(project)[0]["enabled"]
            await pilot.press("a")
            await pilot.pause(0.2)
            assert isinstance(app.screen, tui.RuleEditScreen)
            ed = app.screen.query_one("#rule-text")
            ed.insert("Commit message tiếng Việt")  # bộ gõ gửi dấu rời -> gộp NFC
            await pilot.pause(0.1)
            assert ed.text == "Commit message tiếng Việt"
            app.screen.query_one("#rule-targets").select("agent:codex")
            await pilot.press("ctrl+s")
            await pilot.pause(0.2)
            assert isinstance(app.screen, tui.RulesScreen)
            r = rules.load(project)[1]
            assert r["text"] == "Commit message tiếng Việt" and r["targets"] == ["agent:codex"]
            app.screen.query_one("#rules-list").highlighted = 1
            await pilot.press("d")
            await pilot.pause(0.1)
            await pilot.press("y")
            await pilot.pause(0.1)
            assert len(rules.load(project)) == 1
            await pilot.press("ctrl+q")
    asyncio.run(main())


def test_web_rules_ops(env, project, monkeypatch):
    import pytest
    pytest.importorskip("aiohttp")
    from test_web import _web_app
    wa = _web_app(env, project, monkeypatch)

    async def main():
        r = await wa.handle({"op": "submit", "text": "/rules Viết test"})
        assert r[1] == "ok" and r[2]["open"] == {"modal": "rules"}
        r = await wa.handle({"op": "rules", "action": "add", "text": "Chỉ codex", "targets": ["agent:codex"]})
        assert [x["text"] for x in r[2]["rules"]] == ["Viết test", "Chỉ codex"]
        assert any(t["v"] == "role:lead" for t in r[2]["targets"]) and "rules" in r[2]["file"]
        r = await wa.handle({"op": "rules", "action": "add", "text": ""})
        assert r[1] == "warn" and len(r[2]["rules"]) == 2
    asyncio.run(main())
    wa.remote.readonly = True  # chỉ xem: đọc được, không sửa được
    assert len(asyncio.run(wa.handle({"op": "rules_list"}))[2]["rules"]) == 2
    assert asyncio.run(wa.handle({"op": "rules", "action": "delete", "id": 1}))[1] == "warn"
