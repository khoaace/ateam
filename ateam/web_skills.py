"""Trang 🧩 Skills của `ateam web` (skills.py): danh mục skill của mọi CLI + dự án + thư viện ateam, bật/tắt theo dự
án, xem, tạo / sửa / nhập / xoá skill trong thư viện, ✨ AI viết skill (theo mô tả hoặc từ mục tiêu đã xong), cài từ
GitHub. Trang: webui/skills.js."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import projects, skills
from .i18n import tr

if TYPE_CHECKING:
    from .web import WebApp

OPS = ("skills_list", "skill_view", "skills", "skill_ai", "skill_fetch", "skill_install", "skill_discard")
READONLY = ("skills_list", "skill_view")
SLOW = ("skill_ai", "skill_fetch", "skill_install")  # gọi agent / mạng: không chặn các thao tác khác


class SkillsOps:
    def __init__(self, app: "WebApp") -> None:
        self.app = app

    def state(self) -> dict:
        root = self.app.root
        sets = skills.load_sets(root)
        return {"skills": [s.as_dict(skills.is_on(s, sets)) for s in skills.scan(root)],
                "library": projects.shorten(skills.library()),
                "agents": list(self.app.cfg.active_agents()), "lead": self.app.cfg.lead}

    async def handle(self, d: dict) -> tuple | None:
        op, root = d.get("op"), self.app.root
        name = str(d.get("name") or "").strip()
        if op == "skills_list":
            return "", "", self.state()
        if op == "skill_view":
            s = skills.find(skills.scan(root), name)
            if not s:
                return tr("Không còn skill '{n}'", n=name), "warn"
            view = dict(s.as_dict(skills.is_on(s, skills.load_sets(root))), text=s.text(), files=s.files())
            return "", "", {"skill_view": view}
        if op == "skills":
            act, err, msg = d.get("action"), "", ""
            if act == "toggle":
                skills.set_on(root, name, bool(d.get("on")))
            elif act == "create":
                err = skills.create(name, str(d.get("description") or ""), str(d.get("body") or ""),
                                    bool(d.get("overwrite")))
                msg = tr("🧩 Đã tạo skill '{n}' trong thư viện", n=name)
            elif act == "update":
                err = skills.update(name, str(d.get("text") or ""))
                msg = tr("Đã lưu skill '{n}'", n=name)
            elif act == "delete":
                err = await skills.delete(name)
                msg = tr("Đã chuyển skill '{n}' vào Thùng rác", n=name)
            elif act == "import":
                s = skills.find(skills.scan(root), name)
                err = skills.import_skill(s, bool(d.get("overwrite"))) if s else tr("Không còn skill '{n}'", n=name)
                msg = tr("Đã chép skill '{n}' vào thư viện", n=name)
            else:
                err = tr("Không hiểu thao tác {v}", v=act)
            return (err, "warn", self.state()) if err else (msg, "ok" if msg else "", self.state())
        if op == "skill_ai":
            gid = d.get("goal")
            ok, res = await self.app.orch.write_skill(str(d.get("description") or ""),
                                                      int(gid) if gid not in (None, "") else None,
                                                      str(d.get("agent") or ""), str(d.get("focus") or ""))
            if not ok:
                return str(res), "warn"
            return tr("✨ Đã viết skill '{n}' — xem lại rồi bấm Lưu", n=res["name"]), "ok", {"skill_draft": res}
        if op == "skill_fetch":
            token, found, err = await skills.fetch(str(d.get("url") or ""))
            if err:
                return err, "warn"
            return tr("Tìm thấy {n} skill", n=len(found)), "ok", {"skill_fetch": {"token": token, "skills": found}}
        if op == "skill_install":
            done, errs = await skills.install(str(d.get("token") or ""), [str(x) for x in d.get("names") or []],
                                              bool(d.get("overwrite")))
            text = "; ".join(([tr("🧩 Đã cài {v}", v=", ".join(done))] if done else []) + errs)
            return text, "warn" if errs else "ok", dict(self.state(), skill_installed=done)
        if op == "skill_discard":
            skills.discard(str(d.get("token") or ""))
            return None
        return None
