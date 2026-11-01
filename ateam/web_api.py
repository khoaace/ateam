"""Tab 🛰 API của giao diện web — bọc `apiclient` thành thao tác `{"op": "http", "action": …}`.

Request đang soạn gửi kèm từ trình duyệt (chưa cần lưu); collection lấy từ đĩa để có biến của nó. Secret chỉ trả
tên, không trả giá trị (web từ xa cũng an toàn). `--readonly`: chỉ cho thao tác đọc (READONLY)."""
from __future__ import annotations

import shlex
import shutil
import sys
from typing import TYPE_CHECKING

from . import apiclient as A
from . import prompts as P
from .i18n import get_lang, tr

if TYPE_CHECKING:
    from .web import WebApp

READONLY = ("state", "get", "history", "env_get", "curl")
SLOW = ("send", "run", "scan")
MAX_FIX_BODY = 4000   # ký tự body response gửi kèm prompt sửa lỗi


class ApiWeb:
    def __init__(self, app: "WebApp"):
        self.app = app
        self.root = app.root

    def ports(self) -> list:
        """Port dev server đang chạy ở tab Terminal — gợi ý base_url."""
        out = []
        for j in self.app.shell.jobs.values():
            if j.alive:
                out += [p for p in j.ports if p not in out]
        return out

    def state(self) -> dict:
        cols = []
        for n in A.list_collections(self.root):
            c = A.load_collection(self.root, n) or {}
            cols.append({"name": n, "count": len(c.get("requests") or [])})
        return {"collections": cols, "envs": A.list_envs(self.root), "secrets": sorted(A.load_secrets(self.root)),
                "ports": self.ports(), "dir": ".ateam/api/"}

    def server_log(self, n: int = 80) -> str:
        """Dòng cuối của dev server đang chạy ở tab Terminal (lệnh còn sống có port) — gửi kèm prompt sửa lỗi."""
        jobs = [j for j in self.app.shell.jobs.values() if j.alive and j.ports]
        return "\n".join(jobs[-1].lines[-n:]) if jobs else ""

    @staticmethod
    def run_cmd(coll: str, env: str = "", only: str = "") -> str:
        """Lệnh `ateam api run …` chạy được trong shell của lệnh kiểm tra (cài từ mã nguồn: python -m ateam)."""
        exe = "ateam" if shutil.which("ateam") else f"{shlex.quote(sys.executable)} -m ateam"
        return " ".join([exe, "api", "run", shlex.quote(coll)] + (["--env", shlex.quote(env)] if env else [])
                        + (["--only", shlex.quote(only)] if only else []))

    def fix_prompt(self, d: dict) -> tuple:
        """(tiêu đề, prompt) giao agent sửa request lỗi — mọi giá trị secret thay bằng {{tên}}."""
        req, res = d.get("request") or {}, d.get("result") or {}
        coll, env = self._coll(d), str(d.get("env") or "")
        sec = A.load_secrets(self.root)
        p = A.prepare(req, A.variables(self.root, coll, env))
        body = p["body"].decode("utf-8", "replace") if p["body"] else ""
        rq = A.mask("\n".join([f"{p['method']} {p['url']}"] + [f"{k}: {v}" for k, v in p["headers"]]
                               + ([""] + [body] if body else [])), sec)
        rp = res.get("response") or {}
        if rp.get("error"):
            rs = "(no response) " + str(rp["error"])
        else:
            text = str(rp.get("body") or "")
            rs = A.mask("\n".join([f"HTTP {rp.get('status')} {rp.get('reason') or ''} ({rp.get('ms')} ms)"]
                                   + [f"{k}: {v}" for k, v in rp.get("headers") or []] + ["",
                                   text[:MAX_FIX_BODY] + ("\n…(truncated)" if len(text) > MAX_FIX_BODY else "")]), sec)
        failed = [A.mask(str(a.get("msg") or a.get("line")), sec) for a in res.get("asserts") or [] if not a.get("ok")]
        prompt = P.api_fix_prompt(request=rq, response=rs, failed=failed, server_log=A.mask(self.server_log(), sec),
                                  note=str(d.get("note") or "").strip(), lang=get_lang(),
                                  rerun=self.run_cmd(str(d.get("collection") or ""), env, str(req.get("name") or ""))
                                  if d.get("collection") else "(send the request again from the 🛰 API tab)")
        return tr("Sửa API: {v}", v=f"{p['method']} {A.mask(p['url'], sec)}")[:80], prompt

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
            await self.app.command("/verify " + self.run_cmd(name, str(d.get("env") or "")))
            return tr("✅ Từ giờ chạy collection “{name}” sau mỗi task (dev server phải đang chạy) — tắt: /verify off",
                      name=name), "ok"
        if act == "history":
            return "", "", {"http": {"history": A.load_history(root)}}
        if act == "import_curl":
            try:
                return "", "", {"http": {"request": A.from_curl(str(d.get("text") or ""))}}
            except ValueError as e:
                return str(e), "warn"
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
