"""Kiểm tra cú pháp mọi lệnh agent qua --help; không chạy prompt, models hay usage thật."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field, replace
from pathlib import Path

from .config import AgentConfig, help_command, unknown_flags
from .i18n import tr
from .opencode import catalog_argv, standard_models


@dataclass
class CommandIssue:
    help_argv: list[str]
    flags: list[str] = field(default_factory=list)
    error: str = ""


def command_examples(a: AgentConfig, root: Path) -> list[list[str]]:
    """Cả lệnh đang dùng lẫn cờ được chèn khi chọn model/effort hoặc tiếp tục phiên."""
    model = (a.model or (a.models[0] if a.models else "model")).partition("#")[0]
    effort = a.effort or next(iter(a.efforts_for(model)), "medium")
    probe = replace(a, model=model, effort=effort, no_effort=set(), model_efforts={model: [effort]})
    commands = [a.argv("{prompt}"), replace(probe, effort="").argv("{prompt}"), probe.argv("{prompt}")]
    session = "00000000-0000-4000-8000-000000000001"
    for plan in ([False, True] if a.plan_command else [False]):
        commands.append(probe.argv("{prompt}", plan=plan))
        if a.session_flags(False):
            commands.append(probe.argv("{prompt}", plan=plan, session=session))
        if a.can_resume():
            commands.append(probe.argv("{prompt}", plan=plan, session=session, resume=True))
    interactive = a.interactive_argv("{session}")
    if interactive:
        commands.append(interactive)
    if a.models_command:
        commands.append(catalog_argv(a.binary, root) if (a.opencode_major or 0) >= 2 and standard_models(a)
                        else list(a.models_command))
    if a.usage_command:
        commands.append(list(a.usage_command))
    return commands


def inspect_commands(a: AgentConfig, root: Path, cache: dict | None = None) -> list[CommandIssue]:
    """Dùng chung cache trợ giúp giữa các alias, trả mọi lỗi thay vì dừng ở cờ đầu tiên."""
    cache = {} if cache is None else cache
    issues, seen = [], set()
    for command in command_examples(a, root):
        hc = help_command(command)
        key = tuple(hc)
        if key not in cache:
            if not shutil.which(hc[0]):
                cache[key] = ("", tr("chưa cài lệnh '{v}'", v=hc[0]))
            else:
                try:
                    r = subprocess.run(hc, cwd=root, stdin=subprocess.DEVNULL, capture_output=True,
                                       text=True, timeout=15)
                    error = tr("trợ giúp thoát với mã {code}", code=r.returncode) if r.returncode else ""
                    text = (r.stdout or "") + (r.stderr or "")
                    cache[key] = (text, error or (tr("trợ giúp không có nội dung") if not text.strip() else ""))
                except subprocess.TimeoutExpired:
                    cache[key] = ("", tr("hết thời gian đọc trợ giúp"))
                except OSError:
                    cache[key] = ("", tr("không chạy được lệnh trợ giúp"))
        text, error = cache[key]
        flags = unknown_flags(command, text) if not error else []
        sig = (key, tuple(flags), error)
        if (error or flags) and sig not in seen:
            seen.add(sig)
            issues.append(CommandIssue(hc, flags, error))
    return issues
