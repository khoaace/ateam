"""Cấu hình: mặc định < ~/.config/ateam/config.toml < .ateam/config.toml < state.json (lựa chọn trong app)."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from .i18n import tr

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

GLOBAL_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ateam"
GLOBAL_CONFIG = GLOBAL_DIR / "config.toml"
STATE_FILE = GLOBAL_DIR / "state.json"
# Agent và workflow người dùng tự thêm (màn hình /custom). File riêng để không mất khi config.toml
# được nâng cấp lên bản mới.
CUSTOM_FILE = GLOBAL_DIR / "custom.toml"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
LEAD_ALIAS = "lead"  # agent của bước workflow = trưởng nhóm hiện tại
CONFIG_VERSION = 8
PROMPT_FLAGS = ("-p", "--print", "--prompt")
# hậu tố effort trong tên model (vd agy: gemini-4-argon-medium) — model đã cố định effort
EFFORT_SUFFIXES = ("minimal", "low", "medium", "high", "xhigh", "max")
# CLI từ chối cờ effort với model đang chọn (agy: "--effort is not supported for model …",
# "--model … conflicts with --effort=high") -> chạy lại không có effort
EFFORT_REJECTED_RE = re.compile(
    r"effort\S* (?:is )?not supported|conflicts with --effort|unsupported (?:reasoning )?effort", re.I)

DEFAULT_CONFIG = """\
# ============================================================
#  AI Team — cấu hình
#  File chung:   ~/.config/ateam/config.toml
#  File dự án:   <dự án>/.ateam/config.toml  (ghi đè file chung)
#  Model / effort đổi trong app (/model, /effort) được lưu ở ~/.config/ateam/state.json
#  và ưu tiên hơn giá trị trong file này. Gõ /model <agent> - để quay về giá trị ở đây.
# ============================================================
config_version = 8

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
#   effort_args   cờ thêm vào khi có effort ({effort} được thay). Có cả {model} thì đây là dạng gộp
#                 model+effort (vd opencode --model x/y#high): thay cho model_args; không có model thì bỏ effort
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
# --sandbox workspace-write: sửa file + chạy lệnh trong sandbox của Codex (codex exec không hỏi duyệt).
# Cho ghi/mạng ngoài thư mục làm việc: "danger-full-access" (chỉ repo tin tưởng).
command = ["codex", "exec", "--sandbox", "workspace-write", "--skip-git-repo-check", "{prompt}"]
model = ""                   # vd: "gpt-6.1-sol", "gpt-6-luna"... (xem: codex debug models)
effort = ""
model_args = ["-m", "{model}"]
effort_args = ["-c", "model_reasoning_effort=\\"{effort}\\""]
efforts = ["low", "medium", "high", "xhigh", "max", "ultra"]
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
# Grok Build CLI (xAI). Danh sách model: grok models
# Chạy headless (-p), "acceptEdits" của grok chặn cả sửa file -> dùng "auto" (sửa file) + "--deny Bash"
# (không chạy lệnh shell). Cho chạy cả lệnh shell/mạng: Toàn quyền (bypassPermissions, chỉ repo tin tưởng)
command = ["grok", "--permission-mode", "auto", "--deny", "Bash", "-p", "{prompt}"]
model = ""                   # vd: "grok-4.7", "grok-4.7-build-fast"
effort = ""
model_args = ["-m", "{model}"]
effort_args = ["--reasoning-effort", "{effort}"]
efforts = ["low", "medium", "high", "xhigh"]
fallback = ["codex"]
role = "Code nhanh, việc nhỏ lặp nhanh, viết test, script, tài liệu."
timeout = 1800
max_concurrent = 1

[agents.opencode]
# OpenCode — chạy được nhiều nhà cung cấp (xAI, OpenAI, Anthropic…). Danh sách model: opencode models
command = ["opencode", "run", "{prompt}"]
model = "xai/grok-build-0.1"
effort = ""                  # OpenCode gọi là "variant"; tuỳ model có hỗ trợ hay không
model_args = ["--model", "{model}"]
# OpenCode bỏ --variant: variant ghi liền model dạng provider/model#variant (cần đặt model)
effort_args = ["--model", "{model}#{effort}"]
efforts = ["low", "medium", "high"]
fallback = ["codex"]
role = "Code nhanh, việc nhỏ, viết test, script, tài liệu."
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
        "usage_command": ["claude", "-p", "/usage"],  # % phiên / tuần đã dùng + giờ hồi (không gọi model)
    },
    "codex": {
        "models": ["gpt-6.1-sol", "gpt-6-astra", "gpt-6-sol", "gpt-6-luna", "gpt-5.6-sol",
                   "gpt-5.6-terra", "gpt-5.6-luna"],
        "efforts": ["low", "medium", "high", "xhigh", "max", "ultra"],
        "models_command": ["codex", "debug", "models"],  # JSON, xem parse_models
    },
    "agy": {
        "models": [],
        "efforts": ["low", "medium", "high", "xhigh", "max"],
        "models_command": ["agy", "models"],
        "usage_command": ["agy", "-p", "/usage"],  # quota còn lại theo nhóm model (cần pty)
    },
    "grok": {
        "models": ["grok-4.7", "grok-4.7-build-fast", "grok-4.6", "grok-4.5"],
        "efforts": ["low", "medium", "high", "xhigh"],
        "models_command": ["grok", "models"],  # "  * grok-4.7 (default)" / "  - grok-4.6"
    },
    "opencode": {
        "models": ["xai/grok-build-0.1", "xai/grok-4.7"],
        "efforts": ["low", "medium", "high"],
        "models_command": ["opencode", "models"],
        "usage_command": ["opencode", "stats", "--days", "7"],  # token & chi phí 7 ngày qua
    },
}
# Giữ phiên giữa các lượt (/retry, vòng sửa verify, /continue, trả lời <<<ASK>>>): cờ đặt id phiên cho lượt
# mới, cờ tiếp tục phiên, regex bắt id trong output (khi CLI không cho tự đặt id). Ghi đè bằng khoá cùng tên
# trong [agents.<tên>]; [] = tắt. agy/opencode: chưa có cách lấy id chắc chắn → chạy như cũ (xem ROADMAP).
_WHICH: dict[tuple, tuple[float, str | None]] = {}
WHICH_TTL = 10.0


def which(binary: str) -> str | None:
    """shutil.which có nhớ tạm: bảng việc hỏi "đã cài chưa" cho từng agent nhiều lần mỗi giây (mỗi lần quét
    mọi thư mục trong PATH). Cài CLI mới thì tối đa WHICH_TTL giây sau mới thấy."""
    key, now = (binary, os.environ.get("PATH", "")), time.time()
    hit = _WHICH.get(key)
    if hit and now - hit[0] < WHICH_TTL:
        return hit[1]
    path = shutil.which(binary)
    _WHICH[key] = (now, path)
    return path


SESSION_PRESETS: dict[str, dict] = {
    "claude": {"session_args": ["--session-id", "{session}"], "resume_args": ["--resume", "{session}"]},
    "grok": {"session_args": ["--session-id", "{session}"], "resume_args": ["--resume", "{session}"]},
    # codex exec resume [OPTIONS] <SESSION_ID> <PROMPT>; header của `codex exec` in "session id: <uuid>"
    "codex": {"session_args": [], "resume_args": ["{session}"],
              "session_re": r"session id:\s*([0-9a-fA-F-]{36})"},
}


def apply_resume(command: list[str]) -> list[str]:
    """Lệnh tiếp tục phiên: codex cần lệnh con `exec resume`; CLI khác chỉ thêm cờ (resume_args)."""
    cmd = list(command)
    if cmd and Path(cmd[0]).name == "codex" and "exec" in cmd and "resume" not in cmd:
        cmd.insert(cmd.index("exec") + 1, "resume")
    return cmd


# codex không có lệnh xem hạn mức không cần gọi model: /usage đọc ảnh chụp rate_limits mà codex ghi
# trong file phiên gần nhất (~/.codex/sessions), xem limits.codex_rate_limits
# Cờ quyền theo CLI: "chỉ sửa file" (mặc định trong DEFAULT_CONFIG) <-> "toàn quyền" (chạy lệnh shell, mạng).
# full_access = true đổi lúc dựng lệnh (apply_access), file cấu hình vẫn ghi lệnh an toàn gốc.
ACCESS_CLIS = ("claude", "codex", "agy", "grok", "opencode")


def full_access_supported(binary: str) -> bool:
    return Path(binary).name in ACCESS_CLIS


def apply_access(command: list[str], full: bool) -> list[str]:
    """Đổi cờ quyền trong lệnh theo CLI. CLI lạ: giữ nguyên (không biết cờ của nó)."""
    cmd = list(command)
    if not cmd:
        return cmd
    name = Path(cmd[0]).name

    def set_value(flag: str, value: str) -> None:
        if flag in cmd and cmd.index(flag) + 1 < len(cmd):
            cmd[cmd.index(flag) + 1] = value
        else:
            cmd[1:1] = [flag, value]

    if name == "grok":
        # grok -p: "acceptEdits" chặn cả sửa file (đã thử thật) -> chỉ sửa file = "auto" + "--deny Bash";
        # cấu hình cũ còn acceptEdits cũng được đổi
        while "--deny" in cmd and cmd.index("--deny") + 1 < len(cmd) and cmd[cmd.index("--deny") + 1] == "Bash":
            j = cmd.index("--deny")
            del cmd[j:j + 2]
        set_value("--permission-mode", "bypassPermissions" if full else "auto")
        if not full:
            j = cmd.index("--permission-mode") + 2
            cmd[j:j] = ["--deny", "Bash"]
    elif name == "claude":
        if full:
            set_value("--permission-mode", "bypassPermissions")
        elif "--permission-mode" in cmd:
            set_value("--permission-mode", "acceptEdits")
    elif name == "codex":
        sandbox = "danger-full-access" if full else "workspace-write"
        i = cmd.index("exec") + 1 if "exec" in cmd else 1
        if "--sandbox" in cmd:
            set_value("--sandbox", sandbox)
        elif full:
            cmd[i:i] = ["--sandbox", sandbox]
    elif name == "agy":
        if full:
            if "--mode" in cmd and cmd.index("--mode") + 1 < len(cmd):
                j = cmd.index("--mode")
                del cmd[j:j + 2]
            if "--dangerously-skip-permissions" not in cmd:
                cmd.insert(1, "--dangerously-skip-permissions")
        elif "--dangerously-skip-permissions" in cmd:
            cmd.remove("--dangerously-skip-permissions")
            cmd[1:1] = ["--mode", "accept-edits"]
    elif name == "opencode":
        if full and "--auto" not in cmd:
            cmd.insert(cmd.index("run") + 1 if "run" in cmd else 1, "--auto")
        elif not full and "--auto" in cmd:
            cmd.remove("--auto")
    return cmd


MODEL_RE = re.compile(r"^[A-Za-z0-9][\w.:/@\[\]+-]*$")


def parse_models_json(output: str) -> list[str] | None:
    """Danh mục model dạng JSON (vd `codex debug models`): {"models": [{"slug", "visibility"}, …]}.
    Bỏ model ẩn. None nếu output không phải JSON như vậy."""
    start, end = output.find("{"), output.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        data = json.loads(output[start:end + 1])
    except ValueError:
        return None
    items = data.get("models") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    out: list[str] = []
    for m in items:
        if not isinstance(m, dict) or m.get("visibility") == "hide":
            continue
        name = m.get("slug") or m.get("id") or m.get("name")
        if isinstance(name, str) and MODEL_RE.match(name) and name not in out:
            out.append(name)
    return out


def parse_models(output: str, filt: str = "") -> list[str]:
    """Bóc tên model từ output của lệnh liệt kê (JSON, hoặc mỗi dòng một model, lấy cột đầu)."""
    found = parse_models_json(output)
    if found is not None:
        return [m for m in found if not filt or filt.lower() in m.lower()]
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
    full_access: bool = False  # toàn quyền: chạy lệnh shell, mạng (xem apply_access)
    enabled: bool = True
    plan_command: list[str] | None = None
    model: str = ""
    effort: str = ""
    model_args: list[str] = field(default_factory=list)
    effort_args: list[str] = field(default_factory=list)
    efforts: list[str] = field(default_factory=list)
    no_effort: set = field(default_factory=set)  # model CLI đã từ chối cờ effort (ghi nhớ khi đang chạy)
    models: list[str] = field(default_factory=list)
    models_command: list[str] = field(default_factory=list)
    usage_command: list[str] = field(default_factory=list)  # lệnh in hạn mức/usage của CLI (/usage)
    models_filter: str = ""
    fallback: list[str] = field(default_factory=list)
    verify: bool = True
    file_ref: str = ""                        # "" = theo mentions.SYNTAX của lệnh
    file_args: list[str] | None = None        # None = theo mentions.SYNTAX của lệnh
    image_args: list[str] | None = None       # None = theo mentions.IMAGE_ARGS (vắng thì như file_args)
    session_args: list[str] | None = None     # None = theo SESSION_PRESETS; đặt id phiên cho lượt mới
    resume_args: list[str] | None = None      # None = theo SESSION_PRESETS; tiếp tục phiên {session}
    session_re: str | None = None             # None = theo SESSION_PRESETS; regex bắt id phiên trong output

    @property
    def binary(self) -> str:
        return self.command[0] if self.command else ""

    def installed(self) -> bool:
        return bool(self.binary) and which(self.binary) is not None

    def label(self, model: str | None = None, effort: str | None = None) -> str:
        m, e = self.split_effort((model if model is not None else self.model) or "",
                                 (effort if effort is not None else self.effort) or "")
        m = m or tr("mặc định")
        return f"{m}" + (f" · {e}" if e else "")

    def model_choices(self) -> list[str]:
        """Model gợi ý; model đang dùng (nếu là tên ngoài danh sách) đứng đầu."""
        return ([self.model] if self.model and self.model not in self.models else []) + self.models

    def split_effort(self, model: str, effort: str) -> tuple[str, str]:
        """Model có sẵn effort trong tên (agy: gemini-4-argon-medium) mà vẫn thêm --effort thì CLI báo
        "conflicts with --effort": đổi sang biến thể đúng effort nếu có trong danh sách model, bỏ cờ effort."""
        if effort and model in self.no_effort:
            return model, ""
        stem, _, tail = model.rpartition("-")
        if not (effort and stem and tail in EFFORT_SUFFIXES):
            return model, effort
        variant = f"{stem}-{effort}"
        return (variant if variant in self.models else model), ""

    def _preset(self, key: str):
        own = getattr(self, key)
        return own if own is not None else SESSION_PRESETS.get(Path(self.binary).name, {}).get(key)

    def session_flags(self, resume: bool) -> list[str]:
        return list(self._preset("resume_args" if resume else "session_args") or [])

    def session_pattern(self) -> str:
        return self._preset("session_re") or ""

    def can_resume(self) -> bool:
        """Giữ được phiên: biết cờ tiếp tục phiên và biết id phiên (tự đặt hoặc bắt từ output)."""
        return bool(self.session_flags(True)) and bool(self.session_flags(False) or self.session_pattern())

    def argv(self, prompt: str, *, model: str | None = None, effort: str | None = None,
             plan: bool = False, session: str | None = None, resume: bool = False) -> list[str]:
        """Dựng lệnh: thay {prompt}/{model}/{effort}, chèn cờ model/effort ngay trước prompt.
        session: id phiên — lượt mới thì đặt id (session_args), resume=True thì tiếp tục phiên đó."""
        model = (model if model else self.model) or ""
        effort = (effort if effort else self.effort) or ""
        model, effort = self.split_effort(model, effort)
        base = apply_access(self.plan_command if plan and self.plan_command else self.command,
                            self.full_access)
        if session and resume:
            base = apply_resume(base)
        extra: list[str] = []
        combined = any("{model}" in a for a in self.effort_args)  # vd opencode: --model {model}#{effort}
        if combined and effort and model and not any("{model}" in c or "{effort}" in c for c in base):
            extra += [a.replace("{model}", model).replace("{effort}", effort) for a in self.effort_args]
        else:
            if model and self.model_args and not any("{model}" in c for c in base):
                extra += [a.replace("{model}", model) for a in self.model_args]
            if effort and self.effort_args and not combined and not any("{effort}" in c for c in base):
                extra += [a.replace("{effort}", effort) for a in self.effort_args]
        if session:
            if resume and Path(self.binary).name == "codex" and "--sandbox" in base:
                # `codex exec resume` không có --sandbox: đổi sang -c sandbox_mode="…"
                j = base.index("--sandbox")
                mode = base[j + 1] if j + 1 < len(base) else "workspace-write"
                del base[j:j + 2]
                extra += ["-c", f'sandbox_mode="{mode}"']
            extra += [a.replace("{session}", session) for a in self.session_flags(resume)]
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
class WorkflowStep:
    agent: str = LEAD_ALIAS          # tên agent, hoặc "lead" = trưởng nhóm lúc chạy
    title: str = ""
    prompt: str = ""                 # {goal} = mục tiêu người dùng gõ
    after: list[int] | None = None   # số thứ tự bước (từ 1) phải xong trước; None = bước liền trước
    effort: str = ""
    model: str = ""


@dataclass
class Workflow:
    """Quy trình dựng sẵn: chuỗi bước cố định, chạy bằng /flow <tên> <mục tiêu> (không cần trưởng
    nhóm lập kế hoạch)."""
    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    review: bool | None = None       # None = theo auto_review

    def plan(self, goal: str, lead: str) -> list[dict]:
        """Đổi thành kế hoạch cùng dạng JSON trưởng nhóm trả về (để dùng chung _insert_plan)."""
        out = []
        for i, st in enumerate(self.steps, 1):
            after = [i - 1] if st.after is None and i > 1 else list(st.after or [])
            out.append({
                "id": i,
                "agent": lead if st.agent in ("", LEAD_ALIAS) else st.agent,
                "title": (st.title or tr("Bước {i}", i=i)).replace("{goal}", goal),
                "prompt": (st.prompt or st.title or goal).replace("{goal}", goal),
                "depends_on": [a for a in after if 0 < a < i],
                "effort": st.effort,
                "model": st.model,
            })
        return out

    def summary(self) -> str:
        return " → ".join(st.agent or LEAD_ALIAS for st in self.steps) or tr("(chưa có bước)")


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
    default_workflow: str = ""  # gõ mục tiêu trong TUI là chạy theo workflow này ("" = trưởng nhóm)
    commit_agent: str = ""  # agent viết commit message ở tab Git ("" = trưởng nhóm)
    prices: dict = field(default_factory=dict)  # [prices."<model>"] input/output… USD / 1 triệu token
    agents: dict[str, AgentConfig] = field(default_factory=dict)
    workflows: dict[str, Workflow] = field(default_factory=dict)
    custom_agents: set[str] = field(default_factory=set)  # tên agent lấy từ custom.toml
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
        lines.append(tr("{n}  ({binary})  đang dùng: {v}", n=n, binary=a.binary, v=a.label()))
        models = a.model_choices()
        lines.append("  model:  " + (" · ".join(("●" if m == a.model else "") + m for m in models)
                                     if models else tr("(để CLI tự chọn)")))
        lines.append("  effort: " + (" · ".join(("●" if e == a.effort else "") + e for e in a.efforts)
                                     if a.efforts else tr("(không có)")))
        if a.models_command:
            lines.append(tr("  danh sách thật: {v}  (làm mới: /models {n} làm mới)", v=' '.join(a.models_command), n=n))
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
    old_version = int(data.get("config_version", 1))
    if old_version < 6:
        note = migrate_grok_to_opencode(data)
        if note:
            notes.append(note)
    if old_version < CONFIG_VERSION:
        bak = GLOBAL_CONFIG.with_name(f"config.v{data.get('config_version', 1)}.{int(time.time())}.bak.toml")
        shutil.copy2(GLOBAL_CONFIG, bak)
        GLOBAL_CONFIG.write_text(DEFAULT_CONFIG, encoding="utf-8")
        notes.append(tr("Đã nâng cấp cấu hình lên bản {CONFIG_VERSION} (thêm tính năng mới). Bản "
                        "cũ sao lưu ở {bak}", CONFIG_VERSION=CONFIG_VERSION, bak=bak))
    return notes


def migrate_grok_to_opencode(old_config: dict) -> str:
    """Bản 6: agent "grok" chuyển sang Grok Build CLI, OpenCode thành agent "opencode". Các lựa chọn đã
    lưu cho "grok" cũ (chạy qua opencode) trong state.json chuyển sang "opencode". Trả về thông báo."""
    old = ((old_config.get("agents") or {}).get("grok") or {})
    cmd = _strs(old.get("command"))
    state = load_state()
    entry = (state.get("agents") or {}).get("grok") or {}
    was_opencode = (Path(cmd[0]).name == "opencode") if cmd else str(entry.get("model", "")).startswith("xai/")
    if not was_opencode:
        return ""
    moved = False
    if entry:
        state["agents"]["opencode"] = {**entry, **(state["agents"].get("opencode") or {})}
        del state["agents"]["grok"]
        moved = True
    found = state.get("models_found") or {}
    if "grok" in found:
        found["opencode"] = found.pop("grok")
        moved = True
    if state.get("lead") == "grok":
        state["lead"] = "opencode"
        moved = True
    if not moved:
        return ""
    shutil.copy2(STATE_FILE, STATE_FILE.with_name(f"state.v5.{int(time.time())}.bak.json"))
    save_state(state)
    return (tr("Agent \"grok\" giờ chạy Grok Build CLI (lệnh grok); lựa chọn cũ của nó (qua "
               "OpenCode) chuyển sang agent mới \"opencode\"."))


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


def save_default_workflow(name: str | None) -> None:
    """Workflow chạy khi gõ mục tiêu: tên, "" = bỏ (trưởng nhóm lập kế hoạch), None = giữ nguyên."""
    if name is None:
        return
    state = load_state()
    if name:
        state["default_workflow"] = name
    else:
        state.pop("default_workflow", None)
    save_state(state)


def save_commit_agent(name: str) -> None:
    """Lưu agent viết commit message (tab Git); "" = trưởng nhóm."""
    state = load_state()
    if name:
        state["commit_agent"] = name
    else:
        state.pop("commit_agent", None)
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


# ---------------------------------------------------------------- agent / workflow tuỳ chỉnh
# Mẫu để điền sẵn form "Thêm agent" (dạng thô như trong file TOML). 4 mẫu đầu lấy từ DEFAULT_CONFIG.
EXTRA_AGENT_TEMPLATES: dict[str, dict] = {
    "gemini": {  # Gemini CLI — cờ chưa kiểm chứng trên CLI thật
        "command": ["gemini", "--approval-mode", "auto_edit", "-p", "{prompt}"],
        "model_args": ["-m", "{model}"],
        "role": "Nghiên cứu, đọc codebase lớn, tài liệu.",
    },
    "aider": {  # Aider — cờ chưa kiểm chứng trên CLI thật
        "command": ["aider", "--yes-always", "--no-auto-commits", "--message", "{prompt}"],
        "model_args": ["--model", "{model}"],
        "file_args": ["--file", "{path}"],
        "role": "Sửa code theo yêu cầu cụ thể.",
    },
    "trống": {"command": ["ten-lenh", "{prompt}"]},
}


# Nhà cung cấp cho form "Thêm agent" đơn giản: tên lệnh -> (nhãn, agent mẫu trong DEFAULT_CONFIG)
PROVIDERS: dict[str, tuple[str, str]] = {
    "claude": ("Claude Code", "claude"),
    "codex": ("Codex", "codex"),
    "agy": ("Antigravity", "antigravity"),
    "grok": ("Grok Build", "grok"),
    "opencode": ("OpenCode", "opencode"),
}


def provider_of(command) -> str:
    """Tên lệnh của agent nếu là một nhà cung cấp có sẵn (claude/codex/agy/grok/opencode), ngược lại ""."""
    cmd = _strs(command)
    name = Path(cmd[0]).name if cmd else ""
    return name if name in PROVIDERS else ""


def provider_template(provider: str) -> dict:
    """Bảng [agents.*] mẫu của nhà cung cấp (lệnh an toàn, cờ model/effort, efforts, pty…)."""
    return dict(tomllib.loads(DEFAULT_CONFIG)["agents"][PROVIDERS[provider][1]])


def agent_templates() -> dict[str, dict]:
    out = {f"{n} ({' '.join(_strs(a.get('command'))[:1])})": dict(a)
           for n, a in tomllib.loads(DEFAULT_CONFIG)["agents"].items()}
    out.update(EXTRA_AGENT_TEMPLATES)
    return out


# Mẫu workflow. agent "*" = thành viên đầu tiên đang bật khác trưởng nhóm (điền lúc chọn mẫu).
WORKFLOW_TEMPLATES: dict[str, dict] = {
    "tinh-nang": {
        "description": "Tính năng mới: thiết kế → viết code → viết test",
        "review": True,
        "steps": [
            {"agent": LEAD_ALIAS, "title": "Thiết kế",
             "prompt": "Đọc codebase và viết thiết kế ngắn cho: {goal}. Chưa sửa code; liệt kê các "
                       "file cần đổi và cách kiểm tra."},
            {"agent": "*", "title": "Viết code", "prompt": "Làm {goal} theo thiết kế ở bước trước."},
            {"agent": "*", "title": "Viết test",
             "prompt": "Viết/cập nhật test cho {goal} và chạy cho tới khi xanh."},
        ],
    },
    "sua-loi": {
        "description": "Sửa lỗi: tái hiện → sửa → test chống tái diễn",
        "review": True,
        "steps": [
            {"agent": "*", "title": "Tái hiện lỗi",
             "prompt": "Tìm nguyên nhân và cách tái hiện lỗi: {goal}. Chưa sửa code."},
            {"agent": "*", "title": "Sửa lỗi", "prompt": "Sửa lỗi theo phân tích ở bước trước: {goal}"},
            {"agent": "*", "title": "Test chống tái diễn",
             "prompt": "Thêm test tái hiện lỗi '{goal}' và chắc chắn nó xanh sau khi sửa."},
        ],
    },
    "review-code": {
        "description": "Trưởng nhóm review, thành viên sửa theo góp ý",
        "review": False,
        "steps": [
            {"agent": LEAD_ALIAS, "title": "Review",
             "prompt": "Review code liên quan tới: {goal}. Liệt kê vấn đề cụ thể (file:dòng), chưa sửa."},
            {"agent": "*", "title": "Sửa theo review", "prompt": "Sửa các vấn đề review ở bước trước."},
        ],
    },
}


def load_custom() -> dict:
    """Nội dung custom.toml ({"agents": {...}, "workflows": {...}}); lỗi cú pháp = rỗng."""
    try:
        return tomllib.loads(CUSTOM_FILE.read_text(encoding="utf-8"))
    except Exception:  # chưa có file hoặc lỗi cú pháp
        return {}


def _toml_key(k: str) -> str:
    return k if re.fullmatch(r"[A-Za-z0-9_-]+", k) else json.dumps(k, ensure_ascii=False)


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    # chuỗi TOML cơ bản dùng cùng quy tắc thoát ký tự với JSON
    return json.dumps(str(v), ensure_ascii=False)


def dump_toml(data: dict, prefix: str = "") -> str:
    """Ghi dict ra TOML (đủ cho custom.toml: chuỗi, số, bool, list, bảng, mảng bảng)."""
    lines: list[str] = []
    scal = {k: v for k, v in data.items() if not isinstance(v, dict)
            and not (isinstance(v, list) and v and all(isinstance(x, dict) for x in v))}
    for k, v in scal.items():
        if v is None:
            continue
        lines.append(f"{_toml_key(k)} = {_toml_value(v)}")
    out = "\n".join(lines)
    for k, v in data.items():
        key = f"{prefix}.{_toml_key(k)}" if prefix else _toml_key(k)
        if isinstance(v, dict):
            body = dump_toml(v, key)
            has_scalars = any(not isinstance(x, dict) for x in v.values())
            out += ("\n\n" if out else "") + (f"[{key}]\n" if has_scalars or not v else "") + body
        elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            for item in v:
                out += ("\n\n" if out else "") + f"[[{key}]]\n" + dump_toml(item, key)
    return out.strip("\n") + ("\n" if not prefix else "")


CUSTOM_HEADER = tr("# Agent và workflow tuỳ chỉnh của ateam. Sửa trong app: /custom (hoặc nút ở "
                   "màn hình /setup).\n"
                   "# File này được giữ nguyên khi config.toml nâng cấp lên bản mới.\n")


def save_custom(data: dict) -> None:
    GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in data.items() if v}
    CUSTOM_FILE.write_text(CUSTOM_HEADER + "\n" + dump_toml(clean), encoding="utf-8")


def save_custom_item(kind: str, name: str, body: dict | None, old_name: str | None = None) -> None:
    """Thêm/sửa (body là dict) hoặc xoá (body None) một agent/workflow trong custom.toml.

    kind = "agents" hoặc "workflows"; old_name khác name = đổi tên."""
    data = load_custom()
    sect = data.setdefault(kind, {})
    if old_name and old_name != name:
        sect.pop(old_name, None)
    if body is None:
        sect.pop(name, None)
    else:
        sect[name] = {k: v for k, v in body.items() if v is not None}
    save_custom(data)


def agent_to_dict(a: AgentConfig) -> dict:
    """Dạng ghi vào custom.toml; bỏ các khoá đang ở giá trị mặc định cho file gọn."""
    d: dict = {"command": list(a.command), "role": a.role}
    for k in ("model", "effort", "models_filter", "file_ref"):
        if getattr(a, k):
            d[k] = getattr(a, k)
    for k in ("model_args", "effort_args", "efforts", "models", "models_command", "usage_command",
              "fallback"):
        if getattr(a, k):
            d[k] = list(getattr(a, k))
    if a.file_args is not None:
        d["file_args"] = list(a.file_args)
    if a.image_args is not None:
        d["image_args"] = list(a.image_args)
    if a.plan_command:
        d["plan_command"] = list(a.plan_command)
    if a.timeout != 1800:
        d["timeout"] = a.timeout
    if a.max_concurrent != 1:
        d["max_concurrent"] = a.max_concurrent
    if a.pty:
        d["pty"] = True
    if a.full_access:
        d["full_access"] = True
    if not a.verify:
        d["verify"] = False
    return d


def workflow_to_dict(w: Workflow) -> dict:
    d: dict = {}
    if w.description:
        d["description"] = w.description
    if w.review is not None:
        d["review"] = w.review
    steps = []
    for st in w.steps:
        s: dict = {"agent": st.agent or LEAD_ALIAS, "title": st.title, "prompt": st.prompt}
        if st.after is not None:
            s["after"] = list(st.after)
        if st.effort:
            s["effort"] = st.effort
        if st.model:
            s["model"] = st.model
        steps.append(s)
    d["steps"] = steps
    return d


def needs_setup() -> bool:
    """Chưa chạy màn hình thiết lập lần đầu (chọn agent, model, effort)."""
    return not load_state().get("onboarded")


def save_setup(root: Path, lead: str, agents: dict[str, dict],
               default_workflow: str | None = None) -> None:
    """Lưu kết quả màn hình thiết lập vào state.json.

    agents = {tên: {"enabled": bool, "model": str|None, "effort": str|None, "role": str|None}};
    model/effort/role None hoặc "" = theo file cấu hình. Giá trị trùng với file cấu hình thì không
    ghi (để sửa file vẫn có tác dụng). default_workflow: workflow chạy khi gõ mục tiêu ("" = bỏ)."""
    base = load_config(root, with_state=False)
    state = load_state()
    st_agents = state.setdefault("agents", {})
    for name, ch in agents.items():
        a = base.agents.get(name)
        if not a:
            continue
        entry = st_agents.setdefault(name, {})
        for key in ("enabled", "model", "effort", "role", "full_access"):
            if key not in ch:
                continue
            v = ch[key]
            if v in (None, "") or v == getattr(a, key):
                entry.pop(key, None)
            else:
                entry[key] = v
        if not entry:
            st_agents.pop(name, None)
    if lead and lead != base.lead and lead in base.agents:
        state["lead"] = lead
    else:
        state.pop("lead", None)
    if default_workflow is not None:
        if default_workflow and default_workflow in base.workflows:
            state["default_workflow"] = default_workflow
        else:
            state.pop("default_workflow", None)
    state["onboarded"] = 1
    save_state(state)


def clear_agent_state(name: str, keys=("model", "effort", "role", "full_access")) -> None:
    """Bỏ các giá trị /setup, /model… đã ghi đè trong state.json cho agent (vd vừa lưu agent ở /custom:
    giá trị trong form phải có hiệu lực, không để giá trị cũ trong state đè lên)."""
    state = load_state()
    entry = (state.get("agents") or {}).get(name)
    if not entry:
        return
    for k in keys:
        entry.pop(k, None)
    if not entry:
        state["agents"].pop(name, None)
    save_state(state)


# ------------------------------------------------------------------ wizard thiết lập (/setup)
# Vai trò trong đội: (khoá, nhãn hiển thị, mô tả gửi trưởng nhóm để phân việc)
ROLES: list[tuple[str, str, str]] = [
    ("lead", tr("★ Trưởng nhóm"), "Trưởng nhóm: lập kế hoạch, thiết kế kiến trúc, review kết quả."),
    ("code", tr("Code chính"), "Viết code, sửa bug, refactor."),
    ("review", "Review code", "Review code, tìm lỗi, đề xuất cải thiện."),
    ("ui", "Frontend/UI", "Frontend, giao diện, CSS, trải nghiệm người dùng."),
    ("test", tr("Test & tài liệu"), "Viết test, script, tài liệu."),
    ("research", tr("Nghiên cứu"), "Nghiên cứu, tìm tài liệu, phân tích codebase lớn."),
]
# CLI ưu tiên cho từng vai trò (lấy CLI đầu tiên người dùng có)
ROLE_PREFS: dict[str, list[str]] = {
    "lead": ["claude", "codex", "grok", "agy", "opencode"],
    "code": ["codex", "claude", "grok", "opencode", "agy"],
    "review": ["claude", "codex", "agy", "grok", "opencode"],
    "ui": ["agy", "claude", "codex", "grok", "opencode"],
    "test": ["grok", "opencode", "codex", "claude", "agy"],
    "research": ["agy", "claude", "codex", "grok", "opencode"],
}
TIERS = [("eco", tr("Tiết kiệm")), ("balanced", tr("Cân bằng")), ("max", tr("Tối đa"))]
# Mức model/effort theo nhà cung cấp, từ rẻ tới mạnh: (từ khoá chọn model trong danh sách có sẵn, effort).
# Tiết kiệm = mức 0, Cân bằng = 1, Tối đa = 2; trưởng nhóm và review được nâng 1 mức. Không có model khớp
# từ khoá thì để CLI tự chọn; effort không hợp lệ với CLI thì bỏ.
TIER_PRESETS: dict[str, list[tuple[list[str], str]]] = {
    "claude": [(["sonnet"], "low"), (["sonnet"], "medium"), (["opus"], "high"), (["opus"], "max")],
    "codex": [(["luna"], "low"), (["sol"], "medium"), (["sol"], "high"), (["sol"], "xhigh")],
    "agy": [(["flash"], "low"), (["pro", "flash"], "medium"), (["pro"], "high"), (["pro"], "xhigh")],
    "grok": [(["build-fast", "fast"], "low"), (["grok-4.7"], "medium"), (["grok-4.7"], "high"),
             (["grok-4.7"], "xhigh")],
    "opencode": [(["grok-build"], "low"), (["grok-4.7", "grok"], "medium"), (["grok-4.7", "grok"], "high"),
                 (["grok-4.7", "grok"], "high")],
}
INSTALL_HINTS: dict[str, str] = {
    "claude": "npm i -g @anthropic-ai/claude-code",
    "codex": "npm i -g @openai/codex",
    "agy": tr("cài Antigravity rồi bật lệnh agy"),
    "grok": "curl -fsSL https://x.ai/cli/install.sh | bash",
    "opencode": "npm i -g opencode-ai",
}
WIZARD_FLOW = "tinh-nang"  # workflow tạo khi chọn kiểu "theo quy trình cố định"


def tier_preset(provider: str, tier: str, role: str, models: list[str], efforts: list[str]) -> tuple[str, str]:
    """(model, effort) gợi ý cho vai trò theo mức chi phí; "" = để CLI tự chọn."""
    levels = TIER_PRESETS.get(provider) or []
    if not levels:
        return "", ""
    i = [k for k, _ in TIERS].index(tier) if tier in [k for k, _ in TIERS] else 1
    if role in ("lead", "review"):
        i += 1
    keys, effort = levels[min(i, len(levels) - 1)]
    model = next((m for k in keys for m in models if k in m.lower()), "")
    return model, effort if effort in efforts else ""


def default_cli(role: str, providers: list[str]) -> str:
    return next((p for p in ROLE_PREFS.get(role, []) if p in providers), providers[0] if providers else "")


@dataclass
class TeamPlan:
    """Kết quả gán vai trò: agents = {tên: {"provider", "model", "effort", "roles", "builtin"}}."""
    agents: dict[str, dict]
    lead: str
    unused: list[str]  # agent có sẵn không được giao vai trò nào -> tắt


def builtin_agent(provider: str) -> str:
    return PROVIDERS[provider][1] if provider in PROVIDERS else provider


def plan_team(assign: dict[str, tuple[str, str, str] | None]) -> TeamPlan:
    """Vai trò -> agent. assign = {khoá vai trò: (CLI, model, effort) hoặc None = không dùng}.

    Vai trò cùng (CLI, model, effort) dùng chung một agent. Nhóm đầu tiên của mỗi CLI dùng agent có sẵn
    (claude, codex, antigravity, grok, opencode); nhóm sau của cùng CLI (model/effort khác) thành agent
    thêm "<agent>-<vai trò>" (vd claude-review)."""
    agents: dict[str, dict] = {}
    by_key: dict[tuple, str] = {}
    lead = ""
    for role, _label, _desc in ROLES:
        a = assign.get(role)
        if not a or not a[0]:
            continue
        key = (a[0], a[1] or "", a[2] or "")
        name = by_key.get(key)
        if not name:
            base = builtin_agent(a[0])
            name = base if base not in agents else f"{base}-{role}"
            agents[name] = {"provider": a[0], "model": key[1], "effort": key[2], "roles": [],
                            "builtin": name == base}
            by_key[key] = name
        agents[name]["roles"].append(role)
        if role == "lead":
            lead = name
    used = {n for n in agents if agents[n]["builtin"]}
    unused = [builtin_agent(p) for p in PROVIDERS if builtin_agent(p) not in used]
    return TeamPlan(agents=agents, lead=lead, unused=unused)


def role_text(roles: list[str]) -> str:
    desc = dict((k, d) for k, _l, d in ROLES)
    return " ".join(desc[r] for r in roles if r in desc)


def save_onboard(root: Path, plan: TeamPlan, *, full_access: bool, approve_plan: bool, auto_review: bool,
                 flow: bool, isolation: str, merge: str, verify_command: str,
                 flow_name: str = WIZARD_FLOW) -> None:
    """Lưu kết quả wizard: agent có sẵn vào state.json, agent thêm vào custom.toml (wizard = true; lần
    chạy wizard sau xoá đi tạo lại), thiết lập chung vào state.json, thiết lập dự án vào .ateam/state.json."""
    data = load_custom()
    for name, body in list((data.get("agents") or {}).items()):
        if isinstance(body, dict) and body.get("wizard"):
            save_custom_item("agents", name, None)
            clear_agent_state(name)
    for name, a in plan.agents.items():
        if a["builtin"]:
            continue
        body = provider_template(a["provider"])
        body.update({"model": a["model"], "effort": a["effort"], "role": role_text(a["roles"]),
                     "full_access": bool(full_access and full_access_supported(a["provider"])),
                     "wizard": True})
        save_custom_item("agents", name, body)
        clear_agent_state(name)
    base = load_config(root, with_state=False)
    choices: dict[str, dict] = {}
    for name in base.agents:
        a = plan.agents.get(name)
        if a and a["builtin"]:
            choices[name] = {"enabled": True, "model": a["model"] or None, "effort": a["effort"] or None,
                             "role": role_text(a["roles"]),
                             "full_access": bool(full_access and full_access_supported(base.agents[name].binary))}
        elif name in plan.unused:
            choices[name] = {"enabled": False}
    workflow = ""
    if flow:
        # đã cấu hình ở popup "Luồng mặc định" (workflow có sẵn) thì giữ; chưa có thì tạo từ mẫu
        if flow_name not in base.workflows:
            flow_name = flow_name if flow_name in WORKFLOW_TEMPLATES else WIZARD_FLOW
            tpl = WORKFLOW_TEMPLATES[flow_name]
            code = next((n for n, a in plan.agents.items() if "code" in a["roles"]), plan.lead)
            steps = [dict(st, agent=code if st["agent"] == "*" else st["agent"]) for st in tpl["steps"]]
            save_custom_item("workflows", flow_name, {**tpl, "steps": steps})
        workflow = flow_name
    save_setup(root, plan.lead, choices, workflow)
    state = load_state()
    for key, value, default in (("approve_plan", approve_plan, True), ("auto_review", auto_review, True)):
        if value == default:
            state.pop(key, None)
        else:
            state[key] = value
    save_state(state)
    save_project_setting(root, "isolation", isolation if isolation != "shared" else None)
    save_project_setting(root, "merge", merge if isolation == "worktree" and merge != "auto" else None)
    save_project_setting(root, "verify_command", verify_command or None)


def mark_setup_done() -> None:
    state = load_state()
    state["onboarded"] = 1
    save_state(state)


# Cờ CLI đã bị bỏ -> cờ thay thế, theo tên lệnh. Áp khi đọc cấu hình để file cũ của người dùng
# vẫn chạy được. Codex bỏ --full-auto từ 0.152 ("unexpected argument"); --sandbox workspace-write
# là tương đương và được mọi bản codex exec nhận.
LEGACY_FLAGS: dict[str, dict[str, list[str]]] = {
    "codex": {"--full-auto": ["--sandbox", "workspace-write"]},
}

# effort_args đã bị bỏ -> dạng mới, theo tên lệnh. OpenCode bỏ `run --variant` ("Unrecognized flag:
# --variant"): variant giờ ghi liền model, `--model provider/model#variant`.
LEGACY_EFFORT_ARGS: dict[str, tuple[list[str], list[str]]] = {
    "opencode": (["--variant", "{effort}"], ["--model", "{model}#{effort}"]),
}


def fix_legacy_effort_args(command: list[str], effort_args: list[str]) -> list[str]:
    old_new = LEGACY_EFFORT_ARGS.get(Path(command[0]).name if command else "")
    return list(old_new[1]) if old_new and effort_args == old_new[0] else effort_args


def fix_legacy_flags(command: list[str]) -> list[str]:
    """Thay cờ đã bị bỏ bằng cờ thay thế; bỏ hẳn nếu lệnh đã có cờ thay thế."""
    table = LEGACY_FLAGS.get(Path(command[0]).name if command else "", {})
    if not table or not any(c in table for c in command):
        return command
    out: list[str] = []
    for c in command:
        new = table.get(c)
        if new is None:
            out.append(c)
        elif new[0] not in command:
            out += new
    return out


def command_flags(command: list[str]) -> list[str]:
    """Các cờ (-x / --xyz) trong lệnh, bỏ placeholder và giá trị sau dấu '='."""
    out = []
    for c in command[1:]:
        if c.startswith("-") and len(c) > 1 and "{" not in c:
            f = c.split("=", 1)[0]
            if f not in out:
                out.append(f)
    return out


def help_command(command: list[str]) -> list[str]:
    """Lệnh xem trợ giúp: tên lệnh + lệnh con (vd `codex exec`, `opencode run`) + --help."""
    head = command[:1]
    for c in command[1:]:
        if c.startswith("-") or "{" in c:
            break
        head.append(c)
    return head + ["--help"]


def unknown_flags(command: list[str], help_text: str) -> list[str]:
    """Cờ trong lệnh mà trang --help không nhắc tới (CLI có thể đã đổi/bỏ cờ)."""
    return [f for f in command_flags(command)
            if not re.search(r"(?<![\w-])" + re.escape(f) + r"(?![\w-])", help_text)]


def _agent_from(name: str, a: dict, st: dict, found: list) -> AgentConfig:
    command = fix_legacy_flags(_strs(a.get("command")))
    cat = CATALOG.get(Path(command[0]).name if command else "", {})
    models = _strs(a.get("models")) or list(cat.get("models", []))
    seen = [str(m) for m in found or []]  # model thật hỏi được từ CLI đứng trước
    models = seen + [m for m in models if m not in seen]
    return AgentConfig(
        name=name,
        command=command,
        role=st.get("role", a.get("role", "")) or "",
        timeout=int(a.get("timeout", 1800)),
        max_concurrent=max(1, int(a.get("max_concurrent", 1))),
        pty=bool(a.get("pty", False)),
        full_access=bool(st.get("full_access", a.get("full_access", False))),
        enabled=bool(st.get("enabled", a.get("enabled", True))),
        plan_command=fix_legacy_flags(_strs(a.get("plan_command"))) or None,
        model=st.get("model", a.get("model", "")) or "",
        effort=st.get("effort", a.get("effort", "")) or "",
        model_args=_strs(a.get("model_args")),
        effort_args=fix_legacy_effort_args(command, _strs(a.get("effort_args"))),
        efforts=_strs(a["efforts"]) if "efforts" in a else list(cat.get("efforts", [])),
        models=models,
        models_command=_strs(a.get("models_command")) or (
            command[:1] + cat["models_command"][1:] if cat.get("models_command") else []),
        models_filter=str(a.get("models_filter", "") or ""),
        usage_command=_strs(a.get("usage_command")) or (
            command[:1] + cat["usage_command"][1:] if cat.get("usage_command") else []),
        fallback=_strs(a.get("fallback")),
        verify=bool(a.get("verify", True)),
        file_ref=str(a.get("file_ref", "") or ""),
        file_args=_strs(a["file_args"]) if "file_args" in a else None,
        image_args=_strs(a["image_args"]) if "image_args" in a else None,
        session_args=_strs(a["session_args"]) if "session_args" in a else None,
        resume_args=_strs(a["resume_args"]) if "resume_args" in a else None,
        session_re=str(a["session_re"]) if "session_re" in a else None,
    )


def agent_from_dict(name: str, body: dict) -> AgentConfig:
    """AgentConfig từ một bảng [agents.<tên>] (không áp state.json) — dùng để xem trước trong form."""
    return _agent_from(name, body, {}, [])


def _workflow_from(name: str, w: dict) -> Workflow:
    steps = []
    for st in w.get("steps") or []:
        if not isinstance(st, dict):
            continue
        after = st.get("after")
        if isinstance(after, (int, str)) and not isinstance(after, bool):
            after = [after]
        steps.append(WorkflowStep(
            agent=str(st.get("agent", "") or LEAD_ALIAS).strip(),
            title=str(st.get("title", "") or "").strip(),
            prompt=str(st.get("prompt", "") or "").strip(),
            after=None if after is None else [int(x) for x in after if str(x).strip().isdigit()],
            effort=str(st.get("effort", "") or "").strip(),
            model=str(st.get("model", "") or "").strip(),
        ))
    review = w.get("review")
    return Workflow(name=name, description=str(w.get("description", "") or ""), steps=steps,
                    review=None if review is None else bool(review))


def load_config(root: Path, with_state: bool = True) -> Config:
    data: dict = tomllib.loads(DEFAULT_CONFIG)
    sources: list[Path] = []
    if GLOBAL_CONFIG.exists():
        data = tomllib.loads(GLOBAL_CONFIG.read_text(encoding="utf-8"))
        sources.append(GLOBAL_CONFIG)
    custom = load_custom()
    if custom:
        data = _merge(data, {k: custom[k] for k in ("agents", "workflows") if k in custom})
        sources.append(CUSTOM_FILE)
    project = root / ".ateam" / "config.toml"
    if project.exists():
        data = _merge(data, tomllib.loads(project.read_text(encoding="utf-8")))
        sources.append(project)
    full_state = load_state() if with_state else {}
    state = full_state.get("agents", {})
    found = full_state.get("models_found", {})

    agents: dict[str, AgentConfig] = {}
    for name, a in (data.get("agents") or {}).items():
        if isinstance(a, dict):
            agents[name] = _agent_from(name, a, state.get(name, {}), found.get(name) or [])
    workflows = {n: _workflow_from(n, w) for n, w in (data.get("workflows") or {}).items()
                 if isinstance(w, dict)}
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
    lead = full_state.get("lead")
    dwf = str(full_state.get("default_workflow") or "")
    cag = str(full_state.get("commit_agent") or "")
    return Config(
        lead=lead if lead in agents else data.get("lead", "claude"),
        max_parallel=max(1, int(data.get("max_parallel", 3))),
        approve_plan=bool(full_state.get("approve_plan", data.get("approve_plan", True))),
        auto_review=bool(full_state.get("auto_review", data.get("auto_review", True))),
        max_rounds=max(1, int(data.get("max_rounds", 3))),
        max_delegation_depth=max(0, int(data.get("max_delegation_depth", 2))),
        lead_sets_effort=bool(data.get("lead_sets_effort", True)),
        isolation=pstate.get("isolation", data.get("isolation", "shared")),
        merge=(pstate.get("merge") or data.get("merge", "auto"))
        if (pstate.get("merge") or data.get("merge")) in ("auto", "review") else "auto",
        verify=verify,
        cooldown_minutes=max(1, int(lim.get("cooldown_minutes", 30))),
        lead_fallback=_strs(lim.get("lead_fallback")),
        default_workflow=dwf if dwf in workflows else "",  # workflow đã bị xoá thì coi như không đặt
        commit_agent=cag if cag in agents else "",
        prices={str(k): v for k, v in (data.get("prices") or {}).items() if isinstance(v, dict)},
        agents=agents,
        workflows=workflows,
        custom_agents={n for n in (custom.get("agents") or {}) if n in agents},
        sources=sources,
    )
