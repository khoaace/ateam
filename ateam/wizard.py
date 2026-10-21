"""Logic thuần của wizard thiết lập (/setup) và form agent/workflow tuỳ chỉnh (/custom) — dùng chung cho TUI
(`OnboardScreen`, `AgentQuickScreen`, `AgentEditScreen`, `WorkflowEditScreen`) và giao diện web.

Không phụ thuộc Textual: màn hình nào cũng chỉ đọc ô nhập rồi gọi các hàm ở đây.
"""

from __future__ import annotations

import re
import shlex
import shutil
import unicodedata
from pathlib import Path

from . import shell
from .config import (CATALOG, LEAD_ALIAS, NAME_RE, PROVIDERS, QUALITY, ROLES, WIZARD_FLOW, WORKFLOW_TEMPLATES, Config,
                     Workflow, WorkflowStep, builtin_agent, default_cli, fill_template, needs_setup, provider_of,
                     provider_template, save_custom_item, save_default_workflow, save_project_setting, task_kind,
                     tier_preset, workflow_to_dict)
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
          ("flow", tr("Theo quy trình cố định: thiết kế → code → review"),
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
    """Model gợi ý cho một nhà cung cấp: gộp model của mọi agent cùng lệnh (kể cả agent tuỳ chỉnh) — agent có
    sẵn có thể đang tắt nên chưa từng hỏi CLI, trong khi một agent tuỳ chỉnh cùng CLI đã có đủ danh sách thật —
    agent nhiều model nhất (đã hỏi CLI) đứng trước; không có agent nào thì lấy danh mục."""
    same = sorted((a for a in cfg.agents.values() if provider_of(a.command) == provider),
                  key=lambda a: -len(a.models))
    out: list[str] = []
    for a in same:
        out += [m for m in a.model_choices() if m not in out]
    return out or list(CATALOG.get(provider, {}).get("models", []))


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


def role_agents(cfg: Config) -> dict:
    """Agent đang giữ từng vai trò: trưởng nhóm, còn lại là agent có role nhắc tới mô tả vai trò."""
    agents = {n: a for n, a in cfg.active_agents().items() if provider_of(a.command)}
    out: dict = {}
    for key, _label, desc in ROLES:
        name = cfg.lead if key == "lead" else next((n for n, x in agents.items() if desc in x.role), None)
        if name in agents:
            out[key] = name
    return out


def current_assign(cfg: Config, providers: list[str], tier: str) -> dict:
    """Gán vai trò theo đội hiện tại (mở lại /setup): vai trò mà role của agent có nhắc tới; còn lại theo mặc
    định."""
    out: dict = {}
    names = role_agents(cfg)
    for key, _label, _desc in ROLES:
        a = cfg.agents.get(names.get(key, ""))
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


def quick_providers(init: dict) -> list[str]:
    """CLI chọn được ở popup sửa nhanh vai trò: mọi CLI đã cài; máy chưa cài CLI nào thì bộ CLI của đội."""
    return [p for p in PROVIDERS if p in init["installed"]] or list(init["providers"])


def current_settings(cfg: Config, root: Path) -> dict:
    """Thiết lập đang dùng (kiểu, quyền, worktree, lệnh kiểm tra) dạng tham số save_onboard — lưu vai trò nhanh
    mà không đổi những thứ này."""
    i = initial(cfg, root)
    return settings_of(i["style"], i["access"], i["apply"], i["verify"], cfg.default_workflow)


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
    cfg.quality = fresh.quality
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
    """Model cho form agent nhanh: như models_of."""
    return models_of(cfg, provider)


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
    """Mẫu workflow, agent '*' thay theo vai trò hợp với loại bước (role_agents), không có thì thành viên đầu tiên
    không phải trưởng nhóm."""
    member = next((n for n in cfg.active_agents() if n != cfg.lead), LEAD_ALIAS)
    return fill_template(WORKFLOW_TEMPLATES[key], role_agents(cfg), member)


def after_text(after) -> str:
    return "" if after is None else ("0" if after == [] else
                                     ",".join(map(str, after if isinstance(after, list) else [after])))


def workflow_body(cfg: Config, name: str, old: str | None, description: str, review: bool,
                  steps: list[dict]) -> dict:
    """Form workflow → thân TOML. steps: [{agent, title, prompt, after (chữ), model, effort, type}]. Lỗi ->
    ValueError."""
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
                                effort=str(st.get("effort") or "").strip().lower(),
                                model=str(st.get("model") or "").strip(), kind=task_kind(st.get("type"))))
    if not out:
        raise ValueError(tr("Workflow cần ít nhất 1 bước"))
    return workflow_to_dict(Workflow(name=name, description=description.strip(), steps=out, review=review))


def suggestion_form(cfg: Config, raw: dict) -> dict:
    """Workflow trưởng nhóm gợi ý (JSON) → dữ liệu điền form: tên chưa trùng, agent lạ → trưởng nhóm, effort
    lạ bỏ, 'Sau bước' sai bỏ (= sau bước liền trước). Không có bước nào → ValueError."""
    steps = []
    for st in raw.get("steps") or []:
        if not isinstance(st, dict) or not (st.get("title") or st.get("prompt")):
            continue
        agent = str(st.get("agent") or LEAD_ALIAS)
        agent = agent if agent in cfg.active_agents() else LEAD_ALIAS
        a = cfg.agents.get(flow_agent(cfg, agent))
        effort = str(st.get("effort") or "").strip().lower()
        after = st.get("after")
        after = after if isinstance(after, list) else None if after is None else [after]
        if after and not all(isinstance(x, int) and 0 < x <= len(steps) for x in after):
            after = None
        steps.append({"agent": agent, "title": str(st.get("title") or "").strip(),
                      "prompt": str(st.get("prompt") or "").strip(), "after": after_text(after),
                      "effort": effort if a and effort in a.efforts_for() else "", "type": task_kind(st.get("type"))})
    if not steps:
        raise ValueError(tr("Trưởng nhóm không gợi ý được bước nào — thử mô tả rõ hơn"))
    slug = unicodedata.normalize("NFKD", str(raw.get("name") or "").translate({0x111: "d", 0x110: "D"}))  # đ/Đ không tách dấu
    base = re.sub(r"[^a-z0-9_-]+", "-", slug.encode("ascii", "ignore").decode().lower()).strip("-_")[:30] or "workflow"
    name, i = base, 2
    while name in cfg.workflows:
        name, i = f"{base}-{i}", i + 1
    return {"name": name, "description": str(raw.get("description") or "").strip(),
            "review": raw.get("review") is not False, "steps": steps}


# ---------------------------------------------------------------------------- gõ mục tiêu đi đâu (ô chọn cạnh ô nhập)
def input_modes(cfg: Config) -> list[tuple[str, str]]:
    """(tên workflow, nhãn) cho ô chọn cạnh ô nhập: "" = trưởng nhóm lập kế hoạch, rồi từng workflow."""
    return [("", tr("★ Trưởng nhóm lập kế hoạch"))] + [
        (n, f"⚙ {n} · {w.summary()}") for n, w in cfg.workflows.items()]


def mode_label(cfg: Config) -> str:
    """Nhãn ngắn trên nút cạnh ô nhập."""
    return f"⚙ {cfg.default_workflow}" if cfg.default_workflow else tr("★ Trưởng nhóm")


def set_input_mode(cfg: Config, name: str) -> str:
    """Gõ mục tiêu (không kèm lệnh) sẽ chạy workflow `name`, "" = trưởng nhóm lập kế hoạch. Lưu state.json (dùng
    chung TUI ↔ web). Trả lời nhắn; tên lạ → ValueError."""
    name = (name or "").strip()
    if name and name not in cfg.workflows:
        raise ValueError(tr("Không có workflow '{name}'", name=name))
    save_default_workflow(name)
    cfg.default_workflow = name
    return (tr("Gõ mục tiêu → chạy workflow '{name}' (/goal: trưởng nhóm lập kế hoạch)", name=name) if name
            else tr("Gõ mục tiêu → trưởng nhóm lập kế hoạch"))


# ---------------------------------------------------------------------------- popup "Luồng mặc định"
LEAD_FLOW = "*lead"  # lựa chọn "★ Trưởng nhóm lập kế hoạch" ở popup (tên workflow không bắt đầu bằng *)
# preset chất lượng của dự án (config.QUALITY): (khoá, nhãn, mô tả)
QUALITY_CHOICES = [
    ("fast", tr("Nhanh"), tr("ít lượt gọi nhất: test khi rủi ro, không review code, bỏ review cuối khi mọi thứ đều qua")),
    ("auto", tr("Trưởng nhóm tự quyết"), tr("viết test khi đổi hành vi, review code (agent khác) khi thay đổi rủi ro "
                                           "hoặc lớn")),
    ("strict", tr("Chặt chẽ"), tr("luôn viết test và review code bởi agent khác")),
]


def quality_label(quality: str) -> str:
    return dict((k, lb) for k, lb, _h in QUALITY_CHOICES).get(quality, quality)


def flow_names(cfg: Config, in_setup: bool = False) -> list[tuple[str, str]]:
    """(tên, nhãn) cho ô chọn luồng: ★ trưởng nhóm lập kế hoạch (trừ khi mở từ /setup), workflow đã có, rồi mẫu chưa
    tạo (lưu sẽ tạo từ mẫu)."""
    out = [] if in_setup else [(LEAD_FLOW, tr("★ Trưởng nhóm lập kế hoạch")
                                + (tr("  ★ mặc định") if not cfg.default_workflow else ""))]
    out += [(n, n + (tr("  ★ mặc định") if n == cfg.default_workflow else "")) for n in cfg.workflows]
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
    return (a.model_choices(), list(a.efforts_for())) if a else ([], [])


def flow_form(cfg: Config, name: str = "", in_setup: bool = False) -> dict:
    """Dữ liệu popup: luồng đang chạy khi gõ mục tiêu (hoặc `name`): ★ trưởng nhóm (preset chất lượng) hoặc
    workflow (chưa có thì lấy từ mẫu). Mở từ /setup thì chỉ có workflow."""
    name = name or cfg.default_workflow or (WIZARD_FLOW if in_setup else LEAD_FLOW)
    if name == LEAD_FLOW:
        return {"name": LEAD_FLOW, "lead": True, "quality": cfg.quality, "verify": cfg.verify.command,
                "is_default": not cfg.default_workflow, "exists": True, "description": "", "review": cfg.auto_review,
                "steps": []}
    w = cfg.workflows.get(name)
    if w:
        raw = workflow_to_dict(w)
    elif name in WORKFLOW_TEMPLATES:
        raw = workflow_template(cfg, name)
    else:
        raise ValueError(tr("Không có workflow '{name}'", name=name))
    steps = [{"agent": st.get("agent") or LEAD_ALIAS, "title": st.get("title") or tr("Bước {i}", i=i),
              "model": st.get("model", ""), "effort": st.get("effort", ""), "type": task_kind(st.get("type"))}
             for i, st in enumerate(raw.get("steps") or [], 1)]
    return {"name": name, "lead": False, "description": raw.get("description", ""),
            "review": raw.get("review") is not False, "steps": steps, "is_default": name == cfg.default_workflow,
            "exists": w is not None}


def save_lead_flow(cfg: Config, root: Path, quality: str) -> str:
    """Popup Luồng mặc định, ★ trưởng nhóm: gõ mục tiêu → trưởng nhóm lập kế hoạch theo preset chất lượng của dự án
    (.ateam/state.json). Trả lời nhắn; preset lạ → ValueError."""
    if quality not in QUALITY:
        raise ValueError(tr("Không có preset chất lượng '{name}'", name=quality))
    save_project_setting(root, "quality", None if quality == "auto" else quality)
    cfg.quality = quality
    set_input_mode(cfg, "")
    return tr("Gõ mục tiêu → trưởng nhóm lập kế hoạch · chất lượng: {v}", v=quality_label(quality))


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
        if effort and a and a.efforts_for() and effort not in a.efforts_for():
            raise ValueError(tr("Bước {i}: effort '{effort}' không hợp lệ cho {agent} ({v})", i=i, effort=effort,
                                agent=a.name, v=", ".join(a.efforts_for())))
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
