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
        # file mặc định vừa ghi phải mang đúng CONFIG_VERSION, không thì lần mở sau lại sao lưu + thay
        assert cfgmod.ensure_global_config() == []
        assert len(list(cfgmod.GLOBAL_DIR.glob("config.v*.bak.toml"))) == 1
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


def test_parse_models_from_cli_listing():
    from ateam.config import parse_models
    out = "Available models:\n  gemini-3-pro      (default)\n- gemini-3-flash\n\nNAME\nxai/grok-4.7\nxai/grok-4.7\n"
    assert parse_models(out) == ["gemini-3-pro", "gemini-3-flash", "xai/grok-4.7"]
    assert parse_models(out, "grok") == ["xai/grok-4.7"]


def test_parse_models_from_json_catalog():
    """`codex debug models`: JSON 1 dòng, bỏ model ẩn; cảnh báo lẫn trước JSON vẫn đọc được."""
    from ateam.config import parse_models, parse_models_json
    out = ('warning: refresh timed out\n{"models":[{"slug":"gpt-6.1-sol","visibility":"list"},'
           '{"slug":"gpt-reserve","visibility":"hide"},{"slug":"gpt-5.6-luna"},'
           '{"slug":"codex-auto-review","visibility":"hide"}]}')
    assert parse_models(out) == ["gpt-6.1-sol", "gpt-5.6-luna"]
    assert parse_models(out, "luna") == ["gpt-5.6-luna"]
    assert parse_models_json("gemini-3-pro\nxai/grok-4.7") is None
    assert parse_models_json('{"x": 1}') is None


def test_catalog_fills_models_and_efforts(tmp_path, monkeypatch):
    import importlib
    import json

    import ateam.config as cfgmod
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfgmod = importlib.reload(cfgmod)
    try:
        cfgmod.GLOBAL_DIR.mkdir(parents=True)
        cfgmod.GLOBAL_CONFIG.write_text(
            'config_version = 99\n[agents.claude]\ncommand = ["/usr/local/bin/claude", "-p", "{prompt}"]\n'
            '[agents.mine]\ncommand = ["mycli"]\nmodels = ["a", "b"]\nefforts = []\n'
            '[agents.grok]\ncommand = ["opencode", "run", "{prompt}"]\nmodel = "xai/custom"\n')
        cfgmod.STATE_FILE.write_text(json.dumps({"models_found": {"grok": ["xai/grok-5-fast", "xai/grok-4.7"]}}))
        c = cfgmod.load_config(tmp_path / "proj")
        cl = c.agents["claude"]
        assert "opus" in cl.models and cl.efforts == ["low", "medium", "high", "max"]
        assert c.agents["mine"].models == ["a", "b"] and c.agents["mine"].efforts == []
        g = c.agents["grok"]
        assert g.models_command == ["opencode", "models"]
        assert g.models[:3] == ["xai/grok-5-fast", "xai/grok-4.7", "xai/grok-build-0.1"]
        assert g.model_choices()[0] == "xai/custom"
        text = cfgmod.describe_models(c, "grok")
        assert "●xai/custom" in text and "opencode models" in text
    finally:
        monkeypatch.undo()
        importlib.reload(cfgmod)


def test_save_setup_only_stores_differences(tmp_path, monkeypatch):
    import importlib

    import ateam.config as cfgmod
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfgmod = importlib.reload(cfgmod)
    try:
        cfgmod.ensure_global_config()
        assert cfgmod.needs_setup()
        cfgmod.save_setup(tmp_path, "codex", {
            "claude": {"enabled": True, "model": "opus", "effort": None},
            "grok": {"enabled": False, "model": "xai/grok-build-0.1", "effort": "high"},
            "codex": {"enabled": True, "model": None, "effort": None},
        })
        st = cfgmod.load_state()
        assert st["onboarded"] and st["lead"] == "codex"
        # giá trị trùng file cấu hình (enabled = true, model mặc định của grok) không ghi vào state
        assert st["agents"] == {"claude": {"model": "opus"}, "grok": {"enabled": False, "effort": "high"}}
        c = cfgmod.load_config(tmp_path)
        assert c.lead == "codex" and c.agents["claude"].model == "opus"
        assert not c.agents["grok"].enabled and c.agents["grok"].effort == "high"
        assert not cfgmod.needs_setup()
        # chọn lại trưởng nhóm như file cấu hình -> xoá khỏi state
        cfgmod.save_setup(tmp_path, "claude", {"grok": {"enabled": True}})
        st = cfgmod.load_state()
        assert "lead" not in st and st["agents"]["grok"] == {"effort": "high"}
        # vai trò sửa trong màn hình thiết lập: khác file cấu hình mới ghi; workflow mặc định phải tồn tại
        role_default = cfgmod.load_config(tmp_path, with_state=False).agents["codex"].role
        (tmp_path / ".ateam").mkdir()
        (tmp_path / ".ateam" / "config.toml").write_text(
            '[workflows.nhanh]\n[[workflows.nhanh.steps]]\nagent = "grok"\ntitle = "Làm"\n')
        cfgmod.save_setup(tmp_path, "claude", {"codex": {"role": "Chỉ viết backend"},
                                               "grok": {"role": c.agents["grok"].role}}, "nhanh")
        st = cfgmod.load_state()
        assert st["agents"]["codex"] == {"role": "Chỉ viết backend"} and "role" not in st["agents"]["grok"]
        c = cfgmod.load_config(tmp_path)
        assert c.agents["codex"].role == "Chỉ viết backend" and c.default_workflow == "nhanh"
        cfgmod.save_setup(tmp_path, "claude", {"codex": {"role": None}}, "khong-co")
        st = cfgmod.load_state()
        assert "codex" not in st["agents"] and "default_workflow" not in st
        assert cfgmod.load_config(tmp_path).agents["codex"].role == role_default
        st["default_workflow"] = "da-xoa"  # workflow bị xoá sau khi đặt: coi như không đặt
        cfgmod.save_state(st)
        assert cfgmod.load_config(tmp_path).default_workflow == ""
    finally:
        monkeypatch.undo()
        importlib.reload(cfgmod)


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_mentions_images_per_agent(tmp_path):
    from ateam import mentions
    (tmp_path / "shot.png").write_bytes(PNG)
    (tmp_path / "a.py").write_text("")
    roots = [tmp_path]
    text = "xem @shot.png và @a.py"
    assert mentions.render(text, "claude", roots) == (text, [])
    out, extra = mentions.render(text, "codex", roots)
    assert out == "xem shot.png và a.py" and extra == ["--image=shot.png"]   # chỉ ảnh mới có --image
    out, extra = mentions.render(text, "opencode", roots)
    assert extra == ["-f", "shot.png", "-f", "a.py"]                       # opencode -f nhận cả ảnh
    out, extra = mentions.render(text, "opencode", roots, image_args=["--img", "{path}"])
    assert extra == ["--img", "shot.png", "-f", "a.py"]
    assert "ảnh: a.png + --image=a.png" in mentions.describe("codex")
    assert "ảnh" not in mentions.describe("claude")
    # ảnh nằm ở thư mục dự án nhưng không có trong worktree -> đường dẫn tuyệt đối
    wt = tmp_path / "wt"
    wt.mkdir()
    (tmp_path / ".ateam" / "images").mkdir(parents=True)
    (tmp_path / ".ateam" / "images" / "p.png").write_bytes(PNG)
    out, extra = mentions.render("@.ateam/images/p.png", "codex", [wt, tmp_path])
    full = str(tmp_path / ".ateam" / "images" / "p.png")
    assert out == full and extra == ["--image=" + full]


def test_dropped_images(tmp_path):
    from ateam import clipboard
    a = tmp_path / "Ảnh chụp 1.png"
    a.write_bytes(PNG)
    b = tmp_path / "b.jpg"
    b.write_bytes(b"\xff\xd8\xff\xe0")
    (tmp_path / "c.txt").write_text("")
    esc = str(a).replace(" ", "\\ ")
    assert clipboard.dropped_images(f"{esc} '{b}' ") == [str(a), str(b)]
    assert clipboard.dropped_images("file://" + str(b)) == [str(b)]
    assert clipboard.dropped_images(str(tmp_path / "c.txt")) is None     # không phải ảnh
    assert clipboard.dropped_images(str(tmp_path / "nope.png")) is None  # không tồn tại
    assert clipboard.dropped_images("chữ thường") is None
    assert clipboard.shorten(a, tmp_path) == "Ảnh chụp 1.png"


def test_grab_image_from_clipboard(tmp_path, monkeypatch):
    import asyncio
    import os
    from ateam import clipboard
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    state = tmp_path / "clip"
    # xclip giả: TARGETS -> danh sách kiểu; -t image/png -> nội dung file $state
    (bin_ / "xclip").write_text(
        '#!/usr/bin/env bash\n'
        f'S="{state}"\n'
        '[ -f "$S" ] || exit 1\n'
        'if [[ "$*" == *TARGETS* ]]; then echo "TARGETS"; echo "image/png"; exit 0; fi\n'
        'cat "$S"\n')
    (bin_ / "xclip").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(clipboard, "methods", lambda: ["xclip"])
    folder = tmp_path / ".ateam" / "images"
    path, why = asyncio.run(clipboard.grab_image(folder))
    assert path is None and why == "clipboard không có ảnh"
    state.write_bytes(PNG)
    path, why = asyncio.run(clipboard.grab_image(folder))
    assert path and path.parent == folder and path.read_bytes() == PNG and why == ""
    state.write_bytes(b"not an image")
    assert asyncio.run(clipboard.grab_image(folder))[0] is None


def test_custom_agents_and_workflows_file(tmp_path, monkeypatch):
    """custom.toml: ghi/đọc lại đúng, gộp vào đội, giữ nguyên khi config.toml được nâng cấp."""
    import importlib

    import ateam.config as cfgmod
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfgmod = importlib.reload(cfgmod)
    try:
        cfgmod.ensure_global_config()
        cfgmod.save_custom_item("agents", "my ai", {
            "command": ["mycli", "--go", "{prompt}"], "role": 'viết "nhanh"\nvà gọn',
            "model_args": ["--model", "{model}"], "efforts": [], "file_args": [], "pty": True})
        cfgmod.save_custom_item("workflows", "feat", {
            "description": "d", "review": False,
            "steps": [{"agent": "lead", "title": "Thiết kế {goal}", "prompt": "nghĩ về {goal}"},
                      {"agent": "my ai", "title": "Code", "prompt": "code"},
                      {"agent": "codex", "title": "Song song", "prompt": "x", "after": []},
                      {"agent": "grok", "title": "Cuối", "prompt": "y", "after": [2, 3], "effort": "high"}]})
        raw = cfgmod.load_custom()
        assert raw["agents"]["my ai"]["role"] == 'viết "nhanh"\nvà gọn'
        c = cfgmod.load_config(tmp_path / "proj")
        assert "my ai" in c.agents and c.custom_agents == {"my ai"}
        a = c.agents["my ai"]
        assert a.pty and a.efforts == [] and a.file_args == []
        assert a.argv("P", model="m1") == ["mycli", "--go", "--model", "m1", "P"]
        plan = c.workflows["feat"].plan("G", c.lead)
        assert [p["agent"] for p in plan] == ["claude", "my ai", "codex", "grok"]
        assert plan[0]["title"] == "Thiết kế G" and plan[0]["prompt"] == "nghĩ về G"
        assert [p["depends_on"] for p in plan] == [[], [1], [], [2, 3]]
        assert plan[3]["effort"] == "high" and c.workflows["feat"].review is False
        # đổi tên rồi xoá
        cfgmod.save_custom_item("workflows", "feat2", cfgmod.workflow_to_dict(c.workflows["feat"]), "feat")
        assert list(cfgmod.load_config(tmp_path / "proj").workflows) == ["feat2"]
        cfgmod.save_custom_item("workflows", "feat2", None)
        assert not cfgmod.load_config(tmp_path / "proj").workflows
        # config.toml cũ bị thay khi nâng cấp, agent tuỳ chỉnh vẫn còn
        cfgmod.GLOBAL_CONFIG.write_text('config_version = 1\nlead = "claude"\n')
        assert cfgmod.ensure_global_config()
        assert "my ai" in cfgmod.load_config(tmp_path / "proj").agents
    finally:
        monkeypatch.undo()
        importlib.reload(cfgmod)


def test_legacy_codex_full_auto_is_rewritten():
    from ateam.config import fix_legacy_flags
    old = ["codex", "exec", "--full-auto", "--skip-git-repo-check", "{prompt}"]
    assert fix_legacy_flags(old) == ["codex", "exec", "--sandbox", "workspace-write",
                                     "--skip-git-repo-check", "{prompt}"]
    # đã có --sandbox thì chỉ bỏ --full-auto; CLI khác không đụng tới
    assert fix_legacy_flags(["codex", "exec", "--full-auto", "--sandbox", "read-only", "{prompt}"]) == [
        "codex", "exec", "--sandbox", "read-only", "{prompt}"]
    assert fix_legacy_flags(["mycli", "--full-auto", "{prompt}"]) == ["mycli", "--full-auto", "{prompt}"]


def test_unknown_flags_against_help():
    from ateam.config import help_command, unknown_flags
    cmd = ["codex", "exec", "--full-auto", "-c", "x=1", "--skip-git-repo-check", "{prompt}"]
    assert help_command(cmd) == ["codex", "exec", "--help"]
    assert help_command(["claude", "-p", "{prompt}"]) == ["claude", "--help"]
    help_text = "Options:\n  -c, --config <key=value>\n  -s, --sandbox <MODE>\n      --skip-git-repo-check\n"
    assert unknown_flags(cmd, help_text) == ["--full-auto"]
    # "-s" không được tính là có mặt nhờ "--skip-…" (so khớp nguyên cờ)
    assert unknown_flags(["x", "-p", "{prompt}"], "  --print-timeout") == ["-p"]


def test_bad_flag_failure_points_to_doctor():
    from ateam.orchestrator import Orchestrator

    class R:
        cancelled = timed_out = False
        output = "error: unexpected argument '--full-auto' found\n\nUsage: codex exec [OPTIONS]"
    assert Orchestrator._classify(R(), 2) == "badflag"
    R.output = "boom"
    assert Orchestrator._classify(R(), 1) == "failed"


def test_log_styler_formats_agent_output():
    """Log hiển thị: ẩn prompt codex in lại, gộp lỗi JSON lặp, nhãn NOTE/DELEGATE/SUMMARY, markdown."""
    from ateam.tui import LogStyler, styled_lines
    log = "\n".join([
        "$ codex · task · gpt-5.5 · medium · /p",
        "Reading additional input from stdin...",
        "OpenAI Codex v0.162.1",
        "--------",
        "model: gpt-5.5",
        "--------",
        "user",
        'You are "codex"…',
        "<<<NOTE>>>your note<<<END>>>",
        "2026-10-15T06:45:08.913858Z ERROR codex_models_manager: request timed out",
        'ERROR: {"type":"error","status":400,"error":{"message":"model không hỗ trợ"}}',
        'ERROR: {"type":"error","status":400,"error":{"message":"model không hỗ trợ"}}',
        "codex",
        "Đã sửa **app.py** và `utils.py`",
        "- mục một",
        '<<<DELEGATE to="grok" title="Viết README">>>',
        "nội dung giao",
        "<<<END>>>",
        "<<<NOTE>>>dòng 1",
        "dòng 2<<<END>>>",
        "SUMMARY: xong",
    ])
    out = styled_lines(log, LogStyler())
    plain = [t.plain for t in out]
    assert plain[0] == "▍codex · task · gpt-5.5 · medium  /p"
    assert "▸ prompt gửi agent (ẩn)" in plain
    assert not any("You are" in p or "your note" in p for p in plain)   # prompt in lại bị ẩn
    assert plain.count("✗ Lỗi: model không hỗ trợ") == 1
    assert "error: codex_models_manager: request timed out" in plain
    md = out[plain.index("Đã sửa app.py và utils.py")]
    assert [(md.plain[sp.start:sp.end], str(sp.style)) for sp in md.spans] == [("app.py", "bold"),
                                                                               ("utils.py", "cyan")]
    assert "• mục một" in plain
    assert "↪ Giao cho grok: Viết README" in plain and "   nội dung giao" in plain
    assert "📝 Ghi chú: dòng 1" in plain and "   dòng 2" in plain
    assert plain[-1] == "✔ Tóm tắt: xong"
    assert all("<<<" not in p for p in plain)
    sysline = styled_lines("[13:45:17] ✗ #2 codex: failed", LogStyler())[0]
    assert sysline.plain == "13:45:17 ✗ #2 codex: failed" and not sysline.style


def test_log_styler_renders_lead_plan_and_review():
    """JSON kế hoạch/review của trưởng nhóm (1 dòng hoặc nhiều dòng trong ```json) vẽ thành danh sách."""
    from ateam.tui import LogStyler, styled_lines
    one = ('  [claude] [{"id": 1, "agent": "codex", "effort": "high", "title": "Hero banner",'
           ' "prompt": "Thay logo chữ", "depends_on": []}, {"id": 2, "agent": "grok", "title": "Test",'
           ' "prompt": "viết test", "depends_on": [1]}]')
    multi = ["```json", "[", '  {"id": 1, "agent": "codex", "title": "A", "prompt": "làm A"}', "]", "```"]
    review = '{"done": false, "summary": "Thiếu **test**", "new_tasks": []}'
    plain = [t.plain for t in styled_lines("\n".join([one, *multi, review, "{ không phải json"]), LogStyler())]
    assert plain[0].startswith("  [claude] 📋 Kế hoạch: 2 task")
    assert "#1  codex@high  Hero banner" in plain[0] and "Thay logo chữ" in plain[0]
    assert "#2  grok  Test  ⟵ sau #1" in plain[0]
    assert plain[1].startswith("📋 Kế hoạch: 1 task") and "#1  codex  A" in plain[1]
    assert plain[2] == "🔎 Review: cần làm thêm\n  Thiếu test"
    assert plain[3] == "{ không phải json"            # không phải JSON: giữ nguyên
    assert not any("```" in p or '"agent"' in p for p in plain)


DIFF_SAMPLE = """\
diff --git a/src/Hero.tsx b/src/Hero.tsx
index 1..2 100644
--- a/src/Hero.tsx
+++ b/src/Hero.tsx
@@ -1,4 +1,5 @@
 import a
+import { useSystem } from "./s"
 <div>
-  <KaceLogo isDark size="loader" />
+  <img src={logo} className="h-10" />
 </div>
\\ No newline at end of file
diff --git a/old.css b/old.css
deleted file mode 100644
--- a/old.css
+++ /dev/null
@@ -1 +0,0 @@
-old
diff --git a/name1.txt b/name2.txt
similarity index 100%
rename from name1.txt
rename to name2.txt
diff --git a/logo.png b/logo.png
new file mode 100644
Binary files /dev/null and b/logo.png differ
diff --git a/tài liệu.md b/tài liệu.md
new file mode 100644
--- /dev/null
+++ b/tài liệu.md
@@ -0,0 +1,2 @@
+# Tiêu đề
+dòng
"""


def test_diffview_parse_unified():
    from ateam.diffview import parse_unified
    files = parse_unified(DIFF_SAMPLE)
    assert [(f.status, f.path, f.old_path) for f in files] == [
        ("M", "src/Hero.tsx", "src/Hero.tsx"), ("D", "old.css", "old.css"),
        ("R", "name2.txt", "name1.txt"), ("A", "logo.png", "logo.png"), ("A", "tài liệu.md", "tài liệu.md")]
    hero = files[0]
    assert (hero.added, hero.removed) == (2, 1) and not files[3].hunks and files[3].binary
    lines = hero.hunks[0].lines
    assert [(ln.kind, ln.old_no, ln.new_no) for ln in lines] == [
        (" ", 1, 1), ("+", None, 2), (" ", 2, 3), ("-", 3, None), ("+", None, 4), (" ", 4, 5)]
    assert files[4].hunks[0].lines[1].new_no == 2


def test_diffview_split_rows_and_word_spans():
    from ateam.diffview import Hunk, DiffLine, parse_unified, split_rows, word_spans
    hero = parse_unified(DIFF_SAMPLE)[0].hunks[0]
    # dòng thêm lẻ: bên trái trống; khối sửa: dòng xoá đối diện dòng thêm
    assert split_rows(hero) == [(0, 0), (None, 1), (2, 2), (3, 4), (5, 5)]
    h = Hunk("@@", [DiffLine("-", 1, None, "a"), DiffLine("-", 2, None, "b"), DiffLine("+", None, 1, "c")])
    assert split_rows(h) == [(0, 2), (1, None)]
    old, new = word_spans('  <KaceLogo isDark size="loader" />', '  <img isDark size="x" />')
    a, b = '  <KaceLogo isDark size="loader" />', '  <img isDark size="x" />'
    assert [a[s:e] for s, e in old] == ["KaceLogo", "loader"]   # theo từ, không vụn từng ký tự
    assert [b[s:e] for s, e in new] == ["img", "x"]
    assert word_spans("hoàn toàn khác", "xyz 123 !!") == ([], [])  # khác hẳn: chỉ tô nền dòng


def test_diffview_render_fits_width():
    from ateam.diffview import added_file, parse_unified, render
    files = parse_unified(DIFF_SAMPLE)
    for split in (True, False):
        for width in (60, 140):
            text, starts = render(files[0], width, split)
            assert starts == [0]
            assert all(ln.cell_len <= width for ln in text.split("\n")), (split, width)
    assert "nhị phân" in render(files[3], 80, True)[0].plain
    assert "chỉ đổi tên" in render(files[2], 80, True)[0].plain
    fd = added_file("a.py", "x = 1\ny = 2")
    assert (fd.status, fd.added) == ("A", 2)
    assert added_file("a.bin", None).binary


def test_self_update(monkeypatch):
    """/update: đã mới nhất -> không làm gì; cài từ mã nguồn -> chỉ dẫn git pull; có bản mới -> chạy get.sh."""
    import asyncio

    from ateam import __version__, update

    async def latest_same():
        return __version__

    async def latest_new():
        return "99.0.0"

    lines = []
    monkeypatch.setattr(update, "latest_version", latest_same)
    assert asyncio.run(update.run_update(lines.append)) == (False, f"Đang dùng bản mới nhất ({__version__}).")
    monkeypatch.setattr(update, "latest_version", latest_new)
    monkeypatch.setattr(update, "editable_source", lambda: Path("/src/ateam"))
    ok, msg = asyncio.run(update.run_update(lines.append))
    assert not ok and "git -C /src/ateam pull" in msg and not lines
    monkeypatch.setattr(update, "editable_source", lambda: None)
    monkeypatch.setattr(update, "UPDATE_CMD", ["bash", "-c", "echo '→ Tải ateam'; echo '✓ Xong.'"])
    ok, msg = asyncio.run(update.run_update(lines.append))
    assert ok and "99.0.0" in msg and lines[-2:] == ["→ Tải ateam", "✓ Xong."]
    monkeypatch.setattr(update, "UPDATE_CMD", ["bash", "-c", "exit 3"])
    ok, msg = asyncio.run(update.run_update(lines.append))
    assert not ok and "mã thoát 3" in msg
    assert update.parse_version("0.10.0") > update.parse_version("0.9.9")


def test_shell_project_scripts_and_ports(tmp_path):
    """Gợi ý cho !: lệnh gần đây trước, script package.json theo lockfile, target Makefile; bắt port."""
    import json

    from ateam.shell import find_ports, project_scripts
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"dev": "next dev -p 3000", "lint": "eslint"}}))
    assert [c for c, _ in project_scripts(tmp_path, [])] == ["npm run dev", "npm run lint"]
    (tmp_path / "yarn.lock").write_text("")
    (tmp_path / "pnpm-lock.yaml").write_text("")   # pnpm ưu tiên hơn yarn
    (tmp_path / "Makefile").write_text(".PHONY: test\nCC := gcc\ntest: build\n\tpytest\nbuild:\n\tcc\n%.o: %.c\n")
    got = project_scripts(tmp_path, ["make test", "ls -la"])
    assert [c for c, _ in got] == ["make test", "ls -la", "pnpm dev", "pnpm lint", "make build"]
    assert dict(got)["pnpm dev"] == "next dev -p 3000" and dict(got)["make test"] == "chạy gần đây"
    assert find_ports("  - Local:        http://localhost:3000") == [3000]
    assert find_ports("ready - started server on 0.0.0.0:5173, url: http://127.0.0.1:5173") == [5173]
    assert find_ports("Listening on port 8080") == [8080] and find_ports("version 1.2.3") == []


def test_full_access_flags_per_cli():
    """Toàn quyền đổi đúng cờ từng CLI (và đổi ngược lại được); CLI lạ giữ nguyên."""
    from ateam.config import agent_from_dict, apply_access, provider_template
    safe = {
        "claude": ["claude", "-p", "{prompt}", "--permission-mode", "acceptEdits"],
        "codex": ["codex", "exec", "--sandbox", "workspace-write", "--skip-git-repo-check", "{prompt}"],
        "agy": ["agy", "--mode", "accept-edits", "--print-timeout", "0", "-p", "{prompt}"],
        "opencode": ["opencode", "run", "{prompt}"],
    }
    full = {
        "claude": ["claude", "-p", "{prompt}", "--permission-mode", "bypassPermissions"],
        "codex": ["codex", "exec", "--sandbox", "danger-full-access", "--skip-git-repo-check", "{prompt}"],
        "agy": ["agy", "--dangerously-skip-permissions", "--print-timeout", "0", "-p", "{prompt}"],
        "opencode": ["opencode", "run", "--auto", "{prompt}"],
    }
    for k in safe:
        assert apply_access(safe[k], True) == full[k], k
        assert apply_access(full[k], False) == safe[k], k
        assert apply_access(safe[k], False) == safe[k], k
        assert safe[k] == provider_template(k)["command"], k   # khớp lệnh mẫu trong DEFAULT_CONFIG
    assert apply_access(["mycli", "{prompt}"], True) == ["mycli", "{prompt}"]
    a = agent_from_dict("x", dict(provider_template("agy"), full_access=True, model="m"))
    assert a.argv("làm") == ["agy", "--dangerously-skip-permissions", "--print-timeout", "0",
                             "--model", "m", "-p", "làm"]
