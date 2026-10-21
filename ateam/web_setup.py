"""/setup (wizard thiết lập đội), /custom (agent & workflow tuỳ chỉnh) và tuỳ chọn dùng chung (vim, màu nhấn)
cho giao diện web — logic nằm ở `wizard.py`/`config.py`, dùng chung với TUI."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from aiohttp import web

from . import mentions, theme, wizard
from .config import (INSTALL_HINTS, LEAD_ALIAS, PROVIDERS, ROLES, TIERS, WORKFLOW_TEMPLATES, agent_from_dict,
                     agent_templates, clear_agent_state, load_custom, load_state, mark_setup_done, plan_team,
                     provider_of, provider_template, save_custom_item, save_onboard, save_state, tier_preset,
                     workflow_to_dict)
from .i18n import tr

if TYPE_CHECKING:
    from .web import WebApp


def _assign_in(raw: dict) -> dict:
    """assign từ trình duyệt ({role: [cli, model, effort] | null}) → dạng của config.plan_team."""
    out = {}
    for k, _l, _d in ROLES:
        v = raw.get(k)
        out[k] = (str(v[0]), str(v[1] or ""), str(v[2] or "")) if v and v[0] else None
    return out


def _assign_out(assign: dict) -> dict:
    return {k: list(v) if v else None for k, v in assign.items()}


def plan_json(plan) -> dict:
    return {"lead": plan.lead, "unused": plan.unused,
            "agents": [{"name": n, "provider": a["provider"], "provider_label": PROVIDERS[a["provider"]][0],
                        "model": a["model"], "effort": a["effort"], "builtin": a["builtin"],
                        "roles": [dict((k, lbl) for k, lbl, _d in ROLES)[r] for r in a["roles"]]}
                       for n, a in plan.agents.items()]}


def preview(a) -> dict:
    """Lệnh sẽ chạy + trạng thái cài của một agent (form /custom)."""
    return {"argv": " ".join(a.argv("<prompt>", model=a.model or None, effort=a.effort or None)) if a.command else "",
            "installed": a.installed(), "binary": a.binary, "full": a.full_access,
            "file": mentions.describe(a.binary, a.file_ref, a.file_args, a.image_args) if a.command else "",
            "no_prompt": bool(a.command) and not any("{prompt}" in c for c in a.command)}


class SetupWeb:
    def __init__(self, app: "WebApp"):
        self.app = app

    def routes(self) -> list:
        return [web.get("/api/setup", self.api_setup), web.get("/api/setup/assign", self.api_assign),
                web.get("/api/setup/plan", self.api_plan), web.get("/api/custom", self.api_custom),
                web.get("/api/custom/quick", self.api_quick), web.get("/api/custom/template", self.api_template),
                web.get("/api/default_flow", self.api_default_flow),
                web.get("/api/prefs", self.api_prefs)]

    @property
    def cfg(self):
        return self.app.cfg

    # ------------------------------------------------------------------ /setup
    async def api_setup(self, _r: web.Request) -> web.Response:
        init = wizard.initial(self.cfg, self.app.root)
        init["assign"] = _assign_out(init["assign"])
        provs, holders = list(PROVIDERS), wizard.role_agents(self.cfg)
        return web.json_response({
            "init": init, "discovering": self.app.discovering,
            "steps": [{"key": k, "title": t, "short": s} for k, t, s in wizard.STEPS],
            "providers": [{"key": p, "label": PROVIDERS[p][0], "installed": p in init["installed"],
                           "hint": INSTALL_HINTS.get(p, p)} for p in provs],
            "styles": [{"key": k, "label": lb, "hint": h} for k, lb, h in wizard.STYLES],
            "tiers": [{"key": k, "label": lb, "hint": wizard.TIER_HINTS[k]} for k, lb in TIERS],
            "roles": [{"key": k, "label": lb, "desc": d, "agent": holders.get(k, "")} for k, lb, d in ROLES],
            "access": [{"key": k, "label": lb, "hint": h} for k, lb, h in wizard.ACCESS],
            "apply": [{"key": k, "label": lb, "hint": h} for k, lb, h in wizard.APPLY],
            "verify": [{"key": k, "label": lb, "hint": h} for k, lb, h in
                       wizard.verify_choices(self.app.root, init["verify"])],
            "models": {p: wizard.models_of(self.cfg, p) for p in provs},
            "efforts": {p: wizard.efforts_of(p) for p in provs},
            "custom_others": [n for n in self.cfg.custom_agents if n in self.cfg.agents and not
                              load_custom().get("agents", {}).get(n, {}).get("wizard")],
            "quick_providers": wizard.quick_providers(init)})

    async def api_assign(self, r: web.Request) -> web.Response:
        """Gán mặc định khi đổi bộ CLI / mức (?providers=a,b&tier=x), hoặc một vai trò (?role=&provider=)."""
        q = r.query
        tier = q.get("tier", "balanced")
        if q.get("role"):
            p = q.get("provider", "")
            if not p:
                return web.json_response(None)
            return web.json_response([p] + list(tier_preset(p, tier, q["role"], wizard.models_of(self.cfg, p),
                                                            wizard.efforts_of(p))))
        providers = [p for p in q.get("providers", "").split(",") if p in PROVIDERS]
        return web.json_response(_assign_out(wizard.default_assign(self.cfg, providers, tier)))

    async def api_plan(self, r: web.Request) -> web.Response:
        return web.json_response(plan_json(plan_team(_assign_in(json.loads(r.query.get("assign", "{}"))))))

    async def save_setup(self, d: dict) -> tuple:
        """Lưu wizard: như OnboardScreen.action_save + TeamApp._setup_done."""
        plan = plan_team(_assign_in(d.get("assign") or {}))
        if not plan.lead:
            return tr("Chưa có trưởng nhóm — chọn CLI cho vai trò ★ Trưởng nhóm"), "error"
        settings = wizard.settings_of(str(d.get("style") or "approve"), str(d.get("access") or "safe"),
                                      str(d.get("apply") or "shared"), str(d.get("verify") or ""),
                                      str(d.get("flow_name") or ""))
        save_onboard(self.app.root, plan, **settings)
        await self.app.reload_config(setup=True)
        c = self.cfg
        on = [f"{n} ({a.label()})" for n, a in c.active_agents().items()]
        flow = (tr(" Gõ mục tiêu → workflow '{default_workflow}' (/goal: trưởng nhóm lập kế hoạch).",
                   default_workflow=c.default_workflow) if c.default_workflow else "")
        self.app.orch.log(tr("⚙ Đã lưu thiết lập. Trưởng nhóm: {lead}. Đội: {v}.{flow} Đổi lại: "
                             "/setup, /model, /effort.", lead=c.lead, v=', '.join(on), flow=flow))
        return tr("Đã lưu thiết lập"), "ok", {"setup_saved": True}

    async def save_roles(self, d: dict) -> tuple:
        """⚡ Sửa nhanh vai trò (/roles): chỉ bảng vai trò · CLI · model · effort, thiết lập khác giữ nguyên."""
        plan = plan_team(_assign_in(d.get("assign") or {}))
        if not plan.lead:
            return tr("Chưa có trưởng nhóm — chọn CLI cho vai trò ★ Trưởng nhóm"), "error"
        save_onboard(self.app.root, plan, **wizard.current_settings(self.cfg, self.app.root))
        await self.app.reload_config(setup=True)
        team = ", ".join(f"{n} ({a.label()})" for n, a in self.cfg.active_agents().items())
        self.app.orch.log(tr("⚡ Đã lưu vai trò. Trưởng nhóm: {lead}. Đội: {v}.", lead=self.cfg.lead, v=team))
        return tr("Đã lưu vai trò"), "ok", {"setup_saved": True}

    def skip_setup(self) -> tuple:
        mark_setup_done()
        self.app.orch.log(tr("ℹ Bỏ qua thiết lập. Mở lại bất cứ lúc nào bằng /setup (hoặc `ateam setup`)."))
        return None

    # ------------------------------------------------------------------ /custom
    async def api_custom(self, _r: web.Request) -> web.Response:
        cfg, custom = self.cfg, load_custom()
        agents = []
        for name in sorted(cfg.custom_agents):
            a = cfg.agents.get(name)
            if a is None:
                continue
            raw = (custom.get("agents") or {}).get(name, {})
            agents.append({"name": name, "installed": a.installed(), "argv": " ".join(a.argv("<prompt>")),
                           "quick": bool(provider_of(raw.get("command"))), "raw": raw,
                           "fields": wizard.agent_fields_text(raw), "in_file": name in (custom.get("agents") or {}),
                           "provider": provider_of(raw.get("command")) or ""})
        flows = []
        for name, w in cfg.workflows.items():
            raw = (custom.get("workflows") or {}).get(name)
            body = raw if raw is not None else workflow_to_dict(w)
            flows.append({"name": name, "steps": len(w.steps), "summary": w.summary(), "description": w.description,
                          "in_file": raw is not None, "raw": body,
                          "step_rows": [dict(st, after=wizard.after_text(st.get("after"))) for st in body.get("steps", [])]})
        return web.json_response({
            "agents": agents, "workflows": flows, "lead": cfg.lead, "agent_names": list(cfg.agents),
            "default_workflow": cfg.default_workflow,
            "auto_review": cfg.auto_review,
            "step_agents": [{"label": lb, "value": v} for lb, v in wizard.flow_agents(cfg)],
            "step_choices": {v: dict(zip(("models", "efforts"), wizard.flow_step_choices(cfg, v)))
                             for v in [LEAD_ALIAS] + list(cfg.agents)},
            "providers": [{"key": p, "label": PROVIDERS[p][0], "installed": p in wizard.installed_providers()}
                          for p in PROVIDERS],
            "fields": [{"id": f, "label": lb, "hint": h} for f, lb, h, _k, _t in wizard.AGENT_FIELDS],
            "agent_templates": list(agent_templates()),
            "workflow_templates": [{"key": k, "description": v.get("description", "")}
                                   for k, v in WORKFLOW_TEMPLATES.items()],
            "sources": [str(s) for s in cfg.sources]})

    async def api_quick(self, r: web.Request) -> web.Response:
        """Lựa chọn của form agent nhanh theo nhà cung cấp: model, effort, vai trò mẫu, tên gợi ý."""
        p = r.query.get("provider", "claude")
        if p not in PROVIDERS:
            return web.json_response({"error": p})
        return web.json_response({"models": wizard.quick_models(self.cfg, p),
                                  "efforts": [str(e) for e in provider_template(p).get("efforts") or []],
                                  "role": str(provider_template(p).get("role", "")),
                                  "name": wizard.auto_name(self.cfg, PROVIDERS[p][1])})

    async def api_template(self, r: web.Request) -> web.Response:
        q = r.query
        if q.get("kind") == "workflow":
            if q.get("key") not in WORKFLOW_TEMPLATES:
                return web.json_response({})
            raw = wizard.workflow_template(self.cfg, q["key"])
            return web.json_response(dict(raw, step_rows=[dict(st, after=wizard.after_text(st.get("after")))
                                                          for st in raw.get("steps", [])]))
        tpls = agent_templates()
        key = q.get("key", "")
        if key not in tpls:
            return web.json_response({})
        base = key.split()[0]
        return web.json_response({"fields": wizard.agent_fields_text(tpls[key]), "raw": tpls[key],
                                  "name": wizard.auto_name(self.cfg, "my-agent" if base == "trống" else base)})

    def _agent_from_form(self, d: dict) -> tuple[str, dict]:
        """Form agent (nhanh hoặc nâng cao) → (tên, thân TOML). Lỗi -> ValueError."""
        name, old = str(d.get("name") or "").strip(), d.get("old") or None
        if d.get("mode") == "quick":
            p = str(d.get("provider") or "")
            if p not in PROVIDERS:
                raise ValueError(tr("Chọn nhà cung cấp"))
            wizard.check_agent_name(self.cfg, name, old)
            return name, wizard.quick_body(self.cfg, p, str(d.get("model") or ""), str(d.get("effort") or ""),
                                           str(d.get("role") or ""), bool(d.get("full")))
        body = wizard.agent_body(d.get("fields") or {}, pty=bool(d.get("pty")), verify=d.get("verify", True)
                                 is not False, full=bool(d.get("full")))
        wizard.check_agent(self.cfg, name, old, body)
        return name, body

    def preview_agent(self, d: dict) -> tuple:
        if d.get("mode") == "fields":  # form nhanh → nâng cao: thân TOML thành chữ từng ô
            return "", "", {"preview": {"fields": wizard.agent_fields_text(d.get("raw") or {})}}
        try:
            if d.get("mode") == "quick":
                p = str(d.get("provider") or "claude")
                body = wizard.quick_body(self.cfg, p, str(d.get("model") or ""), str(d.get("effort") or ""),
                                         str(d.get("role") or ""), bool(d.get("full")))
            else:
                body = wizard.agent_body(d.get("fields") or {}, pty=bool(d.get("pty")),
                                         verify=d.get("verify", True) is not False, full=bool(d.get("full")))
            out = preview(agent_from_dict(str(d.get("name") or "agent").strip() or "agent", body))
            out["body"] = body
        except ValueError as e:
            out = {"error": str(e)}
        return "", "", {"preview": out}

    async def save_custom(self, d: dict) -> tuple:
        kind, old = d.get("kind"), d.get("old") or None
        try:
            if kind == "agents":
                name, body = self._agent_from_form(d)
            else:
                name = str(d.get("name") or "").strip()
                body = wizard.workflow_body(self.cfg, name, old, str(d.get("description") or ""),
                                            bool(d.get("review")), d.get("steps") or [])
        except ValueError as e:
            return str(e), "error"
        save_custom_item(kind, name, body, old)
        if kind == "agents":  # giá trị vừa đặt trong form phải có hiệu lực, không để state.json cũ đè
            clear_agent_state(name)
            if old and old != name:
                clear_agent_state(old, keys=("enabled", "model", "effort", "role", "full_access"))
        await self.app.reload_config()
        return tr("Đã lưu {v} '{name}'", v="agent" if kind == "agents" else "workflow", name=name), "ok", \
            {"custom_saved": True}

    async def suggest_workflow(self, d: dict) -> tuple:
        """✨ Gợi ý ở form workflow: trưởng nhóm thiết kế các bước theo mô tả — điền form, chưa lưu."""
        ok, form = await self.app.orch.suggest_workflow(str(d.get("description") or ""))
        if not ok:
            return str(form), "warn"
        return tr("✨ Đã điền {n} bước — xem lại rồi bấm Lưu", n=len(form["steps"])), "ok", {"wf_suggest": form}

    # ------------------------------------------------------------------ popup "Luồng mặc định"
    async def api_default_flow(self, r: web.Request) -> web.Response:
        """Như DefaultFlowScreen: ★ trưởng nhóm (preset chất lượng) hoặc workflow (bước agent/model/effort) + model/effort
        gợi ý của mọi agent. ?setup=1: mở từ /setup — chỉ workflow."""
        in_setup = r.query.get("setup") == "1"
        try:
            form = wizard.flow_form(self.cfg, r.query.get("name", ""), in_setup)
        except ValueError as e:
            return web.json_response({"error": str(e)})
        agents = wizard.flow_agents(self.cfg)
        choices = {v: dict(zip(("models", "efforts"), wizard.flow_step_choices(self.cfg, v))) for _l, v in agents}
        return web.json_response({"form": form, "names": [{"name": n, "label": lb} for n, lb in
                                                          wizard.flow_names(self.cfg, in_setup)],
                                  "agents": [{"label": lb, "value": v} for lb, v in agents], "choices": choices,
                                  "quality": [{"key": k, "label": lb, "hint": h} for k, lb, h in wizard.QUALITY_CHOICES]})

    async def save_default_flow(self, d: dict) -> tuple:
        make_default = d.get("make_default")
        try:
            if d.get("name") == wizard.LEAD_FLOW:
                msg = wizard.save_lead_flow(self.cfg, self.app.root, str(d.get("quality") or "auto"))
            else:
                msg = wizard.save_flow(self.cfg, str(d.get("name") or ""), list(d.get("steps") or []),
                                       bool(d.get("review")), None if make_default is None else bool(make_default))
        except ValueError as e:
            return str(e), "error"
        await self.app.reload_config()
        return msg, "ok", {"flow_saved": str(d.get("name") or "")}

    async def delete_custom(self, d: dict) -> tuple:
        kind, name = d.get("kind"), str(d.get("name") or "")
        if kind == "agents" and name == self.cfg.lead:
            return tr("'{name}' đang là trưởng nhóm — đổi trưởng nhóm ở /setup trước.", name=name), "error"
        if name not in (load_custom().get(kind) or {}):
            return tr("'{name}' nằm trong file cấu hình khác ({v}) — sửa file đó để xoá.", name=name,
                      v=", ".join(map(str, self.cfg.sources))), "warn"
        save_custom_item(kind, name, None)
        await self.app.reload_config()
        return tr("Đã xoá '{name}'", name=name), "ok", {"custom_saved": True}

    # ------------------------------------------------------------------ tuỳ chọn dùng chung với TUI (state.json)
    async def api_prefs(self, _r: web.Request) -> web.Response:
        st = load_state()
        return web.json_response({"vim": st.get("vim", True) is not False, "accent": st.get("accent") or "",
                                  "accents": [{"key": k, "label": theme.accent_label(k), "color": c}
                                              for k, c in [("", "")] + list(theme.ACCENTS.items())]})

    def set_prefs(self, d: dict) -> tuple | None:
        st = load_state()
        msg = None
        if "vim" in d:
            st["vim"] = bool(d["vim"])
            msg = tr("Phím vim trong tab 📝 Code: bật") if st["vim"] else \
                tr("Phím vim trong tab 📝 Code: tắt (Ctrl+S lưu)")
        for key, label in (("fmt_save", tr("Format khi lưu")), ("autosave", tr("Tự lưu"))):
            if key in d:
                st[key] = bool(d[key])
                msg = tr("{v}: bật", v=label) if st[key] else tr("{v}: tắt", v=label)
        if "accent" in d:
            acc = theme.normalize_accent(str(d["accent"] or ""))
            if acc is None:
                return tr("Không có màu nhấn {name} — có: {v}", name=d["accent"], v=", ".join(theme.ACCENTS)), "warn"
            st["accent"] = acc
            msg = tr("Màu nhấn: {v}", v=theme.accent_label(acc))
        save_state(st)
        self.app.broadcast_prefs()
        return (msg, "ok") if msg else None
