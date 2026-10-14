"""Test đơn vị: dựng lệnh, đọc JSON/khối giao việc, nhận diện hết hạn mức, nâng cấp config."""

from __future__ import annotations

import time
from pathlib import Path

from ateam import limits
from ateam import prompts as P
from ateam.config import AgentConfig


def test_argv_inserts_model_and_effort_before_prompt():
    claude = AgentConfig("claude", ["claude", "-p", "{prompt}", "--permission-mode", "acceptEdits"],
                         model_args=["--model", "{model}"], effort_args=["--effort", "{effort}"])
    # cờ phải đứng TRƯỚC "-p" vì -p của vài CLI nhận prompt làm giá trị
    assert claude.argv("HI", model="opus", effort="high") == [
        "claude", "--model", "opus", "--effort", "high", "-p", "HI", "--permission-mode", "acceptEdits"]
    assert claude.argv("HI") == ["claude", "-p", "HI", "--permission-mode", "acceptEdits"]


def test_argv_codex_effort_is_toml_string():
    codex = AgentConfig("codex", ["codex", "exec", "{prompt}"], model_args=["-m", "{model}"],
                        effort_args=["-c", 'model_reasoning_effort="{effort}"'], effort="xhigh")
    assert codex.argv("X") == ["codex", "exec", "-c", 'model_reasoning_effort="xhigh"', "X"]


def test_argv_placeholder_in_command_and_missing_prompt_placeholder():
    a = AgentConfig("x", ["tool", "--model", "{model}", "run"])
    assert a.argv("P") == ["tool", "run", "P"]  # model rỗng: bỏ cả cờ đứng trước
    assert a.argv("P", model="m1") == ["tool", "--model", "m1", "run", "P"]


def test_extract_json_from_noisy_output():
    out = 'Đây là kế hoạch:\n```json\n[{"id": 1, "agent": "codex"}]\n```\nxong'
    assert P.extract_json(out, list) == [{"id": 1, "agent": "codex"}]
    assert P.extract_json('blah {"done": true} more', dict) == {"done": True}
    assert P.extract_json("[1, 2] không phải task", list) is None


def test_delegations_notes_summary():
    out = ('làm...\n<<<DELEGATE to="grok" title="Viết test">>>\nviết test cho a\n<<<END>>>\n'
           '<<<NOTE>>>cổng 8080<<<END>>>\nSUMMARY: xong phần A')
    assert P.parse_delegations(out) == [("grok", "Viết test", "viết test cho a")]
    assert P.parse_notes(out) == ["cổng 8080"]
    assert P.extract_summary(out) == "xong phần A"


def test_rate_limit_detection():
    now = time.time()
    assert limits.looks_rate_limited("Claude AI usage limit reached|%d" % (now + 3600), 1)
    assert limits.looks_rate_limited("Error: 429 Too Many Requests", 1)
    # code nói về rate limiter, chạy thành công, output dài -> KHÔNG phải hết hạn mức
    assert not limits.looks_rate_limited("implement rate limiter\n" * 30, 0)
    t = limits.reset_time("Try again in 7 minutes.", 30, now=now)
    assert 7 * 60 <= t - now <= 8 * 60
    t = limits.reset_time("usage limit reached|%d" % (now + 3600), 30, now=now)
    assert abs(t - (now + 3600)) < 2
    assert abs(limits.reset_time("quota exceeded", 30, now=now) - (now + 1800)) < 2


def test_old_global_config_is_upgraded_with_backup(tmp_path, monkeypatch):
    import importlib

    import ateam.config as cfgmod
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfgmod = importlib.reload(cfgmod)
    try:
        cfgmod.GLOBAL_DIR.mkdir(parents=True)
        cfgmod.GLOBAL_CONFIG.write_text('lead = "claude"\n[agents.claude]\ncommand = ["claude"]\n')
        notes = cfgmod.ensure_global_config()
        assert notes and "nâng cấp" in notes[0]
        assert list(cfgmod.GLOBAL_DIR.glob("config.v1.*.bak.toml"))
        c = cfgmod.load_config(Path(tmp_path / "proj"))
        assert set(c.agents) == {"claude", "codex", "antigravity", "grok"}
        assert c.agents["grok"].model == "xai/grok-build-0.1"
    finally:
        monkeypatch.undo()
        importlib.reload(cfgmod)


def test_mentions_render_per_agent(tmp_path):
    from ateam import mentions
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("")
    roots = [tmp_path]
    text = "sửa @src/app.py. Email a@b.com, @property, (@src/) và codex@xhigh"
    out, extra = mentions.render(text, "claude", roots)
    assert out == text and extra == []
    out, extra = mentions.render(text, "/usr/local/bin/codex", roots)
    assert out == "sửa src/app.py. Email a@b.com, @property, (src/) và codex@xhigh"
    assert extra == []
    out, extra = mentions.render(text, "opencode", roots)
    assert out.startswith("sửa src/app.py.") and extra == ["-f", "src/app.py", "-f", "src/"]
    # ghi đè trong config: file_args = [] tắt cờ, file_ref tuỳ ý
    out, extra = mentions.render("@src/app.py", "opencode", roots, file_ref="`{path}`", file_args=[])
    assert out == "`src/app.py`" and extra == []
    assert mentions.insert_args(["claude", "-p", "P", "--x"], "P", ["-a"]) == ["claude", "-a", "-p", "P", "--x"]
    assert mentions.insert_args(["opencode", "run", "P"], "P", ["-f", "a"]) == ["opencode", "run", "-f", "a", "P"]


def test_mentions_search_ranking():
    from ateam import mentions
    entries = mentions.with_dirs(["README.md", "ateam/tui.py", "ateam/config.py", "tests/test_tui.py",
                                  "docs/CONFIG.md"])
    assert entries[:3] == ["ateam/", "docs/", "tests/"]
    assert mentions.search(entries, "")[:3] == ["ateam/", "docs/", "tests/"]
    assert mentions.search(entries, "tui")[0] == "ateam/tui.py"
    assert mentions.search(entries, "ateam/") == ["ateam/config.py", "ateam/tui.py"]
    assert mentions.search(entries, "atcfg")[0] == "ateam/config.py"   # khớp rải rác
    assert mentions.search(entries, "zzz") == []
