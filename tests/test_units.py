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


def test_argv_model_with_effort_suffix_drops_effort_flag():
    # agy: "--model gemini-4-argon-medium conflicts with --effort=high" -> đổi sang biến thể -high
    agy = AgentConfig("antigravity", ["agy", "-p", "{prompt}"], model_args=["--model", "{model}"],
                      effort_args=["--effort", "{effort}"],
                      models=["gemini-4-argon-medium", "gemini-4-argon-high", "claude-sonnet-4-6"])
    assert agy.argv("P", model="gemini-4-argon-medium", effort="high") == [
        "agy", "--model", "gemini-4-argon-high", "-p", "P"]
    # không có biến thể đúng effort: mức gần nhất có biến thể (xhigh -> high)
    assert agy.argv("P", model="gemini-4-argon-medium", effort="xhigh") == [
        "agy", "--model", "gemini-4-argon-high", "-p", "P"]
    assert agy.efforts_for("gemini-4-argon-medium") == ["medium", "high"]
    # model không có biến thể (claude-*): agy 1.4.2 báo "--effort is not supported" -> không gửi effort
    assert agy.efforts_for("claude-sonnet-4-6") == []
    assert agy.argv("P", model="claude-sonnet-4-6", effort="high") == [
        "agy", "--model", "claude-sonnet-4-6", "-p", "P"]
    # tên gốc không đuôi (gemini-4-argon) nhận --effort
    assert agy.argv("P", model="gemini-4-argon", effort="high") == [
        "agy", "--model", "gemini-4-argon", "--effort", "high", "-p", "P"]
    # model lạ (chưa có trong danh sách): giữ nguyên --effort như cũ
    assert agy.argv("P", model="gemini-9", effort="high")[-4:-2] == ["--effort", "high"]
    # log/ô agent ghi model chạy thật, tách phần effort trong tên
    assert agy.label("gemini-4-argon-medium", "high") == "gemini-4-argon · high"
    agy.model = "gemini-4-argon-medium"
    assert agy.current_effort() == "medium" and agy.label() == "gemini-4-argon · medium"


def test_argv_placeholder_in_command_and_missing_prompt_placeholder():
    a = AgentConfig("x", ["tool", "--model", "{model}", "run"])
    assert a.argv("P") == ["tool", "run", "P"]  # model rỗng: bỏ cả cờ đứng trước
    assert a.argv("P", model="m1") == ["tool", "--model", "m1", "run", "P"]


def test_argv_opencode_variant_flag():
    # opencode 1.19 có lại `run --variant`; "provider/model#variant" thì báo "Unexpected server error" (đã thử)
    from ateam.config import agent_from_dict, provider_template
    oc = agent_from_dict("opencode", provider_template("opencode"))
    assert oc.argv("P", model="xai/grok-4.7", effort="medium") == [
        "opencode", "run", "--model", "xai/grok-4.7", "--variant", "medium", "P"]
    assert oc.argv("P", model="xai/grok-4.7") == ["opencode", "run", "--model", "xai/grok-4.7", "P"]
    oc.model = ""
    assert oc.argv("P", effort="high") == ["opencode", "run", "--variant", "high", "P"]
    # mức riêng từng model (opencode models --verbose): medium không có -> mức gần nhất (hoà lấy mức cao)
    oc.model_efforts = {"opencode/deepseek-v4.1-flash-free": ["low", "high", "max"], "xai/grok-build-0.1": []}
    assert oc.argv("P", model="opencode/deepseek-v4.1-flash-free", effort="medium")[-3:-1] == ["--variant", "high"]
    assert "--variant" not in oc.argv("P", model="xai/grok-build-0.1", effort="high")  # model không có variant
    # cấu hình cũ còn dạng gộp model#variant được chọn lại theo phiên bản khi dựng lệnh
    old = agent_from_dict("deepseek", {"command": ["opencode", "run", "{prompt}"],
                                       "model_args": ["--model", "{model}"],
                                       "effort_args": ["--model", "{model}#{effort}"],
                                       "model": "xai/grok-4.7", "effort": "high"})
    old.opencode_major = 1
    assert old.argv("P") == ["opencode", "run", "--model", "xai/grok-4.7", "--variant", "high", "P"]


def test_nearest_effort_and_codex_per_model():
    from ateam.config import nearest_effort
    assert nearest_effort("medium", ["low", "high", "max"]) == "high"
    assert nearest_effort("ultra", ["low", "medium", "high", "xhigh", "max"]) == "max"
    assert nearest_effort("high", []) == ""
    codex = AgentConfig("codex", ["codex", "exec", "{prompt}"], effort_args=["-c", 'model_reasoning_effort="{effort}"'],
                        efforts=["low", "medium", "high", "xhigh", "max", "ultra"], model="gpt-6-luna",
                        model_efforts={"gpt-6-luna": ["low", "medium", "high", "xhigh", "max"]})
    assert codex.efforts_for() == ["low", "medium", "high", "xhigh", "max"]
    assert codex.argv("P", effort="ultra") == ["codex", "exec", "-c", 'model_reasoning_effort="max"', "P"]
    assert "ultra" in codex.efforts_for("gpt-6.1-sol")  # model chưa biết: danh sách chung


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
        assert set(c.agents) == {"claude", "codex", "antigravity", "grok", "opencode"}
        assert c.agents["grok"].binary == "grok" and c.agents["opencode"].model == "xai/grok-build-0.1"
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
    assert out.startswith("sửa src/app.py.") and extra == ["-f", "src/app.py"]
    # ghi đè trong config: file_args = [] tắt cờ, file_ref tuỳ ý
    out, extra = mentions.render("@src/app.py", "opencode", roots, file_ref="`{path}`", file_args=[])
    assert out == "`src/app.py`" and extra == []
    assert mentions.insert_args(["claude", "-p", "P", "--x"], "P", ["-a"]) == ["claude", "-a", "-p", "P", "--x"]
    assert mentions.insert_args(["opencode", "run", "P"], "P", ["-f", "a"]) == ["opencode", "run", "-f", "a", "--", "P"]
    # cờ dạng --x=giá-trị không cần "--"; prompt không đứng cuối thì không thêm (cờ sau prompt vẫn là cờ)
    assert mentions.insert_args(["codex", "exec", "P"], "P", ["--image=a"]) == ["codex", "exec", "--image=a", "P"]
    assert mentions.insert_args(["x", "P", "--y"], "P", ["-f", "a"]) == ["x", "-f", "a", "P", "--y"]


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
        cfgmod.STATE_FILE.write_text(json.dumps({"models_found": {"grok": ["xai/grok-5-fast", "xai/grok-4.7"]},
                                                 "models_found_v": 2}))
        c = cfgmod.load_config(tmp_path / "proj")
        cl = c.agents["claude"]
        assert "opus" in cl.models and cl.efforts == ["low", "medium", "high", "xhigh", "max"]
        assert c.agents["mine"].models == ["a", "b"] and c.agents["mine"].efforts == []
        g = c.agents["grok"]
        assert g.models_command == ["opencode", "models", "--verbose"]
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
            "opencode": {"enabled": False, "model": "xai/grok-build-0.1", "effort": "high"},
            "codex": {"enabled": True, "model": None, "effort": None},
        })
        st = cfgmod.load_state()
        assert st["onboarded"] and st["lead"] == "codex"
        # giá trị trùng file cấu hình (enabled = true, model mặc định của opencode) không ghi vào state
        assert st["agents"] == {"claude": {"model": "opus"}, "opencode": {"enabled": False, "effort": "high"}}
        c = cfgmod.load_config(tmp_path)
        assert c.lead == "codex" and c.agents["claude"].model == "opus"
        assert not c.agents["opencode"].enabled and c.agents["opencode"].effort == "high"
        assert not cfgmod.needs_setup()
        # chọn lại trưởng nhóm như file cấu hình -> xoá khỏi state
        cfgmod.save_setup(tmp_path, "claude", {"opencode": {"enabled": True}})
        st = cfgmod.load_state()
        assert "lead" not in st and st["agents"]["opencode"] == {"effort": "high"}
        # vai trò sửa trong màn hình thiết lập: khác file cấu hình mới ghi; workflow mặc định phải tồn tại
        role_default = cfgmod.load_config(tmp_path, with_state=False).agents["codex"].role
        (tmp_path / ".ateam").mkdir()
        (tmp_path / ".ateam" / "config.toml").write_text(
            '[workflows.nhanh]\n[[workflows.nhanh.steps]]\nagent = "grok"\ntitle = "Làm"\n')
        cfgmod.save_setup(tmp_path, "claude", {"codex": {"role": "Chỉ viết backend"},
                                               "opencode": {"role": c.agents["opencode"].role}}, "nhanh")
        st = cfgmod.load_state()
        assert st["agents"]["codex"] == {"role": "Chỉ viết backend"} and "role" not in st["agents"]["opencode"]
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


def test_diffview_long_lines_do_not_hang():
    """Dòng cực dài (tsconfig.tsbuildinfo, *.min.js…): không so từng chữ (difflib bình phương làm treo app), chỉ hiện
    phần đầu dòng — cả diff dựng xong ngay."""
    import time

    from ateam import diffview
    from ateam.web_git import diffset_json
    old = '{"program":{"fileNames":[' + ",".join(f'"./src/f{i}.ts"' for i in range(30000)) + "]}}"
    new = old.replace("f29999", "g29999").replace("f7", "h7")
    patch = f"diff --git a/t.tsbuildinfo b/t.tsbuildinfo\n--- a/t.tsbuildinfo\n+++ b/t.tsbuildinfo\n@@ -1 +1 @@\n-{old}\n+{new}\n"
    start = time.time()
    fd = diffview.parse_unified(patch)[0]
    assert diffview.word_spans(old, new) == ([], [])
    shown = fd.hunks[0].lines[0].text
    assert len(shown) < diffview.MAX_LINE_CHARS + 100 and "+" in shown[diffview.MAX_LINE_CHARS:]
    out = diffset_json(diffview.DiffSet(0, "x", [fd], "HEAD", None))
    assert len(out["files"][0]["hunks"][0]["lines"]) == 2
    assert time.time() - start < 3  # trước khi sửa: treo hàng giờ


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


def test_goal_followups_migration_and_continue_refs(tmp_path):
    import sqlite3
    from ateam.config import Config
    from ateam.db import DB
    from ateam.orchestrator import Orchestrator
    # DB cũ chưa có cột followups vẫn mở được
    path = tmp_path / "old.db"
    c = sqlite3.connect(str(path))
    c.execute("CREATE TABLE goals (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL,"
              " status TEXT NOT NULL DEFAULT 'planning', round INTEGER NOT NULL DEFAULT 1,"
              " summary TEXT, created REAL)")
    c.execute("INSERT INTO goals(text, status) VALUES ('làm A', 'done')")
    c.commit()
    c.close()
    db = DB(path)
    g = db.goal(1)
    assert g.followups == [] and g.full_text() == "làm A"
    db.add_followup(1, "thêm B")
    assert db.goal(1).full_text() == "làm A\n\nFOLLOW-UP 1: thêm B"

    o = Orchestrator(tmp_path, Config(), db)
    in_goal = db.add_task("codex", "t", "p", goal_id=1, status="done")
    alone = db.add_task("codex", "t", "p", status="running")
    assert o.continue_ref("m1") == ("goal", 1)
    assert o.continue_ref(f"t{in_goal}") == ("goal", 1)  # task thuộc mục tiêu -> mục tiêu
    assert o.continue_ref(str(alone)) == ("task", alone)
    assert "Không có mục tiêu" in o.continue_ref("m9")
    assert "chưa xong" in o.continue_task(alone, "x")
    db.update_goal(1, status="running")
    assert "chưa kết thúc" in o.continue_goal(1, "x")


def test_thread_prompt_includes_previous_turns():
    assert P.thread_prompt([], "chỉ hỏi") == "chỉ hỏi"
    p = P.thread_prompt([("viết hàm cộng", "đã viết add()")], "thêm test")
    assert p.index("viết hàm cộng") < p.index("đã viết add()") < p.index("NEW REQUEST:\nthêm test")


def test_grok_build_cli_flags_and_models():
    from ateam.config import apply_access, parse_models
    # grok -p: "acceptEdits" chặn cả sửa file -> chỉ sửa file = auto + --deny Bash (đã thử với grok thật)
    cmd = ["grok", "--permission-mode", "auto", "--deny", "Bash", "-p", "{prompt}"]
    assert apply_access(cmd, True) == ["grok", "--permission-mode", "bypassPermissions", "-p", "{prompt}"]
    assert apply_access(apply_access(cmd, True), False) == cmd
    assert apply_access(["grok", "--permission-mode", "acceptEdits", "-p", "{prompt}"], False) == cmd  # cấu hình 0.6.0
    grok = AgentConfig("grok", cmd, model_args=["-m", "{model}"],
                       effort_args=["--reasoning-effort", "{effort}"], model="grok-4.7", effort="xhigh")
    assert grok.argv("HI") == ["grok", "--permission-mode", "auto", "--deny", "Bash", "-m", "grok-4.7",
                               "--reasoning-effort", "xhigh", "-p", "HI"]
    out = ("You are not authenticated.\n\nDefault model: grok-4.7\n\nAvailable models:\n"
           "  * grok-4.7 (default)\n  - grok-4.7-build-fast\n  - grok-4.6\n")
    assert parse_models(out, "grok") == ["grok-4.7", "grok-4.7-build-fast", "grok-4.6"]


def test_state_of_old_grok_agent_moves_to_opencode(tmp_path, monkeypatch):
    """Bản 6: "grok" thành Grok Build CLI; model/effort đã chọn cho grok cũ (qua opencode) chuyển sang
    agent "opencode", không áp nhầm vào Grok Build."""
    import importlib
    import json

    import ateam.config as cfgmod
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfgmod = importlib.reload(cfgmod)
    try:
        cfgmod.GLOBAL_DIR.mkdir(parents=True)
        cfgmod.GLOBAL_CONFIG.write_text('config_version = 5\nlead = "claude"\n[agents.grok]\n'
                                        'command = ["opencode", "run", "{prompt}"]\n')
        cfgmod.STATE_FILE.write_text(json.dumps({
            "lead": "grok", "agents": {"grok": {"model": "xai/grok-4.7", "role": "R"}},
            "models_found": {"grok": ["xai/grok-4.7"]}}))
        notes = cfgmod.ensure_global_config()
        assert any("Grok Build" in n for n in notes)
        st = cfgmod.load_state()
        assert st["agents"] == {"opencode": {"model": "xai/grok-4.7", "role": "R"}}
        assert st["models_found"] == {"opencode": ["xai/grok-4.7"]} and st["lead"] == "opencode"
        assert list(cfgmod.GLOBAL_DIR.glob("state.v5.*.bak.json"))
        c = cfgmod.load_config(tmp_path)
        assert c.agents["grok"].binary == "grok" and c.agents["grok"].model == ""
        assert c.agents["opencode"].model == "xai/grok-4.7"
    finally:
        monkeypatch.delenv("XDG_CONFIG_HOME")
        importlib.reload(cfgmod)


def test_plan_team_groups_roles_and_adds_agents():
    from ateam.config import TIER_PRESETS, PROVIDERS, plan_team, tier_preset
    plan = plan_team({
        "lead": ("claude", "opus", "high"), "code": ("codex", "", "medium"),
        "review": ("claude", "sonnet", "medium"), "ui": ("claude", "opus", "high"),
        "test": None, "research": ("agy", "", ""),
    })
    assert plan.lead == "claude"
    assert plan.agents["claude"]["roles"] == ["lead", "ui"] and plan.agents["claude"]["builtin"]
    # cùng CLI nhưng model khác -> agent thêm, không phải agent có sẵn
    assert plan.agents["claude-review"] == {"provider": "claude", "model": "sonnet", "effort": "medium",
                                            "roles": ["review"], "builtin": False}
    assert plan.agents["antigravity"]["provider"] == "agy"
    assert set(plan.unused) == {"grok", "opencode"}
    # mỗi nhà cung cấp đều có mức gợi ý; trưởng nhóm được nâng 1 mức; effort sai bị bỏ
    assert set(TIER_PRESETS) == set(PROVIDERS)
    models = ["opus", "sonnet", "haiku"]
    assert tier_preset("claude", "eco", "code", models, ["low", "medium", "high", "max"]) == ("sonnet", "low")
    assert tier_preset("claude", "eco", "lead", models, ["low", "medium", "high", "max"]) == ("sonnet", "medium")
    assert tier_preset("claude", "max", "lead", models, ["low", "high"]) == ("opus", "")
    assert tier_preset("agy", "max", "code", [], ["high"]) == ("", "high")  # chưa biết model: CLI tự chọn


def test_save_onboard_writes_state_custom_and_project(tmp_path, monkeypatch):
    import importlib

    import ateam.config as cfgmod
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    cfgmod = importlib.reload(cfgmod)
    try:
        cfgmod.ensure_global_config()
        root = tmp_path / "proj"
        root.mkdir()

        def save(plan, **kw):
            opts = dict(full_access=True, approve_plan=False, auto_review=True, flow=True,
                        isolation="worktree", merge="review", verify_command="npm test")
            opts.update(kw)
            cfgmod.save_onboard(root, plan, **opts)

        save(cfgmod.plan_team({"lead": ("claude", "opus", "high"), "code": ("codex", "", "medium"),
                               "review": ("claude", "sonnet", "")}))
        c = cfgmod.load_config(root)
        assert c.lead == "claude" and c.agents["claude"].model == "opus"
        assert c.agents["claude"].full_access and c.agents["codex"].effort == "medium"
        assert "Trưởng nhóm" in c.agents["claude"].role and "Viết code" in c.agents["codex"].role
        rv = c.agents["claude-review"]
        assert rv.model == "sonnet" and rv.binary == "claude" and rv.full_access and rv.enabled
        assert cfgmod.load_custom()["agents"]["claude-review"]["wizard"] is True
        assert not c.agents["grok"].enabled and not c.agents["antigravity"].enabled
        assert not c.approve_plan and c.auto_review
        assert c.isolation == "worktree" and c.merge == "review" and c.verify.command == "npm test"
        assert c.default_workflow == "tinh-nang"
        assert c.workflows["tinh-nang"].steps[1].agent == "codex"  # bước "*" -> agent code chính
        assert not cfgmod.needs_setup()
        # chạy lại wizard: agent thêm lần trước bị xoá, không dồn; thiết lập trở về mặc định thì bỏ khỏi state
        save(cfgmod.plan_team({"lead": ("codex", "", ""), "code": ("codex", "", "")}), full_access=False,
             approve_plan=True, flow=False, isolation="shared", verify_command="")
        c = cfgmod.load_config(root)
        assert "claude-review" not in c.agents and c.lead == "codex" and not c.agents["claude"].enabled
        assert c.approve_plan and c.isolation == "shared" and c.default_workflow == ""
        assert "approve_plan" not in cfgmod.load_state() and not c.agents["codex"].full_access
    finally:
        monkeypatch.delenv("XDG_CONFIG_HOME")
        importlib.reload(cfgmod)


def test_grok_shell_denial_is_detected():
    """Câu grok thật in ra khi --deny Bash chặn lệnh (thoát 0) — phải nhận ra là bị chặn quyền."""
    from ateam.orchestrator import DENIED_RE
    real = [
        "`npm run lint` did not run. The shell is blocked in this session by a permission policy that denies bash.",
        "The shell command did not run. The permission policy blocked `echo hi > ran.txt`.",
        "Lệnh `git --version` không chạy được: bị chặn bởi permission policy (`deny rule on bash`).",
        "SUMMARY: Chạy `git --version` bị từ chối bởi deny rule trên bash; không có output.",
        "permission required: Execute `echo hi` was not run, as a headless run cannot ask for approval",
    ]
    for line in real:
        assert DENIED_RE.search(line), line
    for ok in ("Ran `git --version`; output was `git version 2.53.0`.", "SUMMARY: thêm kiểm tra quyền (permission) cho API"):
        assert not DENIED_RE.search(ok), ok


def test_form_models_from_any_agent_of_same_cli():
    """Form thêm agent: agent "opencode" có sẵn đang tắt (chưa hỏi CLI, chỉ có danh mục) nhưng agent tuỳ chỉnh cùng
    CLI đã có danh sách thật -> gợi ý đủ model thật, không chỉ 2 model trong danh mục."""
    from types import SimpleNamespace
    from ateam import wizard
    from ateam.config import AgentConfig
    real = [f"opencode/m{i}" for i in range(30)]
    cfg = SimpleNamespace(agents={
        "opencode": AgentConfig(name="opencode", command=["opencode", "run", "{prompt}"], models=["xai/grok-4.7"]),
        "deepseek": AgentConfig(name="deepseek", command=["opencode", "run", "{prompt}"], models=real),
        "claude": AgentConfig(name="claude", command=["claude", "-p", "{prompt}"], models=["opus"]),
    }, custom_agents={"deepseek"})
    for f in (wizard.quick_models, wizard.models_of):
        got = f(cfg, "opencode")
        assert got[:30] == real and "xai/grok-4.7" in got and "opus" not in got
    assert wizard.quick_models(SimpleNamespace(agents={}, custom_agents=set()), "opencode")  # danh mục


def test_prompts_keep_agents_focused(tmp_path, monkeypatch):
    """Prompt gọn: kế hoạch ít task + prompt ngắn; thành viên biết task song song và lệnh kiểm tra ateam tự chạy;
    review vòng cuối không viết task mới (sẽ bị bỏ)."""
    import importlib

    import ateam.config as cfgmod
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfgmod = importlib.reload(cfgmod)
    try:
        _check_focused_prompts(cfgmod.load_config(tmp_path / "proj"))
    finally:
        monkeypatch.undo()
        importlib.reload(cfgmod)


def _check_focused_prompts(cfg):
    plan = P.plan_prompt(cfg, "G", "/x", "")
    assert "as FEW tasks as possible" in plan and "Reply with ONLY a JSON array" in plan
    assert "To ask the user first" not in plan and "To ask the user first" in P.plan_prompt(cfg, "G", "/x", "", True)
    assert "as FEW tasks" in P.followup_plan_prompt(cfg, "G", "", "", "thêm", "/x", "")
    t = P.task_prompt(cfg, agent="codex", task_id=3, title="t", prompt="làm X", goal="G", deps=[], notes="",
                      cwd="/x", can_delegate=True, siblings=[(4, "claude", "Trang cài đặt")], verify_cmd="pytest -q")
    assert "#4 claude: Trang cài đặt" in t and "runs `pytest -q`" in t and "smallest change" in t
    assert "VERIFICATION COMMAND" not in t  # cụm này dành cho lượt sửa lỗi test (agent giả lập dựa vào)
    t = P.task_prompt(cfg, agent="codex", task_id=3, title="t", prompt="làm X", goal=None, deps=[], notes="",
                      cwd="/x", can_delegate=False)
    assert "OTHER TASKS" not in t and "Check your change" in t and "SUMMARY:" in t
    assert "new_tasks\" to []" in P.review_prompt(cfg, "G", 3, "r", "/x", final=True)
    r = P.review_prompt(cfg, "G", 1, "r", "/x")
    assert "Review round 1 of" in r and "ONLY for concrete bugs" in r


def test_results_text_marks_verified_tasks(env, project, monkeypatch):
    """Kết quả gửi trưởng nhóm review ghi task đã qua lệnh kiểm tra — trưởng nhóm khỏi chạy lại test."""
    from test_resume import _orch
    from conftest import ateam
    ateam(env, project, "verify", "true")
    o = _orch(env, project, monkeypatch)
    gid = o.db.add_goal("G")
    o.db.add_task("codex", "a", "a", goal_id=gid, status="done")
    o.db.add_task("codex", "b", "b", goal_id=gid, status="failed")
    text = o._results_text(gid)
    assert text.count("verification `true`: passed") == 1


def test_extract_code_block_and_answer():
    from ateam import prompts as P
    assert P.extract_code_block("x\n<<<CODE>>>\n\n    a = 1\n    b = 2\n\n<<<END>>>\n") == "    a = 1\n    b = 2"  # giữ thụt lề
    assert P.extract_code_block("<<<CODE>>>\n```python\nx\n```\n<<<END>>>") == "x"
    assert P.extract_code_block("<<<CODE>>>\nchưa xong") is None and P.extract_code_block("không có") is None
    # CLI in lại prompt (khối mẫu) trước câu trả lời: strip_echo bỏ phần đó, lấy khối cuối
    p = P.code_edit_prompt(path="a.py", language="Python", before="", selection="s", after="", instruction="i", cwd="/x")
    assert P.extract_code_block(P.strip_echo("user\n" + p + "\ncodex\n<<<CODE>>>\nthật\n<<<END>>>", p)) == "thật"
    assert P.extract_code_block(P.strip_echo("user\n" + p + "\n", p)) is None  # chỉ có prompt in lại: không bóc nhầm mẫu
    assert P.extract_answer("đọc...\nSUMMARY:\n**A**\n- b\n") == "**A**\n- b"
    assert P.extract_answer("chỉ có chữ") == "chỉ có chữ"


def test_overview_file_block_and_parser(tmp_path):
    """/init: .ateam/project.md có dòng meta; khối PROJECT OVERVIEW cắt dài, liệt kê file đã đổi; parser lấy khối cuối."""
    from ateam import overview
    assert overview.load(tmp_path) == ("", {}) and overview.block("", {}) == ""
    overview.save(tmp_path, "- Purpose: demo\n", "abc123")
    text, meta = overview.load(tmp_path)
    assert text == "- Purpose: demo" and meta["commit"] == "abc123" and meta["date"]
    b = overview.block(text, meta, [f"f{i}.py" for i in range(45)], 7)
    assert b.startswith("PROJECT OVERVIEW") and "(7 commits): f0.py" in b and "f39.py, … (+5 more)" in b
    assert "truncated" in overview.block("x" * (overview.MAX_CHARS + 5), {})
    (tmp_path / ".ateam/project.md").write_text("người dùng tự viết\n")  # không có meta vẫn đọc được
    assert overview.load(tmp_path) == ("người dùng tự viết", {})
    p = P.init_prompt(cwd="/x")
    assert P.extract_overview(P.strip_echo("user\n" + p + "\n", p)) is None  # chỉ có prompt in lại: không lấy mẫu "..."
    assert P.extract_overview("đọc...\n<<<OVERVIEW>>>\n```markdown\n- a\n```\n<<<END>>>") == "- a"
    assert P.extract_overview("<<<OVERVIEW>>>\nchưa xong") is None
    assert "CURRENT OVERVIEW:\n- a" in P.init_prompt(cwd="/x", current="- a", changes="1 commits")
    # khối code ở hai đầu của chính bản tổng quan: không bóc nhầm thành rào bọc ngoài
    both = "```bash\nnpm i\n```\n- x\n```\ny\n```"
    assert P.extract_overview(f"<<<OVERVIEW>>>\n{both}\n<<<END>>>") == both
    assert P.extract_overview("<<<OVERVIEW>>>\n```markdown\n- a\n```bash\nx\n```\n```\n<<<END>>>") == "- a\n```bash\nx\n```"
    # thay đổi gửi khi cập nhật có giới hạn (prompt đi qua argv)
    status = "\n".join(f"?? f{i}" for i in range(80))
    t = overview.changes_text(3, [f"a{i}.py" for i in range(250)], status)
    assert t.startswith("3 commits; files changed: a0.py") and "a199.py, … (+50 more)" in t and "a200.py" not in t
    assert "?? f49\n… (+30 more)" in t and "?? f50" not in t
    assert overview.changes_text(None, [], "") == ""
    # AGENTS.md mọi CLI tự nạp: không chép lại; /init không cài / build / chạy test
    assert "do NOT repeat" in P.init_prompt(cwd="/x", native=["AGENTS.md", "CLAUDE.md"])
    assert "do NOT repeat" not in P.init_prompt(cwd="/x", native=["CLAUDE.md"])
    assert "do not install dependencies, build or run tests" in P.init_prompt(cwd="/x")


def test_prompts_use_overview_only_when_present():
    from ateam.config import Config
    cfg = Config()
    ov = "PROJECT OVERVIEW (x):\n- Test: pytest"
    assert P.plan_prompt(cfg, "G", "/x", "", overview="") == P.plan_prompt(cfg, "G", "/x", "")
    plan = P.plan_prompt(cfg, "G", "/x", "", overview=ov)
    assert "- Test: pytest" in plan and "Rely on the PROJECT OVERVIEW" in plan and "do not read the whole" not in plan
    assert "Rely on the PROJECT" in P.followup_plan_prompt(cfg, "G", "", "", "thêm", "/x", "", overview=ov)
    assert "- Test: pytest" in P.grill_prompt(cfg, "G", [], "/x", "", finish=False, max_questions=5, overview=ov)
    kw = dict(agent="codex", task_id=1, title="t", prompt="p", goal="G", deps=[], notes="", cwd="/x",
              can_delegate=False)
    t = P.task_prompt(cfg, overview=ov, **kw)
    assert "- Test: pytest" in t and "Use the PROJECT OVERVIEW" in t
    assert "PROJECT OVERVIEW" not in P.task_prompt(cfg, **kw)
    assert "do not repeat it in task prompts" in plan
    assert "<<<NOTE>>>your note<<<END>>>" in t and "short fact" in t  # parse_notes vẫn lọc câu mẫu


def test_fix_prompts_do_not_run_whole_suite_twice():
    """ateam tự chạy lại lệnh kiểm tra sau mỗi lượt sửa: agent chỉ chạy lại test đang fail."""
    kw = dict(command="pytest -q", rc=1, output="FAILED t", attempt=1, max_attempts=2)
    for p in (P.fix_resume_prompt(**kw),
              P.fix_prompt(agent="codex", task_id=1, title="t", prompt="p", cwd="/x", original_agent="claude", **kw)):
        assert "VERIFICATION COMMAND: pytest -q" in p and "Run the command yourself" not in p
        assert "re-run only the failing tests" in p


def test_notes_and_overview_block_in_orchestrator(tmp_path):
    """Ghi chú agent dài bị cắt trong prompt (ghi chú người dùng, /compact giữ nguyên); phiên trưởng nhóm đã nhận bản
    tổng quan thì lượt tiếp phiên chỉ nhận một dòng nhắc, đổi bản tổng quan thì gửi lại cả bản."""
    import asyncio

    from ateam import overview
    from ateam.config import Config
    from ateam.db import DB
    from ateam.orchestrator import NOTE_MAX, Orchestrator
    db = DB(tmp_path / ".ateam/team.db")
    cfg = Config()
    cfg.agents["claude"] = AgentConfig("claude", ["claude", "-p", "{prompt}"])
    o = Orchestrator(tmp_path, cfg, db)
    db.add_note("codex", "x" * (NOTE_MAX + 300))
    db.add_note("user", "u" * (NOTE_MAX + 300))
    notes = o.notes_text()
    assert "x" * NOTE_MAX + "…" in notes and "x" * (NOTE_MAX + 1) not in notes and "u" * (NOTE_MAX + 300) in notes

    assert asyncio.run(o.overview_block(session="s1")) == ""  # chưa có bản tổng quan
    overview.save(tmp_path, "- Test: pytest", "")
    full = asyncio.run(o.overview_block(session="s1"))
    assert full.startswith("PROJECT OVERVIEW") and "- Test: pytest" in full
    gid = db.add_goal("G")
    db.update_goal(gid, lead_session="s1", lead_session_agent="claude")
    assert o._lead_session(db.goal(gid)) == "s1"
    o._overview_seen(gid, full)
    assert asyncio.run(o.overview_block(session="s1")) == overview.SEEN
    assert asyncio.run(o.overview_block(session="s2")) == full  # phiên khác chưa nhận
    overview.save(tmp_path, "- Test: make test", "")
    assert "make test" in asyncio.run(o.overview_block(session="s1"))  # bản mới: gửi lại cả bản
    db.update_goal(gid, lead_session_agent="codex")  # phiên của agent khác: trưởng nhóm không tiếp tục được
    assert o._lead_session(db.goal(gid)) is None


def _orch_unit(tmp_path):
    from ateam.config import Config
    from ateam.db import DB
    from ateam.orchestrator import Orchestrator
    cfg = Config()
    cfg.agents["claude"] = AgentConfig("claude", ["claude", "-p", "{prompt}"], effort_args=["--effort", "{effort}"],
                                       efforts=["low", "medium", "high"], effort="high")
    cfg.agents["codex"] = AgentConfig("codex", ["codex", "exec", "{prompt}"])
    cfg.lead = "claude"
    return Orchestrator(tmp_path, cfg, DB(tmp_path / ".ateam/team.db"))


def test_prompt_starting_with_dash_is_not_a_flag(tmp_path):
    """Tin chat / `/task` gửi nguyên văn: "- sửa nút" (gạch đầu dòng) không được để CLI hiểu là cờ."""
    o = _orch_unit(tmp_path)
    for name in ("claude", "codex"):
        argv = o.argv_for(o.cfg.agents[name], "- sửa nút\n- thêm test", tmp_path)
        assert " - sửa nút\n- thêm test" in argv and not any(x.startswith("- ") for x in argv), argv
    assert "làm X" in o.argv_for(o.cfg.agents["codex"], "làm X", tmp_path)


def test_insert_plan_odd_and_circular_dependencies(tmp_path):
    """depends_on là số / chuỗi / phần tử lạ không làm hỏng lập kế hoạch; vòng phụ thuộc bị bỏ (không thì treo mãi)."""
    o = _orch_unit(tmp_path)
    gid = o.db.add_goal("G")
    plan = [{"id": 1, "agent": "codex", "title": "A", "prompt": "a", "depends_on": [2]},
            {"id": 2, "agent": "codex", "title": "B", "prompt": "b", "depends_on": [1]},
            {"id": 3, "agent": "codex", "title": "C", "prompt": "c", "depends_on": 1},
            {"id": 4, "agent": "codex", "title": "D", "prompt": "d", "depends_on": "2"},
            {"id": 5, "agent": "codex", "title": "E", "prompt": "e", "depends_on": [[1], {"x": 1}, 4]}]
    ids = o._insert_plan(gid, plan, source="plan")
    deps = {t.title: [ids.index(d) + 1 for d in t.depends_on] for t in o.db.tasks(goal_id=gid)}
    assert deps == {"A": [2], "B": [], "C": [1], "D": [2], "E": [4]}, deps
    assert "Bỏ phụ thuộc vòng" in (tmp_path / ".ateam/logs/system.log").read_text()


def test_commit_message_quick_effort_and_bounded_untracked(tmp_path, monkeypatch):
    """Viết commit message: chạy effort low (lượt nhanh), danh sách file chưa track có giới hạn (prompt đi qua argv);
    giải thích code cũng effort low, ⌘I sửa code giữ effort của agent."""
    import asyncio
    import subprocess

    from ateam.orchestrator import UNTRACKED_MAX
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x"],
                   cwd=tmp_path, check=True)
    for i in range(UNTRACKED_MAX + 200):
        (tmp_path / f"f{i}.txt").write_text("x")
    o = _orch_unit(tmp_path)
    calls = []

    async def fake_lead(prompt, label, first="", goal_id=None, keep_session=False, slow=False, effort=None):
        calls.append((prompt, effort))
        return "SUMMARY:\n<<<CODE>>>\nx\n<<<END>>>\nthêm file"
    monkeypatch.setattr(o, "_call_lead", fake_lead)
    ok, _msg = asyncio.run(o.commit_message())
    prompt, effort = calls[-1]
    assert ok and effort == "low" and "… (+200 more)" in prompt and prompt.count(".txt") == UNTRACKED_MAX
    asyncio.run(o.code_ai("explain", "a.py", "x = 1\n", 0, 5))
    assert calls[-1][1] == "low"
    asyncio.run(o.code_ai("edit", "a.py", "x = 1\n", 0, 5, instruction="đổi tên"))
    assert calls[-1][1] is None
    # effort riêng của lượt đi tới argv thay effort "high" của agent
    argv = o.argv_for(o.cfg.agents["claude"], "p", tmp_path, plan=True, effort="low")
    assert argv[argv.index("--effort") + 1] == "low"



def test_apply_checks_final_check_and_quality_presets(tmp_path):
    """Kiểm tra cuối chỉ thêm khi có lệnh verify và ≥2 task song song (chuỗi tuần tự: task cuối đã kiểm tra kết quả
    gộp); preset Nhanh bỏ review, Chặt chẽ thêm review cho kế hoạch mới (không cho vòng review)."""
    from ateam.config import task_kind
    o = _orch_unit(tmp_path)
    kinds = (lambda plan: [task_kind(x.get("type")) for x in plan])
    par = [{"id": 1, "agent": "codex", "title": "A", "prompt": "a"},
           {"id": 2, "agent": "claude", "title": "B", "prompt": "b"}]
    chain = [{"agent": "codex", "title": "A", "prompt": "a"},
             {"agent": "claude", "title": "B", "prompt": "b", "depends_on": [1]}]
    rev = par + [{"id": 3, "type": "review", "agent": "claude", "title": "R", "prompt": "r", "depends_on": [1, 2]}]
    assert o._apply_checks(par, "plan") == par  # chưa có lệnh verify: không có gì để kiểm tra
    o.cfg.verify.command = "pytest -q"
    out = o._apply_checks(par, "plan")
    assert kinds(out) == ["code", "code", "verify"] and out[2]["depends_on"] == [1, 2] and out[2]["agent"] == "claude"
    out = o._apply_checks(chain, "plan")
    assert kinds(out) == ["code", "code"] and [x["id"] for x in out] == [1, 2]
    assert o._apply_checks(rev, "plan")[-1]["depends_on"] == [1, 2, 3]
    own = par + [{"id": 9, "type": "verify", "agent": "codex", "title": "V", "depends_on": [1, 2]}]
    assert kinds(o._apply_checks(own, "plan")) == ["code", "code", "verify"]  # trưởng nhóm đã thêm: không thêm nữa
    o.cfg.quality = "fast"
    assert kinds(o._apply_checks(rev, "plan")) == ["code", "code", "verify"]
    o.cfg.quality = "strict"
    out = o._apply_checks(chain, "plan")
    assert kinds(out) == ["code", "code", "review"] and out[2]["depends_on"] == [1, 2] and out[2]["agent"] == "claude"
    assert kinds(o._apply_checks(chain, "review")) == ["code", "code"]

    # chèn vào DB: loại task, phụ thuộc của kiểm tra cuối; review cuối được báo task nào do kiểm tra cuối bao
    o.cfg.quality = "auto"
    gid = o.db.add_goal("G")
    ids = o._insert_plan(gid, rev, source="plan")
    ts = o.db.tasks(goal_id=gid)
    assert [t.kind for t in ts] == [None, None, "review", "verify"] and ts[3].depends_on == ids[:3]
    assert f"(checked by final verify #{ids[3]}: draft)" in o._results_text(gid)
    assert "verification `pytest -q`: passed" not in o._results_text(gid)
    # preset Nhanh chỉ bỏ review cuối khi mục tiêu "sạch": có task review thì không
    for t in ts:
        o.db.update_task(t.id, status="done")
    assert not o._clean(o.db.tasks(goal_id=gid))
    o.db.update_task(ids[2], status="cancelled")
    assert not o._clean(o.db.tasks(goal_id=gid))
    o.db.delete([ids[2]], [])
    assert o._clean(o.db.tasks(goal_id=gid))
    o.cfg.verify.command = ""
    assert not o._clean(o.db.tasks(goal_id=gid))  # không có lệnh kiểm tra: review cuối là lớp kiểm tra duy nhất


def test_plan_and_task_prompts_follow_quality_preset():
    from ateam.config import Config
    cfg = Config()
    p = P.plan_prompt(cfg, "G", "/w", "")
    assert '"type": "code"' in p and 'Code review: only for risky' in p and "Do NOT create separate tasks" not in p
    assert "each member runs the tests related to its change" in p
    cfg.verify.command = "pytest -q"
    assert "ateam runs `pytest -q` after each task" in P.plan_prompt(cfg, "G", "/w", "")
    cfg.quality = "fast"
    p = P.plan_prompt(cfg, "G", "/w", "")
    assert "Code review" not in p and "only for risky logic" in p
    cfg.quality = "strict"
    assert "Code review: REQUIRED" in P.followup_plan_prompt(cfg, "G", "", "", "thêm", "/w", "")
    tp = P.task_prompt(cfg, agent="claude", task_id=3, title="R", prompt="r", goal="G",
                       deps=[(1, "codex", "A", "ok")], notes="", cwd="/w", can_delegate=True, kind="review",
                       diff="`git diff HEAD`", handoff=True)
    assert "You REVIEW the work of the tasks you depend on" in tp and "`git diff HEAD`" in tp and "~40 lines" in tp
    tp = P.task_prompt(cfg, agent="codex", task_id=1, title="A", prompt="a", goal="G", deps=[], notes="", cwd="/w",
                       can_delegate=True)
    assert "You REVIEW" not in tp and "~40 lines" not in tp
    assert "PROJECT OVERVIEW" in P.review_prompt(cfg, "G", 1, "r", "/x", overview="PROJECT OVERVIEW\n- x")
    fp = P.check_fix_prompt(agent="claude", task_id=4, goal="G", note="", tasks=[(1, "codex", "A")], command="make",
                            rc=1, output="boom", attempt=1, max_attempts=2, cwd="/w")
    assert "final check #4" in fp and "- #1 by codex: A" in fp and "VERIFICATION COMMAND: make" in fp


def test_old_db_without_task_kind_opens(tmp_path):
    import sqlite3

    from ateam.db import DB
    path = tmp_path / "old.db"
    c = sqlite3.connect(str(path))
    c.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, goal_id INTEGER, parent_id INTEGER,"
              " agent TEXT NOT NULL, title TEXT NOT NULL, prompt TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',"
              " depends_on TEXT NOT NULL DEFAULT '[]', depth INTEGER NOT NULL DEFAULT 0, source TEXT, result TEXT,"
              " error TEXT, branch TEXT, created REAL, started REAL, finished REAL)")
    c.execute("INSERT INTO tasks(agent, title, prompt) VALUES ('codex', 't', 'p')")
    c.commit()
    c.close()
    db = DB(path)
    assert db.task(1).kind is None
    assert db.task(db.add_task("claude", "Kiểm tra cuối", "", kind="verify")).kind == "verify"


def test_workflow_step_type_roundtrip(tmp_path, monkeypatch):
    """Loại bước workflow: TOML "type" ↔ WorkflowStep.kind ↔ kế hoạch; form (wizard) giữ loại; lạ = code."""
    from ateam import wizard
    from ateam.config import Config, Workflow, WorkflowStep, workflow_to_dict
    w = Workflow("w", steps=[WorkflowStep(agent="codex", title="A"), WorkflowStep(agent="lead", title="V", kind="verify")])
    raw = workflow_to_dict(w)
    assert "type" not in raw["steps"][0] and raw["steps"][1]["type"] == "verify"
    assert [p["type"] for p in w.plan("G", "claude")] == ["code", "verify"] and "lead (verify)" in w.summary()
    body = wizard.workflow_body(Config(), "w2", None, "", True, [{"agent": "lead", "title": "R", "type": "review"},
                                                              {"agent": "lead", "title": "X", "type": "lạ"}])
    assert body["steps"][0]["type"] == "review" and "type" not in body["steps"][1]
