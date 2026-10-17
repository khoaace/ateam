"""Logic thuần của wizard thiết lập (/setup) và form agent/workflow tuỳ chỉnh (/custom) — dùng chung cho TUI
(`OnboardScreen`, `AgentQuickScreen`, `AgentEditScreen`, `WorkflowEditScreen`) và giao diện web.

Không phụ thuộc Textual: màn hình nào cũng chỉ đọc ô nhập rồi gọi các hàm ở đây.
"""

from __future__ import annotations

import re
import shlex
import shutil
from pathlib import Path

from . import shell
from .config import (CATALOG, LEAD_ALIAS, NAME_RE, PROVIDERS, ROLES, WIZARD_FLOW, WORKFLOW_TEMPLATES, Config,
                     Workflow, WorkflowStep, builtin_agent, default_cli, needs_setup, provider_of,
                     provider_template, save_custom_item, save_default_workflow, tier_preset, workflow_to_dict)
from .i18n import tr

# ---------------------------------------------------------------------------- wizard /setup
# (khoá, tiêu đề, tên ngắn trên thanh tiến trình)
STEPS = [("cli", tr("CLI bạn đang dùng"), "CLI"), ("style", tr("Kiểu làm việc"), tr("Kiểu")),
         ("tier", tr("Mức chi phí"), tr("Mức")), ("roles", tr("Vai trò · model · effort"), tr("Vai trò")),
         ("safety", tr("An toàn & duyệt code"), tr("An toàn")), ("verify", tr("Lệnh kiểm tra"), tr("Kiểm tra")),
         ("review", tr("Xem lại & lưu"), tr("Xem lại"))]
STYLES = [("approve", tr("Trưởng nhóm lập kế hoạch, tôi duyệt rồi mới chạy"),
           tr("kế hoạch hiện ở khung Duyệt kế hoạch, Enter/F2 để chạy — an toàn, dễ kiểm soát")),
          ("auto", tr("Trưởng nhóm lập kế hoạch và chạy luôn"), tr("nhanh nhất, không cần duyệt")),
          ("flow", tr("Theo quy trình cố định: thiết kế → code → test"),
           tr("gõ mục tiêu là chạy workflow 'tinh-nang'; /goal vẫn để trưởng nhóm lập kế hoạch")),
          ("manual", tr("Chủ yếu tôi tự giao từng việc (/task)"),
           tr("tắt trưởng nhóm tự review và giao thêm việc"))]
TIER_HINTS = {"eco": tr("model nhỏ/nhanh, effort thấp — tốn ít hạn mức nhất"),
              "balanced": tr("model mạnh vừa, effort trung bình; trưởng nhóm và review cao hơn "
                             "1 bậc"),
              "max": tr("model mạnh nhất, effort cao — chất lượng tốt nhất, tốn hạn mức nhất")}
APPLY = [("shared", tr("Sửa thẳng vào thư mục dự án"), tr("đơn giản; các agent làm chung một chỗ")),
         ("worktree-auto", tr("Mỗi task một nhánh git riêng, xong thì tự merge"),
          tr("an toàn khi nhiều agent chạy song song")),
         ("worktree-review", tr("Mỗi task một nhánh git riêng, tôi xem diff rồi mới merge"),
          tr("Ctrl+D xem diff kiểu VS Code, Ctrl+Y merge"))]
ACCESS = [("safe", tr("Chỉ sửa file (an toàn)"), tr("agent không chạy lệnh shell / mạng")),
          ("full", tr("Toàn quyền — chạy lệnh, mạng (lint, build, git push…)"),
           tr("chỉ dùng cho repo bạn tin tưởng; agent tuỳ chỉnh đổi riêng ở /custom"))]
VERIFY_WORDS = ("test", "lint", "check", "build", "typecheck", "tsc", "vitest", "jest", "pytest")


def installed_providers() -> list[str]:
    return [p for p in PROVIDERS if shutil.which(p)]


def models_of(cfg: Config, provider: str) -> list[str]:
    """Model gợi ý cho một nhà cung cấp: hỏi được từ CLI (agent có sẵn cùng lệnh) hoặc danh mục."""
    a = cfg.agents.get(builtin_agent(provider))
    if a is None or provider_of(a.command) != provider:
        a = next((x for x in cfg.agents.values() if provider_of(x.command) == provider), None)
    return a.model_choices() if a else list(CATALOG.get(provider, {}).get("models", []))


def efforts_of(provider: str) -> list[str]:
    return [str(e) for e in provider_template(provider).get("efforts") or []] if provider in PROVIDERS else []


def default_role(cfg: Config, role: str, providers: list[str], tier: str) -> tuple[str, str, str] | None:
    """(CLI, model, effort) mặc định cho một vai trò theo bộ CLI và mức chi phí."""
    p = default_cli(role, providers)
    if not p:
        return None
    return (p,) + tier_preset(p, tier, role, models_of(cfg, p), efforts_of(p))


def default_assign(cfg: Config, providers: list[str], tier: str) -> dict:
    return {k: default_role(cfg, k, providers, tier) for k, _l, _d in ROLES}


def current_assign(cfg: Config, providers: list[str], tier: str) -> dict:
    """Gán vai trò theo đội hiện tại (mở lại /setup): vai trò mà role của agent có nhắc tới; còn lại theo mặc
    định."""
    out: dict = {}
    agents = {n: a for n, a in cfg.active_agents().items() if provider_of(a.command)}
    for key, _label, desc in ROLES:
        a = agents.get(cfg.lead) if key == "lead" else next((x for x in agents.values() if desc in x.role), None)
        if a and provider_of(a.command) in providers:
            out[key] = (provider_of(a.command), a.model, a.effort)
        else:
            out[key] = default_role(cfg, key, providers, tier)
    return out


def initial(cfg: Config, root: Path) -> dict:
    """Giá trị khởi đầu của wizard theo cấu hình hiện tại."""
    installed = installed_providers()
    team = {provider_of(a.command) for a in cfg.active_agents().values()}
    providers = [p for p in installed if p in team] or list(installed)
    tier = "balanced"
    return {
        "installed": installed, "providers": providers, "tier": tier,
        "style": ("flow" if cfg.default_workflow else "manual" if not cfg.auto_review
                  else "approve" if cfg.approve_plan else "auto"),
        "assign": current_assign(cfg, providers, tier),
        "access": "full" if any(a.full_access for a in cfg.active_agents().values()) else "safe",
        "apply": ("shared" if cfg.isolation != "worktree" else
                  "worktree-review" if cfg.merge == "review" else "worktree-auto"),
        "verify": cfg.verify.command, "git": (root / ".git").exists(), "first": needs_setup(),
        "flow_name": cfg.default_workflow,
    }


def settings_of(style: str, access: str, apply: str, verify: str, flow_name: str = "") -> dict:
    """Lựa chọn của wizard → tham số `config.save_onboard`. flow_name: workflow chọn ở popup Luồng mặc định."""
    return {"full_access": access == "full", "approve_plan": style != "auto",
            "auto_review": style != "manual", "flow": style == "flow", "flow_name": flow_name or WIZARD_FLOW,
            "isolation": "worktree" if apply.startswith("worktree") else "shared",
            "merge": "review" if apply == "worktree-review" else "auto",
            "verify_command": verify.strip()}


def verify_choices(root: Path, current: str) -> list[tuple[str, str, str]]:
    """(lệnh, nhãn, gợi ý) cho bước Lệnh kiểm tra: script test/lint/build của dự án, lệnh đang dùng, "không"."""
    cmds = [c for c, _d in shell.project_scripts(root, recent=[]) if any(w in c.lower() for w in VERIFY_WORDS)][:8]
    items = [(c, c, tr("chạy sau mỗi task có sửa code; lỗi thì giao agent sửa")) for c in cmds]
    if current and current not in cmds:
        items.insert(0, (current, current, tr("đang dùng")))
    items.append(("", tr("Không chạy lệnh kiểm tra"), tr("bật sau bằng /verify <lệnh>")))
    return items


def apply_live(cfg: Config, fresh: Config) -> bool:
    """Áp cấu hình vừa lưu (fresh) vào config đang chạy sau /setup. Trả True nếu đổi chế độ worktree/shared
    (bên gọi cần `orch.apply_isolation()`)."""
    cfg.lead, cfg.default_workflow = fresh.lead, fresh.default_workflow
    cfg.approve_plan, cfg.auto_review, cfg.merge = fresh.approve_plan, fresh.auto_review, fresh.merge
    cfg.verify.command = fresh.verify.command
    for n, a in cfg.agents.items():
        f = fresh.agents.get(n)
        if f:
            a.enabled, a.model, a.effort, a.role = f.enabled, f.model, f.effort, f.role
            a.full_access = f.full_access
    if cfg.isolation != fresh.isolation:
        cfg.isolation = fresh.isolation
        return True
    return False


def reload_custom(cfg: Config, fresh: Config) -> tuple[set[str], set[str]]:
    """Đọc lại agent/workflow tuỳ chỉnh vào config đang chạy. Trả (agent thêm, agent bớt)."""
    before = set(cfg.agents)
    for n in [n for n in cfg.agents if n not in fresh.agents]:
        del cfg.agents[n]
    for n, a in fresh.agents.items():
        if n not in cfg.agents or n in cfg.custom_agents or n in fresh.custom_agents:
            cfg.agents[n] = a  # agent có sẵn giữ nguyên đối tượng (model/effort đang dùng)
    cfg.custom_agents = fresh.custom_agents
    cfg.workflows = fresh.workflows
    cfg.default_workflow = fresh.default_workflow  # workflow mặc định vừa bị xoá -> bỏ
    if cfg.lead not in cfg.agents:
        cfg.lead = fresh.lead
    return set(cfg.agents) - before, before - set(cfg.agents)


# ---------------------------------------------------------------------------- agent & workflow tuỳ chỉnh
AGENT_FIELDS = [  # (id, nhãn, gợi ý, khoá TOML, kiểu: argv | csv | text | int)
    ("command", tr("Lệnh"), tr("bắt buộc; {prompt} = nội dung task"), "command", "argv"),
    ("role", tr("Vai trò"), tr("trưởng nhóm phân việc dựa vào đây"), "role", "text"),
    ("model", tr("Model mặc định"), tr("trống = để CLI tự chọn"), "model", "text"),
    ("models", tr("Model gợi ý"), tr("cách nhau dấu phẩy"), "models", "csv"),
    ("model-args", tr("Cờ model"), "vd: --model {model}", "model_args", "argv"),
    ("efforts", tr("Mức effort"), tr("vd: low, medium, high · '-' = không có"), "efforts", "csv"),
    ("effort", tr("Effort mặc định"), tr("trống = để CLI tự chọn"), "effort", "text"),
    ("effort-args", tr("Cờ effort"), "vd: --effort {effort}", "effort_args", "argv"),
    ("models-command", tr("Lệnh liệt kê model"), tr("vd: mycli models (tuỳ chọn)"), "models_command", "argv"),
    ("file-ref", tr("Nhắc file @"), tr("vd: @{path} hoặc {path} · trống = theo lệnh"), "file_ref", "text"),
    ("file-args", tr("Cờ đính file"), tr("vd: -f {path} · trống = theo lệnh · '-' = tắt"), "file_args", "argv"),
    ("image-args", tr("Cờ đính ảnh"), tr("vd: --image={path} · trống = theo lệnh · '-' = tắt"), "image_args",
     "argv"),
    ("fallback", tr("Dự phòng"), tr("agent thay khi hết hạn mức, cách nhau dấu phẩy"), "fallback", "csv"),
    ("timeout", tr("Timeout (giây)"), tr("mặc định 1800"), "timeout", "int"),
    ("max-concurrent", tr("Số task cùng lúc"), tr("mặc định 1"), "max_concurrent", "int"),
]


def csv(text: str) -> list[str]:
    return [x.strip() for x in text.replace(";", ",").split(",") if x.strip()]


def argv_text(v) -> str:
    """argv -> chuỗi để sửa trong ô nhập; chỉ đặt trong nháy khi cần ({prompt} giữ nguyên cho dễ đọc)."""
    if not isinstance(v, list):
        return str(v or "")
    return " ".join(x if x and not re.search(r"[\s'\"\\]", x) else shlex.quote(x) for x in map(str, v))


def agent_fields_text(raw: dict) -> dict[str, str]:
    """Thân TOML của agent → chữ cho từng ô của form nâng cao (khoá = id trong AGENT_FIELDS)."""
    out = {}
    for fid, _l, _h, key, kind in AGENT_FIELDS:
        v = raw.get(key)
        if v is None:
            text = ""
        elif kind == "argv":
            text = "-" if key in ("file_args", "image_args") and v == [] else argv_text(v)
        elif kind == "csv":
            text = "-" if v == [] else ", ".join(map(str, v if isinstance(v, list) else [v]))
        else:
            text = str(v)
        out[fid] = text
    return out


def agent_body(fields: dict[str, str], pty: bool = False, verify: bool = True, full: bool = False) -> dict:
    """Chữ của form nâng cao → thân TOML (chỉ những khoá có điền). Lỗi -> ValueError."""
    out: dict = {}
    for fid, label, _h, key, kind in AGENT_FIELDS:
        text = str(fields.get(fid) or "").strip()
        if not text:
            continue
        if kind == "argv":
            if key in ("file_args", "image_args") and text == "-":
                out[key] = []
                continue
            try:
                out[key] = shlex.split(text)
            except ValueError:
                raise ValueError(tr("{label}: thiếu dấu nháy đóng", label=label))
        elif kind == "csv":
            out[key] = [] if text == "-" else csv(text)
        elif kind == "int":
            if not text.isdigit() or int(text) < 1:
                raise ValueError(tr("{label}: phải là số nguyên dương", label=label))
            out[key] = int(text)
        else:
            out[key] = text
    if pty:
        out["pty"] = True
    if not verify:
        out["verify"] = False
    if full:
        out["full_access"] = True
    return out


def quick_models(cfg: Config, provider: str) -> list[str]:
    """Model cho form agent nhanh: hỏi được từ CLI ở agent có sẵn cùng lệnh, không thì danh mục."""
    same = [a for n, a in cfg.agents.items() if provider_of(a.command) == provider and n not in cfg.custom_agents]
    if same:
        return same[0].model_choices()
    return list(CATALOG.get(provider, {}).get("models", []))


def quick_body(cfg: Config, provider: str, model: str = "", effort: str = "", role: str = "",
               full: bool = False) -> dict:
    """Thân TOML cho agent dựa trên nhà cung cấp có sẵn: mẫu + model/effort/vai trò/quyền."""
    body = provider_template(provider)
    for key, v in (("model", model), ("effort", effort)):
        body.pop(key, None)
        if v:
            body[key] = v
    body["role"] = role.strip()
    if full:
        body["full_access"] = True
    # dự phòng của mẫu có thể trỏ tới agent đã bị tắt/xoá: chỉ giữ agent đang có
    body["fallback"] = [f for f in body.get("fallback", []) if f in cfg.agents]
    return body


def auto_name(cfg: Config, base: str) -> str:
    n, i = base, 2
    while n in cfg.agents:
        n, i = f"{base}-{i}", i + 1
    return n


def check_agent_name(cfg: Config, name: str, old: str | None) -> None:
    if not NAME_RE.match(name) or name == LEAD_ALIAS:
        raise ValueError(tr("Tên chỉ gồm chữ, số, - và _ (không dùng 'lead')"))
    if name in cfg.agents and name != old:
        raise ValueError(tr("Đã có agent '{name}' — chọn tên khác", name=name))


def check_agent(cfg: Config, name: str, old: str | None, body: dict) -> None:
    """Kiểm tra agent đầy đủ (form nâng cao). Lỗi -> ValueError."""
    check_agent_name(cfg, name, old)
    if not body.get("command"):
        raise ValueError(tr("Cần nhập lệnh chạy agent"))
    bad = [f for f in body.get("fallback", []) if f not in cfg.agents or f == name]
    if bad:
        raise ValueError(tr("Dự phòng không có trong đội: {v}", v=', '.join(bad)))


def workflow_template(cfg: Config, key: str) -> dict:
    """Mẫu workflow, agent '*' thay bằng thành viên đầu tiên (không phải trưởng nhóm)."""
    tpl = WORKFLOW_TEMPLATES[key]
    member = next((n for n in cfg.active_agents() if n != cfg.lead), LEAD_ALIAS)
    return dict(tpl, steps=[dict(st, agent=member if st["agent"] == "*" else st["agent"]) for st in tpl["steps"]])


def after_text(after) -> str:
    return "" if after is None else ("0" if after == [] else
                                     ",".join(map(str, after if isinstance(after, list) else [after])))


def workflow_body(cfg: Config, name: str, old: str | None, description: str, review: bool,
                  steps: list[dict]) -> dict:
    """Form workflow → thân TOML. steps: [{agent, title, prompt, after (chữ), effort}]. Lỗi -> ValueError."""
    if not NAME_RE.match(name):
        raise ValueError(tr("Tên chỉ gồm chữ, số, - và _"))
    if name in cfg.workflows and name != old:
        raise ValueError(tr("Đã có workflow '{name}' — chọn tên khác", name=name))
    out = []
    for i, st in enumerate(steps, 1):
        title, prompt = str(st.get("title") or "").strip(), str(st.get("prompt") or "").strip()
        if not (title or prompt):
            raise ValueError(tr("Bước {i}: cần tiêu đề hoặc prompt", i=i))
        text = str(st.get("after") or "").strip()
        after: list[int] | None = None
        if text in ("0", "-"):
            after = []
        elif text:
            parts = csv(text)
            if not all(p.isdigit() and 0 < int(p) < i for p in parts):
                raise ValueError(tr("Bước {i}: 'Sau bước' phải là số bước đứng trước (1…{v})", i=i, v=i - 1))
            after = [int(p) for p in parts]
        out.append(WorkflowStep(agent=str(st.get("agent") or LEAD_ALIAS), title=title, prompt=prompt, after=after,
                                effort=str(st.get("effort") or "").strip().lower()))
    if not out:
        raise ValueError(tr("Workflow cần ít nhất 1 bước"))
    return workflow_to_dict(Workflow(name=name, description=description.strip(), steps=out, review=review))


# ---------------------------------------------------------------------------- popup "Luồng mặc định"
def flow_names(cfg: Config) -> list[tuple[str, str]]:
    """(tên, nhãn) cho ô chọn workflow: workflow đã có, rồi mẫu chưa tạo (lưu sẽ tạo từ mẫu)."""
    out = [(n, n + (tr("  ★ mặc định") if n == cfg.default_workflow else "")) for n in cfg.workflows]
    out += [(k, tr("{k}  (mẫu, chưa tạo)", k=k)) for k in WORKFLOW_TEMPLATES if k not in cfg.workflows]
    return out


def flow_agent(cfg: Config, agent: str) -> str:
    """Agent thật chạy bước (bước 'lead' = trưởng nhóm hiện tại)."""
    return cfg.lead if agent in ("", LEAD_ALIAS) else agent


def flow_agents(cfg: Config) -> list[tuple[str, str]]:
    """(nhãn, giá trị) cho ô chọn agent của một bước."""
    return [(tr("★ Trưởng nhóm ({lead})", lead=cfg.lead), LEAD_ALIAS)] + [(n, n) for n in cfg.active_agents()]


def flow_step_choices(cfg: Config, agent: str) -> tuple[list[str], list[str]]:
    """(model, effort) gợi ý cho agent của một bước."""
    a = cfg.agents.get(flow_agent(cfg, agent))
    return (a.model_choices(), list(a.efforts)) if a else ([], [])


def flow_form(cfg: Config, name: str = "") -> dict:
    """Dữ liệu popup: workflow mặc định hiện tại (hoặc `name`; chưa có thì lấy từ mẫu)."""
    name = name or cfg.default_workflow or WIZARD_FLOW
    w = cfg.workflows.get(name)
    if w:
        raw = workflow_to_dict(w)
    elif name in WORKFLOW_TEMPLATES:
        raw = workflow_template(cfg, name)
    else:
        raise ValueError(tr("Không có workflow '{name}'", name=name))
    steps = [{"agent": st.get("agent") or LEAD_ALIAS, "title": st.get("title") or tr("Bước {i}", i=i),
              "model": st.get("model", ""), "effort": st.get("effort", "")}
             for i, st in enumerate(raw.get("steps") or [], 1)]
    return {"name": name, "description": raw.get("description", ""), "review": raw.get("review") is not False,
            "steps": steps, "is_default": name == cfg.default_workflow, "exists": w is not None}


def save_flow(cfg: Config, name: str, steps: list[dict], review: bool, make_default: bool | None) -> str:
    """Lưu agent/model/effort từng bước (giữ tiêu đề, prompt, thứ tự) vào custom.toml; make_default: True đặt
    làm workflow chạy khi gõ mục tiêu, False bỏ nếu đang là mặc định, None giữ nguyên (wizard /setup tự đặt
    khi lưu). Trả lời nhắn; lỗi → ValueError."""
    w = cfg.workflows.get(name)
    if w:
        raw = workflow_to_dict(w)
    elif name in WORKFLOW_TEMPLATES:
        raw = workflow_template(cfg, name)
    else:
        raise ValueError(tr("Không có workflow '{name}'", name=name))
    old = [dict(st) for st in raw.get("steps") or []]
    if len(steps) != len(old):
        raise ValueError(tr("Workflow '{name}' vừa đổi số bước — mở lại popup", name=name))
    for i, (st, ch) in enumerate(zip(old, steps), 1):
        agent = str(ch.get("agent") or LEAD_ALIAS)
        if agent != LEAD_ALIAS and agent not in cfg.agents:
            raise ValueError(tr("Bước {i}: không có agent '{name}'", i=i, name=agent))
        a = cfg.agents.get(flow_agent(cfg, agent))
        effort = str(ch.get("effort") or "").strip().lower()
        if effort and a and a.efforts and effort not in a.efforts:
            raise ValueError(tr("Bước {i}: effort '{effort}' không hợp lệ cho {agent} ({v})", i=i, effort=effort,
                                agent=a.name, v=", ".join(a.efforts)))
        st["agent"] = agent
        for key, val in (("model", str(ch.get("model") or "").strip()), ("effort", effort)):
            if val:
                st[key] = val
            else:
                st.pop(key, None)
    raw["steps"], raw["review"] = old, bool(review)
    save_custom_item("workflows", name, raw)
    if make_default is not None:
        save_default_workflow(name if make_default else ("" if cfg.default_workflow == name else None))
    return tr("Đã lưu luồng '{name}': {v}", name=name,
              v=" → ".join(flow_agent(cfg, st["agent"]) for st in old))
