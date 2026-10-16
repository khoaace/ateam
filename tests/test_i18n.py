"""Đa ngôn ngữ (vi/en): bản dịch đủ và khớp placeholder, không còn chữ tiếng Việt hiển thị ngoài tr(),
CLI và TUI chạy bằng tiếng Anh, /lang lưu lựa chọn rồi mở lại app."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

from conftest import ROOT, ateam

PKG = ROOT / "ateam"
VI = re.compile(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", re.I)
PH = re.compile(r"\{(\w+)[^{}]*\}")
# chữ tiếng Việt cố ý không dịch: nội dung gửi agent / ghi vào file cấu hình, từ khoá lệnh người dùng gõ
SKIP_FILES = {"prompts.py", "i18n.py", "en.py"}
SKIP_NAMES = {"DEFAULT_CONFIG", "EXTRA_AGENT_TEMPLATES", "WORKFLOW_TEMPLATES", "CATALOG", "ROLES", "CSS",
              "DEFAULT_CSS", "FORM_CSS", "ACCENT_ALIASES"}


def _sources():
    for p in sorted(PKG.rglob("*.py")):
        if p.name not in SKIP_FILES:
            yield p, ast.parse(p.read_text(encoding="utf-8"))


def _tr_keys():
    for p, tree in _sources():
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and getattr(n.func, "id", "") == "tr" and n.args
                    and isinstance(n.args[0], ast.Constant)):
                yield p, n.lineno, n.args[0].value


def test_every_tr_string_has_an_english_translation():
    from ateam.locales.en import EN
    missing = [f"{p.name}:{ln}: {k[:70]!r}" for p, ln, k in _tr_keys() if k not in EN]
    assert not missing, "Thiếu bản dịch (thêm vào ateam/locales/en.py):\n" + "\n".join(missing)
    bad = [k[:70] for k in EN if set(PH.findall(k)) != set(PH.findall(EN[k]))]
    assert not bad, f"Placeholder vi/en không khớp: {bad}"
    for k, v in EN.items():
        assert not VI.search(v), f"Bản dịch còn chữ tiếng Việt: {v[:70]!r}"


def test_no_vietnamese_ui_string_outside_tr():
    leaks = []
    for p, tree in _sources():
        parents = {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
        docs = set()
        for n in ast.walk(tree):
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body:
                f = n.body[0]
                if isinstance(f, ast.Expr) and isinstance(f.value, ast.Constant):
                    docs.add(f.value)
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Constant) and isinstance(n.value, str) and VI.search(n.value)) or n in docs:
                continue
            cur, ok = n, False
            while cur in parents:
                par = parents[cur]
                if isinstance(par, ast.Call) and getattr(par.func, "id", "") == "tr" and par.args \
                        and par.args[0] is cur:
                    ok = True
                if isinstance(par, ast.Compare):  # từ khoá lệnh: /grill xong, /verify tắt…
                    ok = True
                if isinstance(par, ast.Call) and getattr(par.func, "attr", "") == "compile":
                    ok = True
                if isinstance(par, (ast.Assign, ast.AnnAssign)):
                    tgts = par.targets if isinstance(par, ast.Assign) else [par.target]
                    names = {x.id for t in tgts for x in ast.walk(t) if isinstance(x, ast.Name)}
                    names |= {x.attr for t in tgts for x in ast.walk(t) if isinstance(x, ast.Attribute)}
                    if names & SKIP_NAMES:
                        ok = True
                if ok:
                    break
                cur = par
            if not ok:
                leaks.append(f"{p.relative_to(ROOT)}:{n.lineno}: {n.value[:60]!r}")
    allowed = {"trống"}  # tên mẫu agent (khoá dict EXTRA_AGENT_TEMPLATES) so sánh trong form
    leaks = [x for x in leaks if not any(f": {a!r}" in x for a in allowed)]
    assert not leaks, "Chữ tiếng Việt chưa bọc tr():\n" + "\n".join(leaks)


def test_detect_and_save_language(tmp_path, monkeypatch):
    from ateam import i18n
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("ATEAM_LANG", raising=False)
    for k in ("LC_ALL", "LC_MESSAGES"):  # runner macOS đặt sẵn LC_ALL, được ưu tiên hơn LANG
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert i18n.detect_lang([]) == "en"  # máy mới, LANG tiếng Anh
    monkeypatch.setenv("LANG", "vi_VN.UTF-8")
    assert i18n.detect_lang([]) == "vi"
    state = tmp_path / "xdg" / "ateam" / "state.json"
    state.parent.mkdir(parents=True)
    state.write_text('{"onboarded": 1}')
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert i18n.detect_lang([]) == "vi"  # người dùng cũ chưa chọn: giữ tiếng Việt như trước
    i18n.save_lang("en")
    assert json.loads(state.read_text()) == {"onboarded": 1, "lang": "en"}
    assert i18n.detect_lang([]) == "en"
    assert i18n.detect_lang(["ateam", "--lang", "vi"]) == "vi"
    monkeypatch.setenv("ATEAM_LANG", "vi")
    assert i18n.detect_lang([]) == "vi"
    old = i18n.get_lang()
    try:
        i18n.set_lang("en")
        assert i18n.tr("Đã merge #{tid}", tid=7) == "Merged #7"
        assert i18n.tr("chuỗi chưa có bản dịch {x}", x=1) == "chuỗi chưa có bản dịch 1"
        i18n.set_lang("vi")
        assert i18n.tr("Đã merge #{tid}", tid=7) == "Đã merge #7"
    finally:
        i18n.set_lang(old)


def test_cli_in_english(env, project):
    r = ateam(env, project, "--lang", "en", "doctor", check=False)
    assert "Config:" in r.stdout and "Cấu hình" not in r.stdout
    r = ateam(env, project, "--lang", "en", "--help")
    assert "check which agents are installed" in r.stdout
    ateam(dict(env, ATEAM_LANG=""), project, "lang", "en")
    state = json.loads((Path(env["XDG_CONFIG_HOME"]) / "ateam" / "state.json").read_text())
    assert state["lang"] == "en"
    r = ateam(dict(env, ATEAM_LANG=""), project, "list")
    r2 = ateam(dict(env, ATEAM_LANG=""), project, "lang")
    assert "English" in r2.stdout and "change with" in r2.stdout


TUI_SCRIPT = r"""
import asyncio, json, sys
from pathlib import Path
from ateam.config import ensure_global_config, load_config
from ateam.db import DB
from ateam.tui import TeamApp, help_text
root = Path(sys.argv[1])
async def main():
    ensure_global_config()
    app = TeamApp(root, load_config(root), DB(root / ".ateam/team.db"))
    out = {}
    async with app.run_test(size=(150, 45)) as pilot:
        await pilot.pause(0.3)
        out["tabs"] = [str(t.label) for t in app.query("Tab")]
        out["placeholder"] = app.query_one("#cmd").placeholder
        out["help"] = help_text().plain[:400]
        app.run_command("/lang vi")
        await pilot.pause(0.5)
        out["restart"] = app.restart_requested
    print(json.dumps(out, ensure_ascii=False))
asyncio.run(main())
"""


def test_tui_in_english_and_lang_switch(env, project, tmp_path):
    script = tmp_path / "tui_en.py"
    script.write_text(TUI_SCRIPT)
    e = dict(env, ATEAM_LANG="en")
    r = subprocess.run([sys.executable, str(script), str(project)], env=e, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert any("Board" in t for t in out["tabs"]) and any("Team" in t for t in out["tabs"])
    assert "Type a goal" in out["placeholder"]
    assert "Assigning work:" in out["help"] and "/task <agent> <content>" in out["help"]
    # /lang vi: lưu rồi xin mở lại app (cli.cmd_tui exec lại tiến trình)
    assert out["restart"] is True
    state = json.loads((Path(env["XDG_CONFIG_HOME"]) / "ateam" / "state.json").read_text())
    assert state["lang"] == "vi"
