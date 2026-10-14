"""Cấu hình: mặc định < ~/.config/ateam/config.toml < .ateam/config.toml < state.json (model/effort chọn trong app)."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

GLOBAL_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ateam"
GLOBAL_CONFIG = GLOBAL_DIR / "config.toml"
STATE_FILE = GLOBAL_DIR / "state.json"
CONFIG_VERSION = 3
PROMPT_FLAGS = ("-p", "--print", "--prompt")

DEFAULT_CONFIG = """\
# ============================================================
#  AI Team — cấu hình
#  File chung:   ~/.config/ateam/config.toml
#  File dự án:   <dự án>/.ateam/config.toml  (ghi đè file chung)
#  Model / effort đổi trong app (/model, /effort) được lưu ở ~/.config/ateam/state.json
#  và ưu tiên hơn giá trị trong file này. Gõ /model <agent> - để quay về giá trị ở đây.
# ============================================================
config_version = 3

lead = "claude"              # agent làm trưởng nhóm (lập kế hoạch + review)
max_parallel = 3             # tổng số task chạy song song tối đa
approve_plan = true          # true: kế hoạch ở trạng thái "nháp", gõ /go để chạy
auto_review = true           # trưởng nhóm review kết quả và giao thêm việc nếu cần
max_rounds = 3               # số vòng review tối đa cho 1 mục tiêu
max_delegation_depth = 2     # agent giao việc cho agent khác tối đa mấy tầng
lead_sets_effort = true      # trưởng nhóm được chọn effort cho từng task trong kế hoạch
# "shared"   : mọi agent làm chung 1 thư mục (đơn giản)
# "worktree" : mỗi task một git worktree riêng, xong thì tự merge (an toàn khi chạy song song)
isolation = "shared"
# Chỉ áp dụng khi isolation = "worktree":
# "auto"   : task xong (và qua test) thì tự merge
# "review" : task dừng ở trạng thái "chờ duyệt" — xem diff bằng /diff, rồi /merge hoặc /reject
merge = "auto"

[verify]
# Lệnh kiểm tra chạy sau mỗi task có thay đổi code. Để trống = tắt.
# Đặt riêng cho từng dự án ngay trong app: /verify npm test   (tắt: /verify off)
command = ""                 # vd: "npm test", "pytest -q", "make check", "cargo test"
timeout = 600                # giây
max_fix_attempts = 2         # test fail thì giao sửa tối đa mấy lần
fix_agent = ""               # "" = agent làm task tự sửa; hoặc tên agent khác (vd "codex")
only_when_changed = true     # bỏ qua nếu task không thay đổi file nào

[limits]
# Khi một agent báo hết hạn mức (rate limit / usage limit): agent đó tạm nghỉ và task được
# chuyển cho agent trong danh sách "fallback" của nó (nếu có agent đang rảnh hạn mức).
cooldown_minutes = 30        # dùng khi CLI không nói rõ lúc nào hạn mức hồi lại
lead_fallback = ["codex"]    # ai lập kế hoạch/review thay khi trưởng nhóm hết hạn mức

# ------------------------------------------------------------
# Mỗi agent:
#   command       lệnh chạy headless; {prompt} = nội dung task
#   model         model mặc định ("" = để CLI tự chọn)
#   effort        mức suy luận mặc định ("" = để CLI tự chọn)
#   model_args    cờ thêm vào khi có model  ({model} được thay)
#   effort_args   cờ thêm vào khi có effort ({effort} được thay)
#   efforts       các mức effort hợp lệ (dùng để kiểm tra và gợi ý)
#   models        model gợi ý trong /model và tab Đội (vắng = danh mục có sẵn của ateam)
#   models_command  lệnh liệt kê model thật của CLI (vd ["opencode", "models"]);
#                 models_filter: chỉ giữ model chứa chữ này (vắng = tên agent nếu có model khớp)
#   role          thế mạnh -> trưởng nhóm dựa vào đây để phân việc
#   timeout       giây;  max_concurrent: số task cùng lúc;  pty: chạy trong terminal giả
#   fallback      agent thay thế khi agent này hết hạn mức
#   verify        false = không chạy lệnh kiểm tra sau task của agent này (vd agent chỉ nghiên cứu)
# ------------------------------------------------------------

[agents.claude]
# acceptEdits: được sửa file. Cho chạy cả lệnh shell: đổi thành "bypassPermissions" (chỉ repo tin tưởng)
command = ["claude", "-p", "{prompt}", "--permission-mode", "acceptEdits"]
model = ""                   # vd: "opus", "sonnet", "haiku" hoặc id đầy đủ
effort = ""
model_args = ["--model", "{model}"]
effort_args = ["--effort", "{effort}"]
efforts = ["low", "medium", "high", "max"]
fallback = ["codex"]
role = "Trưởng nhóm. Lập kế hoạch, thiết kế kiến trúc, review code, các việc cần suy luận sâu."
timeout = 1800
max_concurrent = 1

[agents.codex]
# --full-auto: sửa file + chạy lệnh trong sandbox của Codex
command = ["codex", "exec", "--full-auto", "--skip-git-repo-check", "{prompt}"]
model = ""                   # vd: "gpt-5.5", "gpt-5.5-codex"... (xem trong codex /model)
effort = ""
model_args = ["-m", "{model}"]
effort_args = ["-c", "model_reasoning_effort=\\"{effort}\\""]
efforts = ["minimal", "low", "medium", "high", "xhigh"]
fallback = ["claude"]
role = "Viết code, sửa bug, chạy test, refactor."
timeout = 1800
max_concurrent = 1

[agents.antigravity]
# agy chỉ in output khi có terminal thật -> pty = true.
# --mode accept-edits: được sửa file. Cho chạy cả lệnh shell: thay bằng "--dangerously-skip-permissions"
command = ["agy", "--mode", "accept-edits", "--print-timeout", "0", "-p", "{prompt}"]
pty = true
model = ""                   # xem danh sách: agy models
effort = ""
model_args = ["--model", "{model}"]
effort_args = ["--effort", "{effort}"]
efforts = ["low", "medium", "high", "xhigh", "max"]
fallback = ["claude", "codex"]
role = "Nghiên cứu, tìm tài liệu, phân tích codebase lớn, frontend/UI."
timeout = 1800
max_concurrent = 1

[agents.grok]
# Grok qua OpenCode. Danh sách model: opencode models | grep grok
# Nếu bị chặn quyền, thêm "--dangerously-skip-permissions" vào command (chỉ repo tin tưởng).
command = ["opencode", "run", "{prompt}"]
model = "xai/grok-build-0.1"
effort = ""                  # OpenCode gọi là "variant"; tuỳ model có hỗ trợ hay không
model_args = ["--model", "{model}"]
effort_args = ["--variant", "{effort}"]
efforts = ["low", "medium", "high"]
fallback = ["codex"]
role = "Code nhanh, việc nhỏ lặp nhanh, viết test, script, tài liệu."
timeout = 1800
max_concurrent = 1
"""


# Danh mục model/effort có sẵn, theo tên lệnh của CLI. Dùng khi file cấu hình không ghi
# `models` / `efforts` / `models_command`. Model chỉ là gợi ý: /model vẫn nhận tên bất kỳ.
CATALOG: dict[str, dict] = {
    "claude": {
        "models": ["opus", "sonnet", "haiku", "opusplan", "claude-opus-5-5", "claude-sonnet-5-5",
                   "claude-haiku-5-5", "claude-fable-5-1"],
        "efforts": ["low", "medium", "high", "max"],
    },
    "codex": {
        "models": ["gpt-5.5", "gpt-5.5-codex"],
        "efforts": ["minimal", "low", "medium", "high", "xhigh"],
    },
    "agy": {
        "models": [],
        "efforts": ["low", "medium", "high", "xhigh", "max"],
        "models_command": ["agy", "models"],
    },
    "opencode": {
        "models": ["xai/grok-build-0.1", "xai/grok-4.7"],
        "efforts": ["low", "medium", "high"],
        "models_command": ["opencode", "models"],
    },
}
MODEL_RE = re.compile(r"^[A-Za-z0-9][\w.:/@\[\]+-]*$")


def parse_models(output: str, filt: str = "") -> list[str]:
    """Bóc tên model từ output của lệnh liệt kê (mỗi dòng một model, lấy cột đầu)."""
    out: list[str] = []
    for line in output.splitlines():
        line = line.strip().lstrip("-*•").strip()
        if not line or line.endswith(":") or line.startswith("#"):
            continue
        tok = line.split()[0]
        if not MODEL_RE.match(tok) or tok.lower() in ("model", "models", "name", "id"):
            continue
        if filt and filt.lower() not in tok.lower():
            continue
        if tok not in out:
            out.append(tok)
    return out


@dataclass
class AgentConfig:
    name: str
    command: list[str]
    role: str = ""
    timeout: int = 1800
    max_concurrent: int = 1
    pty: bool = False
    enabled: bool = True
    plan_command: list[str] | None = None
    model: str = ""
    effort: str = ""
    model_args: list[str] = field(default_factory=list)
    effort_args: list[str] = field(default_factory=list)
    efforts: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    models_command: list[str] = field(default_factory=list)
    models_filter: str = ""
    fallback: list[str] = field(default_factory=list)
    verify: bool = True
    file_ref: str = ""                        # "" = theo mentions.SYNTAX của lệnh
    file_args: list[str] | None = None        # None = theo mentions.SYNTAX của lệnh

    @property
    def binary(self) -> str:
        return self.command[0] if self.command else ""

    def installed(self) -> bool:
        return bool(self.binary) and shutil.which(self.binary) is not None

    def label(self, model: str | None = None, effort: str | None = None) -> str:
        m = (model if model is not None else self.model) or "mặc định"
        e = effort if effort is not None else self.effort
        return f"{m}" + (f" · {e}" if e else "")

    def model_choices(self) -> list[str]:
        """Model gợi ý; model đang dùng (nếu là tên ngoài danh sách) đứng đầu."""
        return ([self.model] if self.model and self.model not in self.models else []) + self.models

    def argv(self, prompt: str, *, model: str | None = None, effort: str | None = None,
             plan: bool = False) -> list[str]:
        """Dựng lệnh: thay {prompt}/{model}/{effort}, chèn cờ model/effort ngay trước prompt."""
        model = (model if model else self.model) or ""
        effort = (effort if effort else self.effort) or ""
        base = list((self.plan_command if plan and self.plan_command else self.command))
        extra: list[str] = []
        if model and self.model_args and not any("{model}" in c for c in base):
            extra += [a.replace("{model}", model) for a in self.model_args]
        if effort and self.effort_args and not any("{effort}" in c for c in base):
            extra += [a.replace("{effort}", effort) for a in self.effort_args]
        idx = next((i for i, c in enumerate(base) if "{prompt}" in c), None)
        if idx is None:
            base.append("{prompt}")
            idx = len(base) - 1
        if idx > 0 and base[idx - 1] in PROMPT_FLAGS:
            idx -= 1
        base[idx:idx] = extra
        out = []
        for c in base:
            if c in ("{model}", "{effort}") and not (model if c == "{model}" else effort):
                # bỏ placeholder rỗng cùng cờ đứng trước nó
                if out and out[-1].startswith("-"):
                    out.pop()
                continue
            out.append(c.replace("{prompt}", prompt).replace("{model}", model)
                       .replace("{effort}", effort))
        return out


@dataclass
class VerifyConfig:
    command: str = ""
    timeout: int = 600
    max_fix_attempts: int = 2
    fix_agent: str = ""
    only_when_changed: bool = True


@dataclass
class Config:
    lead: str = "claude"
    max_parallel: int = 3
    approve_plan: bool = True
    auto_review: bool = True
    max_rounds: int = 3
    max_delegation_depth: int = 2
    lead_sets_effort: bool = True
    isolation: str = "shared"
    merge: str = "auto"
    verify: VerifyConfig = field(default_factory=VerifyConfig)
    cooldown_minutes: int = 30
    lead_fallback: list[str] = field(default_factory=list)
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    sources: list[Path] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)

    def active_agents(self) -> dict[str, AgentConfig]:
        return {n: a for n, a in self.agents.items() if a.enabled}


def describe_models(cfg: Config, only: str | None = None) -> str:
    """Danh sách model & effort mỗi agent hỗ trợ, đánh dấu ● cái đang dùng."""
    lines = []
    for n, a in cfg.agents.items():
        if only and n != only:
            continue
        lines.append(f"{n}  ({a.binary})  đang dùng: {a.label()}")
        models = a.model_choices()
        lines.append("  model:  " + (" · ".join(("●" if m == a.model else "") + m for m in models)
                                     if models else "(để CLI tự chọn)"))
        lines.append("  effort: " + (" · ".join(("●" if e == a.effort else "") + e for e in a.efforts)
                                     if a.efforts else "(không có)"))
        if a.models_command:
            lines.append(f"  danh sách thật: {' '.join(a.models_command)}  (làm mới: /models {n} làm mới)")
    return "\n".join(lines)


# ---------------------------------------------------------------- file cấu hình
def ensure_global_config() -> list[str]:
    """Tạo file cấu hình chung; nâng cấp file cũ (sao lưu lại). Trả về thông báo cho người dùng."""
    notes: list[str] = []
    GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    if not GLOBAL_CONFIG.exists():
        GLOBAL_CONFIG.write_text(DEFAULT_CONFIG, encoding="utf-8")
        return notes
    try:
        data = tomllib.loads(GLOBAL_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if int(data.get("config_version", 1)) < CONFIG_VERSION:
        bak = GLOBAL_CONFIG.with_name(f"config.v{data.get('config_version', 1)}.{int(time.time())}.bak.toml")
        shutil.copy2(GLOBAL_CONFIG, bak)
        GLOBAL_CONFIG.write_text(DEFAULT_CONFIG, encoding="utf-8")
        notes.append(f"Đã nâng cấp cấu hình lên bản {CONFIG_VERSION} (thêm tính năng mới). "
                     f"Bản cũ sao lưu ở {bak}")
    return notes


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def save_agent_setting(agent: str, key: str, value: str | None) -> None:
    """Lưu model/effort chọn trong app. value None hoặc '-' = xoá (quay về config)."""
    state = load_state()
    agents = state.setdefault("agents", {})
    entry = agents.setdefault(agent, {})
    if value in (None, "", "-"):
        entry.pop(key, None)
    else:
        entry[key] = value
    if not entry:
        agents.pop(agent, None)
    save_state(state)


def save_found_models(agent: str, models: list[str]) -> None:
    """Lưu danh sách model lấy được từ CLI (models_command) để lần sau mở app có ngay."""
    state = load_state()
    state.setdefault("models_found", {})[agent] = models
    save_state(state)


def load_project_state(root: Path) -> dict:
    try:
        return json.loads((root / ".ateam" / "state.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_project_setting(root: Path, key: str, value) -> None:
    """Lưu thiết lập riêng của dự án (vd lệnh kiểm tra) vào .ateam/state.json."""
    st = load_project_state(root)
    if value in (None, ""):
        st.pop(key, None)
    else:
        st[key] = value
    p = root / ".ateam" / "state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def _strs(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        return v.split()
    return [str(x) for x in v]


def load_config(root: Path) -> Config:
    data: dict = tomllib.loads(DEFAULT_CONFIG)
    sources: list[Path] = []
    if GLOBAL_CONFIG.exists():
        data = tomllib.loads(GLOBAL_CONFIG.read_text(encoding="utf-8"))
        sources.append(GLOBAL_CONFIG)
    project = root / ".ateam" / "config.toml"
    if project.exists():
        data = _merge(data, tomllib.loads(project.read_text(encoding="utf-8")))
        sources.append(project)
    full_state = load_state()
    state = full_state.get("agents", {})
    found = full_state.get("models_found", {})

    agents: dict[str, AgentConfig] = {}
    for name, a in (data.get("agents") or {}).items():
        st = state.get(name, {})
        command = _strs(a.get("command"))
        cat = CATALOG.get(Path(command[0]).name if command else "", {})
        models = _strs(a.get("models")) or list(cat.get("models", []))
        seen = [str(m) for m in found.get(name) or []]  # model thật hỏi được từ CLI đứng trước
        models = seen + [m for m in models if m not in seen]
        agents[name] = AgentConfig(
            name=name,
            command=command,
            role=a.get("role", ""),
            timeout=int(a.get("timeout", 1800)),
            max_concurrent=max(1, int(a.get("max_concurrent", 1))),
            pty=bool(a.get("pty", False)),
            enabled=bool(a.get("enabled", True)),
            plan_command=_strs(a.get("plan_command")) or None,
            model=st.get("model", a.get("model", "")) or "",
            effort=st.get("effort", a.get("effort", "")) or "",
            model_args=_strs(a.get("model_args")),
            effort_args=_strs(a.get("effort_args")),
            efforts=_strs(a["efforts"]) if "efforts" in a else list(cat.get("efforts", [])),
            models=models,
            models_command=_strs(a.get("models_command")) or (
                command[:1] + cat["models_command"][1:] if cat.get("models_command") else []),
            models_filter=str(a.get("models_filter", "") or ""),
            fallback=_strs(a.get("fallback")),
            verify=bool(a.get("verify", True)),
            file_ref=str(a.get("file_ref", "") or ""),
            file_args=_strs(a["file_args"]) if "file_args" in a else None,
        )
    v = data.get("verify") or {}
    pstate = load_project_state(root)
    verify = VerifyConfig(
        command=pstate.get("verify_command", v.get("command", "")) or "",
        timeout=int(v.get("timeout", 600)),
        max_fix_attempts=max(0, int(v.get("max_fix_attempts", 2))),
        fix_agent=v.get("fix_agent", "") or "",
        only_when_changed=bool(v.get("only_when_changed", True)),
    )
    lim = data.get("limits") or {}
    return Config(
        lead=data.get("lead", "claude"),
        max_parallel=max(1, int(data.get("max_parallel", 3))),
        approve_plan=bool(data.get("approve_plan", True)),
        auto_review=bool(data.get("auto_review", True)),
        max_rounds=max(1, int(data.get("max_rounds", 3))),
        max_delegation_depth=max(0, int(data.get("max_delegation_depth", 2))),
        lead_sets_effort=bool(data.get("lead_sets_effort", True)),
        isolation=data.get("isolation", "shared"),
        merge=data.get("merge", "auto") if data.get("merge") in ("auto", "review") else "auto",
        verify=verify,
        cooldown_minutes=max(1, int(lim.get("cooldown_minutes", 30))),
        lead_fallback=_strs(lim.get("lead_fallback")),
        agents=agents,
        sources=sources,
    )
