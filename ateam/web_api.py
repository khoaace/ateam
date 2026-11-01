"""Tab 🛰 API của giao diện web — bọc `apiclient` thành thao tác `{"op": "http", "action": …}`.

Request đang soạn gửi kèm từ trình duyệt (chưa cần lưu); collection lấy từ đĩa để có biến của nó. Secret chỉ trả
tên, không trả giá trị (web từ xa cũng an toàn). `--readonly`: chỉ cho thao tác đọc (READONLY)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import apiclient as A
from .i18n import tr

if TYPE_CHECKING:
    from .web import WebApp

READONLY = ("state", "get", "history", "env_get", "curl")
SLOW = ("send", "run", "scan")


class ApiWeb:
    def __init__(self, app: "WebApp"):
        self.app = app
        self.root = app.root

    def ports(self) -> list:
        return A.dev_ports(self.app.shell)

    def state(self) -> dict:
        cols = []
        for n in A.list_collections(self.root):
            c = A.load_collection(self.root, n) or {}
            cols.append({"name": n, "count": len(c.get("requests") or [])})
        return {"collections": cols, "envs": A.list_envs(self.root), "secrets": sorted(A.load_secrets(self.root)),
                "ports": self.ports(), "dir": ".ateam/api/"}

    def server_log(self) -> str:
        return A.dev_log(self.app.shell)

    def fix_prompt(self, d: dict) -> tuple:
        return A.fix_task(self.root, d, self.server_log())

    def _coll(self, d: dict) -> dict | None:
        name = str(d.get("collection") or "")
        return A.load_collection(self.root, name) if name else None

    async def op(self, d: dict) -> tuple | None:
        act = str(d.get("action") or "")
        root = self.root
        if act == "state":
            return "", "", {"http": self.state()}
        if act == "get":
            c = self._coll(d)
            if not c:
                return tr("Không thấy collection '{name}'", name=d.get("collection")), "warn"
            return "", "", {"http": {"collection": c}}
        if act == "new":
            name = A.slug(d.get("name") or "")
            if not str(d.get("name") or "").strip():
                return tr("Nhập tên collection"), "warn"
            if name in A.list_collections(root):
                return tr("Đã có collection “{name}”", name=name), "warn"
            ports = self.ports()
            vs = {"base_url": f"http://localhost:{ports[0]}"} if ports else {}
            A.save_collection(root, {"name": name, "vars": vs, "requests": []}, name)
            return "", "", {"http": {**self.state(), "created": name}}
        if act == "save":
            c = d.get("data")
            if not isinstance(c, dict):
                return tr("Thiếu dữ liệu collection"), "warn"
            name = str(d.get("collection") or c.get("name") or "")
            c["requests"] = [r for r in c.get("requests") or [] if isinstance(r, dict)]
            ids = [r.get("id") for r in c["requests"] if isinstance(r.get("id"), int)]
            nxt = max(ids + [0]) + 1
            for r in c["requests"]:
                if not isinstance(r.get("id"), int):
                    r["id"], nxt = nxt, nxt + 1
            stem = A.save_collection(root, c, name)
            return "", "", {"http": {"collection": A.load_collection(root, stem), "saved": stem}}
        if act == "delete":
            p = A.api_dir(root) / f"{A.slug(d.get('collection') or '')}.json"
            if p.is_file():
                p.unlink()
            return "", "", {"http": self.state()}
        if act in ("send", "curl"):
            req = d.get("request")
            if not isinstance(req, dict):
                return tr("Thiếu request"), "warn"
            coll, env = self._coll(d), str(d.get("env") or "")
            if act == "curl":
                p = A.prepare(req, A.variables(root, coll, env))
                return "", "", {"http": {"curl": A.to_curl(p, A.load_secrets(root))}}
            r = await A.run_request(root, coll, req, env)
            r["curl"] = A.to_curl(A.prepare(req, A.variables(root, coll, env)), A.load_secrets(root))
            r["response"]["body"] = A.mask(r["response"].get("body") or "", A.load_secrets(root))
            return "", "", {"http": {"result": r, "secrets": sorted(A.load_secrets(root))}}
        if act == "run":
            coll = self._coll(d)
            if not coll:
                return tr("Không thấy collection '{name}'", name=d.get("collection")), "warn"
            rows: list = []
            await A.run_collection(root, coll, str(d.get("env") or ""), str(d.get("only") or ""), on_result=lambda req, r:
                                   rows.append({"name": req.get("name") or "", "id": req.get("id"), "ok": r["ok"],
                                                "status": r["response"].get("status"), "ms": r["response"].get("ms"),
                                                "error": r["response"].get("error", ""), "asserts": r["asserts"]}))
            ok = sum(1 for x in rows if x["ok"])
            lvl = "ok" if ok == len(rows) else "warn"
            return (tr("{ok}/{n} request đạt", ok=ok, n=len(rows)), lvl,
                    {"http": {"run": rows, "secrets": sorted(A.load_secrets(root))}})
        if act == "scan":
            c = self._coll(d)
            have = [f"{r.get('method') or 'GET'} {r.get('url') or ''}" for r in (c or {}).get("requests") or []]
            ok, res = await self.app.orch.api_scan(have, str(d.get("focus") or ""), str(d.get("agent") or ""))
            return (res, "warn") if not ok else ("", "", {"http": {"scan": res}})
        if act == "fix":
            agents = self.app.cfg.active_agents()
            agent = str(d.get("agent") or "")
            if agent not in agents:
                agent = self.app.cfg.lead
            title, prompt = self.fix_prompt(d)
            tid = self.app.orch.add_task(agent, prompt, title)
            return tr("🛠 Đã giao {agent} sửa (task #{tid})", agent=agent, tid=tid), "ok", {"open": {"task_link": tid}}
        if act == "verify":
            name = str(d.get("collection") or "")
            if not self._coll(d):
                return tr("Không thấy collection '{name}'", name=name), "warn"
            await self.app.command("/verify " + A.run_cmd(name, str(d.get("env") or "")))
            return tr("✅ Từ giờ chạy collection “{name}” sau mỗi task (dev server phải đang chạy) — tắt: /verify off",
                      name=name), "ok"
        if act == "history":
            return "", "", {"http": {"history": A.load_history(root)}}
        if act == "import":  # lệnh curl -> một request; JSON Postman / OpenAPI -> collection mới
            try:
                res = A.import_text(str(d.get("text") or ""))
            except ValueError as e:
                return str(e), "warn"
            if "request" in res:
                return "", "", {"http": {"request": res["request"]}}
            c = res["collection"]
            c["name"] = A.unique_name(root, c["name"])
            A.save_collection(root, c, c["name"])
            return (tr("Đã nhập {n} request vào collection “{name}”", n=len(c["requests"]), name=c["name"]), "ok",
                    {"http": {**self.state(), "created": c["name"]}})
        if act == "env_get":
            name = str(d.get("env") or "")
            return "", "", {"http": {"env": name, "values": A.load_env(root, name)}}
        if act == "env_save":
            name = str(d.get("env") or "").strip()
            vals = d.get("values")
            if not name or not isinstance(vals, dict):
                return tr("Nhập tên môi trường"), "warn"
            A.save_env(root, name, {str(k).strip(): str(v) for k, v in vals.items() if str(k).strip()})
            return tr("Đã lưu môi trường “{name}”", name=A.slug(name)), "ok", {"http": self.state()}
        if act == "env_delete":
            p = A.api_dir(root) / "env" / f"{A.slug(d.get('env') or '')}.json"
            if p.is_file():
                p.unlink()
            return "", "", {"http": self.state()}
        if act == "secret_set":
            key = str(d.get("key") or "").strip()
            if not key:
                return tr("Nhập tên secret"), "warn"
            A.save_secrets(root, {**A.load_secrets(root), key: str(d.get("value") or "")})
            return "", "", {"http": self.state()}
        if act == "secret_delete":
            sec = A.load_secrets(root)
            sec.pop(str(d.get("key") or ""), None)
            A.save_secrets(root, sec)
            return "", "", {"http": self.state()}
        return tr("Không hiểu thao tác {op}", op="http " + act), "warn"
