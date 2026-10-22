"""Hạ tầng test: chạy `python -m ateam` với các agent giả lập trong tests/fakebin.

Mỗi test có cấu hình (XDG_CONFIG_HOME), thư mục dự án và trạng thái hạn mức riêng,
nên không đụng tới ~/.config/ateam của máy thật.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# test so chuỗi tiếng Việt: cố định ngôn ngữ (test tiếng Anh tự đặt ATEAM_LANG=en)
os.environ["ATEAM_LANG"] = "vi"
FAKEBIN = Path(__file__).resolve().parent / "fakebin"


@pytest.fixture
def env(tmp_path) -> dict:
    e = dict(os.environ)
    e["PATH"] = f"{FAKEBIN}{os.pathsep}{e.get('PATH', '')}"
    e["XDG_CONFIG_HOME"] = str(tmp_path / "xdg")
    e["ATEAM_FAKE_LIMIT_DIR"] = str(tmp_path / "limits")
    e["ATEAM_FAKE_ARGS_LOG"] = str(tmp_path / "args.log")
    e["ATEAM_FAKE_SLOW"] = "0"
    e["ATEAM_LANG"] = "vi"
    e["ATEAM_DESKTOP_NOTIFY"] = "0"  # không hiện thông báo macOS thật khi task giả lập lỗi
    e["CODEX_HOME"] = str(tmp_path / "codex")  # không đọc phiên codex thật của máy (/usage)
    e["GROK_HOME"] = str(tmp_path / "grok")  # /usage: không đọc phiên grok thật của máy
    e["CLAUDE_CONFIG_DIR"] = str(tmp_path / "claude")  # phiên Claude giả lập (dashboard), không đọc của máy
    e["PYTHONPATH"] = str(ROOT)
    for k in ("ATEAM_DB", "ATEAM_ROOT", "ATEAM_TASK_ID", "ATEAM_AGENT"):
        e.pop(k, None)
    (tmp_path / "limits").mkdir()
    return e


@pytest.fixture
def project(tmp_path) -> Path:
    p = tmp_path / "proj"
    p.mkdir()
    return p


def ateam(env: dict, cwd: Path, *args: str, timeout: int = 120,
          check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run([sys.executable, "-m", "ateam", *args], cwd=cwd, env=env,
                       capture_output=True, text=True, timeout=timeout)
    if check and r.returncode not in (0, 2):
        raise AssertionError(f"ateam {args} -> {r.returncode}\n{r.stdout}\n{r.stderr}")
    return r


def git_init(path: Path) -> None:
    def g(*a):
        subprocess.run(["git", *a], cwd=path, check=True, capture_output=True)
    g("init", "-q")
    (path / "base.txt").write_text("base\n")
    g("add", ".")
    g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")


async def wait_for(pilot, cond, timeout: float = 20) -> bool:
    """TUI: chờ tới khi cond() đúng — CI chậm có thể mất vài giây mới đẩy xong popup; xong sớm thì thoát sớm."""
    for _ in range(int(timeout / 0.1)):
        await pilot.pause(0.1)
        if cond():
            return True
    return False


def write_project_config(project: Path, text: str) -> None:
    (project / ".ateam").mkdir(exist_ok=True)
    (project / ".ateam" / "config.toml").write_text(text, encoding="utf-8")


def tasks(project: Path) -> list:
    sys.path.insert(0, str(ROOT))
    from ateam.db import DB
    return DB(project / ".ateam" / "team.db").tasks()
