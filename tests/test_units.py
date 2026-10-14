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


def test_parse_models_from_cli_listing():
    from ateam.config import parse_models
    out = "Available models:\n  gemini-3-pro      (default)\n- gemini-3-flash\n\nNAME\nxai/grok-4.7\nxai/grok-4.7\n"
    assert parse_models(out) == ["gemini-3-pro", "gemini-3-flash", "xai/grok-4.7"]
    assert parse_models(out, "grok") == ["xai/grok-4.7"]


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
