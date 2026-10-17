"""Token & cost từ log phiên của CLI (ateam/usage_logs.py), số liệu dashboard (reports.dashboard/goal_history)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from conftest import ateam

from ateam import usage_logs
from ateam.db import DB


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def write_claude(root, cwd: str, prompt: str, t: float, usage: dict, model="claude-sonnet-4-6", mid="m1"):
    d = root / "projects" / usage_logs.encode_dir(cwd)
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{mid}.jsonl"
    lines = [{"type": "user", "timestamp": iso(t), "message": {"role": "user", "content": prompt}}]
    lines += [{"type": "assistant", "timestamp": iso(t + 1), "message": {"id": mid, "model": model, "usage": usage}}] * 2
    f.write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def test_claude_session_matches_cwd_time_and_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    t = time.time()
    u = {"input_tokens": 10, "output_tokens": 20, "cache_read_input_tokens": 300, "cache_creation_input_tokens": 40}
    write_claude(tmp_path / "claude", "/w/proj", "Viết test cho đăng nhập", t, u, mid="a")
    write_claude(tmp_path / "claude", "/w/proj", "Việc khác hẳn", t, dict(u, output_tokens=999), mid="b")
    got = usage_logs.collect("/usr/bin/claude", "/w/proj", t - 1, t + 3, "Viết test cho đăng nhập")
    # hai dòng cùng message.id chỉ tính một lần; chọn đúng phiên theo prompt
    assert (got.in_tok, got.out_tok, got.cache_read, got.cache_write, got.model) == (10, 20, 300, 40,
                                                                                     "claude-sonnet-4-6")
    assert usage_logs.collect("claude", "/w/khac", t - 1, t + 3, "Viết test") is None  # thư mục khác
    assert usage_logs.collect("claude", "/w/proj", t + 600, t + 700, "Viết test cho đăng nhập") is None
    assert usage_logs.collect("grok", "/w/proj", t - 1, t + 3, "x") is None  # CLI không đọc được → ước tính
    # cost: sonnet $3 / $15, đọc cache 0.3, ghi cache 3.75 (USD / 1M token)
    assert abs(usage_logs.cost_of(got) - (10 * 3 + 20 * 15 + 300 * 0.3 + 40 * 3.75) / 1e6) < 1e-12
    assert usage_logs.cost_of(usage_logs.Usage(model="mo-hinh-la")) is None
    over = {"mo-hinh": {"input": 1, "output": 2}}
    assert usage_logs.cost_of(usage_logs.Usage(in_tok=1_000_000, out_tok=1_000_000, model="mo-hinh-la"), over) == 3


def test_codex_session(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex"))
    t = time.time()
    d = tmp_path / "codex" / "sessions" / time.strftime("%Y/%m/%d", time.localtime(t))
    d.mkdir(parents=True)
    lines = [
        {"timestamp": iso(t), "type": "session_meta", "payload": {"cwd": "/w/proj", "timestamp": iso(t)}},
        {"timestamp": iso(t), "type": "turn_context", "payload": {"cwd": "/w/proj", "model": "gpt-5-codex"}},
        {"timestamp": iso(t), "type": "event_msg", "payload": {"type": "user_message", "message": "sửa bug"}},
        {"timestamp": iso(t), "type": "event_msg", "payload": {"type": "token_count", "info": None}},
        {"timestamp": iso(t + 1), "type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": {"input_tokens": 5000, "cached_input_tokens": 4000, "output_tokens": 70}}}},
    ]
    (d / "rollout-1.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    got = usage_logs.collect("codex", "/w/proj", t - 1, t + 3, "sửa bug")
    assert (got.in_tok, got.cache_read, got.out_tok, got.model) == (1000, 4000, 70, "gpt-5-codex")
    assert usage_logs.collect("codex", "/w/khac", t - 1, t + 3, "sửa bug") is None


def test_goal_records_real_tokens_and_dashboard(env, project):
    ateam(env, project, "goal", "-y", "-q", "Tạo các file a b c")
    db = DB(project / ".ateam/team.db")
    runs = db.runs_since(0)
    claude = [r for r in runs if r["agent"] == "claude"]
    # claude giả lập ghi file phiên như Claude Code thật → số thật; agent khác ước tính
    assert claude and all(r["tok_src"] == "cli" and r["in_tok"] == 1000 and r["cache_read"] == 5000
                          and r["model"] == "claude-sonnet-4-6" and r["cost"] for r in claude), claude
    assert any(r["tok_src"] == "estimate" for r in runs if r["agent"] != "claude")
    assert any(r["kind"] == "lead" and r["gid"] == 1 for r in runs)  # lượt lập kế hoạch gắn mục tiêu

    from ateam import reports
    d = reports.dashboard(db)
    assert d["today"]["runs"] == len(runs) and d["today"]["tokens"] > 0 and d["today"]["cost"] > 0
    assert d["by_agent"]["claude"]["real"] == len(claude) and "claude-sonnet-4-6" in d["by_model"]
    assert len(d["per_day"]) == 14 and d["per_day"][-1]["runs"] == len(runs)
    h = reports.goal_history(db)
    assert h[0]["id"] == 1 and h[0]["status"] == "done" and h[0]["tasks"] >= 3 and h[0]["tokens"] > 0
    assert "claude" in h[0]["agents"] and h[0]["cost"] > 0


def test_old_db_without_usage_columns_opens(tmp_path):
    import sqlite3
    p = tmp_path / "team.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER, agent TEXT NOT NULL,"
              " kind TEXT NOT NULL, started REAL, finished REAL, rc INTEGER, status TEXT, prompt_chars INTEGER,"
              " output_chars INTEGER)")
    c.execute("INSERT INTO runs(agent, kind, started, finished, prompt_chars, output_chars)"
              " VALUES ('codex', 'task', ?, ?, 400, 400)", (time.time(), time.time()))
    c.commit()
    c.close()
    db = DB(p)
    r = db.runs_since(0)[0]
    assert r["tokens"] == 200 and r["tok_src"] is None  # lượt cũ: ước tính từ số ký tự


def test_tui_dash_tab(env, project, monkeypatch):
    ateam(env, project, "goal", "-y", "-q", "Tạo các file a b c")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import asyncio
    import importlib

    importlib.reload(importlib.import_module("ateam.config"))  # đọc XDG_CONFIG_HOME của test
    from ateam.config import load_config
    from ateam.tui import TeamApp

    async def main():
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(150, 46)) as pilot:
            await pilot.pause(0.3)
            app.run_command("/dash")
            await pilot.pause(0.5)
            assert app.query_one("#tabs").active == "tab-dash"
            cards = str(app.query_one("#dash-cards").render())
            assert "token" in cards and "$" in cards
            assert app.query_one("#dash-goals").row_count == 1
            assert "Mục tiêu #1" in str(app.query_one("#dash-goal").render())
            app.query_one("#dash-goals").focus()
            await pilot.press("enter")
            await pilot.pause(0.2)
            assert app.query_one("#cmd").value == "/continue m1 "
            await pilot.press("ctrl+q")
    asyncio.run(main())
