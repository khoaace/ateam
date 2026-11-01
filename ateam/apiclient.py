"""Gọi thử HTTP API kiểu Postman (tab 🛰 API, `ateam api run`). Không phụ thuộc Textual/aiohttp — gửi bằng urllib
trong thread để không treo vòng lặp asyncio.

Lưu trữ:
- `.ateam/api/<tên>.json` — collection (commit được: `.ateam/.gitignore` chừa `api/`):
  {name, vars: {tên: giá trị}, requests: [{id, name, folder, method, url, query: [[k, v, bật]],
  headers: [[k, v, bật]], body: {type: none|json|form|raw, text, form: [[k, v, bật]]},
  auth: {type: none|bearer|basic, token, user, password}, asserts: ["status == 200", …],
  extract: ["token = json $.token", …], timeout, follow, insecure}]}
- `.ateam/api/env/<tên>.json` — biến môi trường không bí mật {tên: giá trị} (commit được).
- Secret + giá trị extract (token đăng nhập…): ~/.config/ateam/api-secrets/…json, ngoài repo.
- Lịch sử gửi: `.ateam/api-history.json` (bị .gitignore của .ateam bỏ qua).

Biến `{{tên}}`: secret > env > vars của collection; `{{$uuid}}`, `{{$timestamp}}`. URL bắt đầu bằng "/" thì
nối sau `{{base_url}}` (nếu có biến đó)."""
from __future__ import annotations

import asyncio
import base64
import json
import re
import shlex
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Callable, Optional

from . import prompts as P
from . import todos
from .i18n import get_lang, tr

MAX_BODY = 2 * 1024 ** 2   # byte body response giữ lại
HISTORY_MAX = 50
MAX_FIX_BODY = 4000   # ký tự body response gửi kèm prompt sửa lỗi
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")
GITIGNORE = "*\n!api/\n!api/**\n"   # .ateam/.gitignore: chỉ collection/env được commit
VAR_RE = re.compile(r"\{\{\s*(\$?[\w.-]+)\s*\}\}")
OPS = ("==", "!=", "<=", ">=", "<", ">", "contains", "!contains", "matches", "exists", "!exists")
_OP_RE = "|".join(re.escape(o) for o in sorted(OPS, key=len, reverse=True))
ASSERT_RE = re.compile(rf"^\s*(?:(status|time|size)|(json|header)\s+(\S+)|(body))\s*({_OP_RE})(?:\s+(.*?))?\s*$")
EXTRACT_RE = re.compile(r"^\s*([\w.-]+)\s*=\s*(json|header)\s+(\S+)\s*$")


# ---------------------------------------------------------------------------- lưu trữ
def api_dir(root: Path) -> Path:
    return Path(root) / ".ateam" / "api"


def slug(name: str) -> str:
    s = re.sub(r"[^\w.-]+", "-", str(name or "").strip(), flags=re.U).strip("-.")
    return s[:60] or "api"


def _read_json(p: Path, default):
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return v if isinstance(v, type(default)) else default


def _write_json(p: Path, v) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def list_collections(root: Path) -> list:
    d = api_dir(root)
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def load_collection(root: Path, name: str) -> Optional[dict]:
    p = api_dir(root) / f"{slug(name)}.json"
    if not p.is_file():
        return None
    c = _read_json(p, {})
    c.setdefault("name", p.stem)
    c["vars"] = c.get("vars") if isinstance(c.get("vars"), dict) else {}
    c["requests"] = [r for r in c.get("requests") or [] if isinstance(r, dict)]
    for i, r in enumerate(c["requests"], 1):
        r.setdefault("id", i)
    return c


def save_collection(root: Path, coll: dict, name: str = "") -> str:
    """Ghi collection vào .ateam/api/<tên>.json; trả tên file (không đuôi)."""
    stem = slug(name or coll.get("name") or "api")
    _write_json(api_dir(root) / f"{stem}.json", coll)
    return stem


def list_envs(root: Path) -> list:
    d = api_dir(root) / "env"
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def load_env(root: Path, name: str) -> dict:
    return _read_json(api_dir(root) / "env" / f"{slug(name)}.json", {}) if name else {}


def save_env(root: Path, name: str, values: dict) -> None:
    _write_json(api_dir(root) / "env" / f"{slug(name)}.json", values)


def secrets_path(root: Path) -> Path:
    return todos.path_for(root, "api-secrets")


def load_secrets(root: Path) -> dict:
    return _read_json(secrets_path(root), {})


def save_secrets(root: Path, values: dict) -> None:
    _write_json(secrets_path(root), values)


def history_path(root: Path) -> Path:
    return Path(root) / ".ateam" / "api-history.json"


def load_history(root: Path) -> list:
    return _read_json(history_path(root), [])


def add_history(root: Path, entry: dict) -> None:
    items = [entry] + load_history(root)
    _write_json(history_path(root), items[:HISTORY_MAX])


def ensure_gitignore(state: Path) -> None:
    """.ateam/.gitignore: bỏ qua mọi thứ trừ api/ (collection chia sẻ được). File cũ đúng bằng "*" thì nâng cấp;
    người dùng tự sửa nội dung khác thì giữ nguyên."""
    gi = state / ".gitignore"
    try:
        cur = gi.read_text()
    except OSError:
        cur = None
    if cur is None or cur.strip() == "*":
        gi.write_text(GITIGNORE)


# ---------------------------------------------------------------------------- biến
def variables(root: Path, coll: Optional[dict] = None, env: str = "") -> dict:
    out = {}
    out.update({k: str(v) for k, v in ((coll or {}).get("vars") or {}).items()})
    out.update({k: str(v) for k, v in load_env(root, env).items()})
    out.update({k: str(v) for k, v in load_secrets(root).items()})
    return out


def render(s, vs: dict) -> str:
    def sub(m):
        k = m.group(1)
        if k == "$uuid":
            return str(uuid.uuid4())
        if k == "$timestamp":
            return str(int(time.time()))
        return vs.get(k, m.group(0))
    return VAR_RE.sub(sub, str(s if s is not None else ""))


def mask(text: str, secrets: dict) -> str:
    """Thay giá trị secret (≥ 4 ký tự) bằng {{tên}} — trước khi ghi lịch sử, xuất curl, gửi agent."""
    for k, v in sorted(secrets.items(), key=lambda kv: -len(str(kv[1]))):
        v = str(v)
        if len(v) >= 4:
            text = text.replace(v, "{{" + k + "}}")
    return text


def _pairs(rows) -> list:
    """[[k, v, bật?], …] -> [(k, v)] chỉ dòng bật, bỏ khoá trống."""
    out = []
    for r in rows or []:
        if isinstance(r, (list, tuple)) and len(r) >= 2 and str(r[0]).strip() and (len(r) < 3 or r[2]):
            out.append((str(r[0]).strip(), str(r[1])))
    return out


# ---------------------------------------------------------------------------- dựng & gửi
def prepare(req: dict, vs: dict) -> dict:
    """Request mẫu + biến -> {method, url, headers: [(k, v)], body: bytes|None} sẵn sàng gửi."""
    method = str(req.get("method") or "GET").upper()
    url = render(req.get("url") or "", vs).strip()
    if url.startswith("/") and vs.get("base_url"):
        url = vs["base_url"].rstrip("/") + url
    q = [(render(k, vs), render(v, vs)) for k, v in _pairs(req.get("query"))]
    if q:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(q)
    headers = [(render(k, vs), render(v, vs)) for k, v in _pairs(req.get("headers"))]
    names = {k.lower() for k, _ in headers}
    auth = req.get("auth") or {}
    if auth.get("type") == "bearer" and "authorization" not in names:
        headers.append(("Authorization", "Bearer " + render(auth.get("token"), vs)))
    elif auth.get("type") == "basic" and "authorization" not in names:
        raw = f"{render(auth.get('user'), vs)}:{render(auth.get('password'), vs)}".encode()
        headers.append(("Authorization", "Basic " + base64.b64encode(raw).decode()))
    body, b = None, req.get("body") or {}
    kind = b.get("type") or "none"
    if kind in ("json", "raw") and str(b.get("text") or "").strip():
        body = render(b.get("text"), vs).encode()
        if kind == "json" and "content-type" not in names:
            headers.append(("Content-Type", "application/json"))
    elif kind == "form":
        body = urllib.parse.urlencode([(render(k, vs), render(v, vs)) for k, v in _pairs(b.get("form"))]).encode()
        if "content-type" not in names:
            headers.append(("Content-Type", "application/x-www-form-urlencoded"))
    return {"method": method, "url": url, "headers": headers, "body": body}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def send_sync(p: dict, timeout: float = 30, follow: bool = True, insecure: bool = False) -> dict:
    """Gửi request đã prepare. Lỗi HTTP (4xx/5xx) vẫn là response; lỗi mạng -> {error}."""
    if not re.match(r"^https?://", p["url"], re.I):
        return {"error": tr("URL phải bắt đầu bằng http:// hoặc https:// (hoặc / khi có biến base_url)"), "ms": 0}
    handlers = [] if follow else [_NoRedirect()]
    if insecure:
        ctx = ssl.create_default_context()
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
    opener = urllib.request.build_opener(*handlers)
    r = urllib.request.Request(p["url"], data=p["body"], method=p["method"])
    for k, v in p["headers"]:
        r.add_header(k, v)
    if not any(k.lower() == "user-agent" for k, _ in p["headers"]):
        r.add_header("User-Agent", "ateam-api")
    t0 = time.monotonic()
    try:
        resp = opener.open(r, timeout=timeout)
    except urllib.error.HTTPError as e:
        resp = e
    except (urllib.error.URLError, OSError, ValueError) as e:
        why = getattr(e, "reason", None) or e
        return {"error": str(why), "ms": int((time.monotonic() - t0) * 1000)}
    try:
        data = resp.read(MAX_BODY + 1)
    except OSError:
        data = b""
    ms = int((time.monotonic() - t0) * 1000)
    hdrs = [[k, v] for k, v in resp.headers.items()]
    m = re.search(r"charset=([\w-]+)", resp.headers.get("Content-Type", ""), re.I)
    try:
        text = data[:MAX_BODY].decode(m.group(1) if m else "utf-8", errors="replace")
    except LookupError:
        text = data[:MAX_BODY].decode("utf-8", errors="replace")
    out = {"status": resp.status if hasattr(resp, "status") else resp.code, "reason": getattr(resp, "reason", "") or "",
           "headers": hdrs, "body": text, "size": len(data), "truncated": len(data) > MAX_BODY, "ms": ms}
    resp.close()
    return out


async def send(req: dict, vs: dict) -> tuple:
    """(prepare, response) — gửi trong thread."""
    p = prepare(req, vs)
    res = await asyncio.to_thread(send_sync, p, float(req.get("timeout") or 30), req.get("follow", True) is not False,
                                  bool(req.get("insecure")))
    return p, res


# ---------------------------------------------------------------------------- assert / extract
def json_path(data, path: str):
    """`$.a.b[0].c`, `.length` -> (thấy?, giá trị). Không hỗ trợ lọc/wildcard."""
    path = path.strip()
    if path.startswith("$"):
        path = path[1:]
    cur = data
    for key, idx in re.findall(r"\.([^.\[\]]+)|\[(-?\d+)\]", path):
        if idx:
            if not isinstance(cur, list) or not -len(cur) <= int(idx) < len(cur):
                return False, None
            cur = cur[int(idx)]
        elif key == "length" and isinstance(cur, (list, dict, str)):
            cur = len(cur)
        elif isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return False, None
    return True, cur


def _body_json(res: dict):
    try:
        return True, json.loads(res.get("body") or "")
    except ValueError:
        return False, None


def _value(res: dict, src: str, path: str):
    if src == "status":
        return True, res.get("status")
    if src == "time":
        return True, res.get("ms")
    if src == "size":
        return True, res.get("size")
    if src == "body":
        return True, res.get("body") or ""
    if src == "header":
        for k, v in res.get("headers") or []:
            if k.lower() == path.lower():
                return True, v
        return False, None
    ok, data = _body_json(res)
    return json_path(data, path) if ok else (False, None)


def _literal(s: Optional[str]):
    if s is None:
        return None
    try:
        return json.loads(s)
    except ValueError:
        return s


def check_one(line: str, res: dict) -> tuple:
    """(đạt?, lời giải thích) cho một dòng assert."""
    m = ASSERT_RE.match(line or "")
    if not m:
        return False, tr("assert không hiểu: {v}", v=line)
    src = m.group(1) or m.group(2) or m.group(4)
    path, op, raw = m.group(3) or "", m.group(5), m.group(6)
    found, got = _value(res, src, path)
    if op in ("exists", "!exists"):
        return found == (op == "exists"), f"{line}: " + (json.dumps(got, ensure_ascii=False)[:200] if found
                                                         else tr("không có"))
    want = _literal(raw)
    if not found:
        return False, tr("{v}: không có giá trị", v=line)
    try:
        if op == "==":
            ok = got == want or str(got) == str(want)
        elif op == "!=":
            ok = not (got == want or str(got) == str(want))
        elif op in ("contains", "!contains"):
            hay = got if isinstance(got, (list, dict)) else str(got)
            ok = (want in hay if isinstance(hay, (list, dict)) else str(want) in hay) == (op == "contains")
        elif op == "matches":
            ok = re.search(str(want), str(got)) is not None
        else:
            a, b = float(got), float(want)
            ok = {"<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]
    except (TypeError, ValueError, re.error):
        ok = False
    shown = json.dumps(got, ensure_ascii=False) if not isinstance(got, str) else got
    return ok, tr("{v} (thực tế: {got})", v=line, got=" ".join(shown.split())[:200])


def check(asserts: list, res: dict) -> list:
    """[{line, ok, msg}] cho mọi dòng assert không trống. Lỗi mạng: mọi assert sai."""
    out = []
    for line in asserts or []:
        if not str(line).strip():
            continue
        if res.get("error"):
            out.append({"line": line, "ok": False, "msg": tr("{v}: không có response", v=line)})
        else:
            ok, msg = check_one(str(line), res)
            out.append({"line": line, "ok": ok, "msg": msg})
    return out


def extract(rules: list, res: dict) -> dict:
    """{tên: giá trị} lấy từ response theo dòng `tên = json $.path` / `tên = header X-Token`."""
    out = {}
    for line in rules or []:
        m = EXTRACT_RE.match(str(line))
        if not m or res.get("error"):
            continue
        found, v = _value(res, m.group(2), m.group(3))
        if found and v is not None:
            out[m.group(1)] = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return out


async def run_request(root: Path, coll: Optional[dict], req: dict, env: str = "", history: bool = True) -> dict:
    """Gửi một request của collection: biến → gửi → assert → extract (lưu vào secret) → lịch sử.
    Trả {request (đã che secret), response, asserts, extracted, ok}."""
    vs = variables(root, coll, env)
    p, res = await send(req, vs)
    results = check(req.get("asserts"), res)
    got = extract(req.get("extract"), res)
    if got:
        save_secrets(root, {**load_secrets(root), **got})
    secrets = {**load_secrets(root)}
    for x in results:
        x["msg"] = mask(x["msg"], secrets)
    shown = {"method": p["method"], "url": mask(p["url"], secrets),
             "headers": [[k, mask(v, secrets)] for k, v in p["headers"]],
             "body": mask(p["body"].decode("utf-8", "replace"), secrets) if p["body"] else ""}
    ok = not res.get("error") and all(r["ok"] for r in results)
    if history:
        add_history(root, {"at": int(time.time()), "name": req.get("name") or "", "collection": (coll or {}).get("name", ""),
                           "request": {k: req.get(k) for k in ("method", "url", "query", "headers", "body", "auth")},
                           "status": res.get("status"), "ms": res.get("ms"), "error": res.get("error", "")})
    return {"request": shown, "response": res, "asserts": results, "extracted": sorted(got), "ok": ok}


async def run_collection(root: Path, coll: dict, env: str = "", only: str = "",
                         on_result: Optional[Callable[[dict, dict], None]] = None) -> list:
    """Chạy tuần tự (extract của request trước dùng được ở request sau). only: tên hoặc thư mục cần chạy."""
    out = []
    for req in coll.get("requests") or []:
        if only and only not in (req.get("name"), req.get("folder"), str(req.get("id"))):
            continue
        r = await run_request(root, coll, req, env, history=False)
        out.append(r)
        if on_result:
            on_result(req, r)
    return out


def result_lines(r: dict) -> list:
    """Kết quả một request (run_request) thành dòng chữ: ✓/✗ METHOD url → status ms, rồi từng assert."""
    res, head = r["response"], f"{r['request']['method']} {r['request']['url']}"
    out = [f"✗ {head}  — {res['error']}" if res.get("error") else
           f"{'✓' if r['ok'] else '✗'} {head}  → {res['status']}  {res['ms']} ms"]
    return out + [f"    {'✓' if a['ok'] else '✗'} {a['msg']}" for a in r["asserts"]]


async def run_report(root: Path, args: str = "") -> tuple:
    """`/api run [collection] [môi trường]` (web + TUI): (chữ kết quả, đạt hết?). Bỏ tên khi chỉ có một collection."""
    try:
        parts = shlex.split(args)
    except ValueError:
        parts = args.split()
    names = list_collections(root)
    name = parts[0] if parts else (names[0] if len(names) == 1 else "")
    coll = load_collection(root, name) if name else None
    if not coll:
        return tr("Không thấy collection '{name}' — có: {v}", name=name, v=", ".join(names) or tr("(trống)")), False
    lines: list = []
    res = await run_collection(root, coll, parts[1] if len(parts) > 1 else "",
                               on_result=lambda _q, r: lines.extend(result_lines(r)))
    bad = sum(1 for r in res if not r["ok"])
    lines.append(tr("{ok}/{n} request đạt", ok=len(res) - bad, n=len(res)) if res else tr("Không có request nào để chạy"))
    return "\n".join(lines), bool(res) and not bad


# ---------------------------------------------------------------------------- 🛠 giao agent sửa
def dev_ports(shell) -> list:
    """Port dev server đang chạy ở tab Terminal (shell.ShellManager) — gợi ý base_url."""
    out: list = []
    for j in shell.jobs.values():
        if j.alive:
            out += [p for p in j.ports if p not in out]
    return out


def dev_log(shell, n: int = 80) -> str:
    """Dòng cuối của dev server đang chạy ở tab Terminal (lệnh `!` còn sống, có port) — gửi kèm prompt sửa lỗi.
    shell: shell.ShellManager."""
    jobs = [j for j in shell.jobs.values() if j.alive and j.ports]
    return "\n".join(jobs[-1].lines[-n:]) if jobs else ""


def run_cmd(coll: str, env: str = "", only: str = "") -> str:
    """Lệnh `ateam api run …` chạy được trong shell của lệnh kiểm tra (cài từ mã nguồn: python -m ateam)."""
    exe = "ateam" if shutil.which("ateam") else f"{shlex.quote(sys.executable)} -m ateam"
    return " ".join([exe, "api", "run", shlex.quote(coll)] + (["--env", shlex.quote(env)] if env else [])
                    + (["--only", shlex.quote(only)] if only else []))


def fix_task(root: Path, d: dict, server_log: str = "") -> tuple:
    """🛠 Giao agent sửa: (tiêu đề, prompt) từ request mẫu + kết quả gửi (d: collection, env, request, result, note);
    mọi giá trị secret thay bằng {{tên}}. server_log: dòng cuối của dev server đang chạy."""
    req, res, env = d.get("request") or {}, d.get("result") or {}, str(d.get("env") or "")
    name = str(d.get("collection") or "")
    coll = load_collection(root, name) if name else None
    sec = load_secrets(root)
    p = prepare(req, variables(root, coll, env))
    body = p["body"].decode("utf-8", "replace") if p["body"] else ""
    rq = mask("\n".join([f"{p['method']} {p['url']}"] + [f"{k}: {v}" for k, v in p["headers"]]
                        + ([""] + [body] if body else [])), sec)
    rp = res.get("response") or {}
    if rp.get("error"):
        rs = "(no response) " + str(rp["error"])
    else:
        text = str(rp.get("body") or "")
        cut = text[:MAX_FIX_BODY] + ("\n…(truncated)" if len(text) > MAX_FIX_BODY else "")
        rs = mask("\n".join([f"HTTP {rp.get('status')} {rp.get('reason') or ''} ({rp.get('ms')} ms)"]
                            + [f"{k}: {v}" for k, v in rp.get("headers") or []] + ["", cut]), sec)
    failed = [mask(str(a.get("msg") or a.get("line")), sec) for a in res.get("asserts") or [] if not a.get("ok")]
    rerun = run_cmd(name, env, str(req.get("name") or "")) if name else "(send the request again from the 🛰 API tab)"
    prompt = P.api_fix_prompt(request=rq, response=rs, failed=failed, server_log=mask(server_log, sec),
                              note=str(d.get("note") or "").strip(), rerun=rerun, lang=get_lang())
    return tr("Sửa API: {v}", v=f"{p['method']} {mask(p['url'], sec)}")[:80], prompt


# ---------------------------------------------------------------------------- chuẩn hoá (AI quét code, nhập)
def _rows(v) -> list:
    out = []
    for r in v if isinstance(v, list) else []:
        if isinstance(r, (list, tuple)) and len(r) >= 2 and str(r[0]).strip():
            out.append([str(r[0]).strip(), str(r[1]), r[2] is not False if len(r) > 2 else True])
        elif isinstance(r, dict) and str(r.get("key") or "").strip():
            out.append([str(r["key"]).strip(), str(r.get("value") or ""), r.get("enabled", True) is not False])
    return out


def clean_request(r: dict) -> dict:
    """Request do agent viết / người dùng nhập -> đúng khuôn collection (chỉ khoá đã biết, đúng kiểu)."""
    method = str(r.get("method") or "GET").upper()
    b = r.get("body") if isinstance(r.get("body"), dict) else {}
    kind = b.get("type") if b.get("type") in ("none", "json", "form", "raw") else "none"
    body: dict = {"type": kind}
    if kind in ("json", "raw"):
        text = b.get("text")
        body["text"] = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False, indent=2)
    elif kind == "form":
        body["form"] = _rows(b.get("form"))
    a = r.get("auth") if isinstance(r.get("auth"), dict) else {}
    atype = a.get("type") if a.get("type") in ("bearer", "basic") else "none"
    auth = {"type": atype, **{k: str(a.get(k) or "") for k in (("token",) if atype == "bearer" else
                                                            ("user", "password") if atype == "basic" else ())}}
    lines = lambda v: [str(x).strip() for x in v if str(x).strip()] if isinstance(v, list) else []  # noqa: E731
    return {"name": str(r.get("name") or "").strip()[:120], "folder": str(r.get("folder") or "").strip()[:60],
            "method": method if method in METHODS else "GET", "url": str(r.get("url") or "").strip(),
            "query": _rows(r.get("query")), "headers": _rows(r.get("headers")), "body": body, "auth": auth,
            "asserts": lines(r.get("asserts")), "extract": lines(r.get("extract"))}


# ---------------------------------------------------------------------------- nhập Postman / OpenAPI
def _pm_rows(v) -> list:
    return [[str(x.get("key") or ""), str(x.get("value") or ""), not x.get("disabled")]
            for x in v if isinstance(x, dict) and str(x.get("key") or "").strip()] if isinstance(v, list) else []


def _pm_auth(a) -> Optional[dict]:
    if not isinstance(a, dict):
        return None
    kv = {x.get("key"): x.get("value") for x in a.get(a.get("type") or "", []) if isinstance(x, dict)} \
        if isinstance(a.get(a.get("type") or ""), list) else {}
    if a.get("type") == "bearer":
        return {"type": "bearer", "token": str(kv.get("token") or "")}
    if a.get("type") == "basic":
        return {"type": "basic", "user": str(kv.get("username") or ""), "password": str(kv.get("password") or "")}
    if a.get("type") == "noauth":
        return {"type": "none"}
    return None


def _pm_tests(item: dict) -> str:
    """Script tab Tests của một request Postman (exec là chuỗi hoặc mảng dòng)."""
    out = []
    for e in item.get("event") or []:
        sc = e.get("script") if isinstance(e, dict) and e.get("listen") == "test" else None
        if isinstance(sc, dict):
            ex = sc.get("exec") or ""
            out.append("\n".join(map(str, ex)) if isinstance(ex, list) else str(ex))
    return "\n".join(out)


PM_STATUS = re.compile(r"(?:to\.have\.status|\.code\)?\.to\.(?:eql|equal))\(\s*(\d{3})\s*\)|responseCode\.code\s*===?\s*(\d{3})")


def from_postman(data: dict) -> dict:
    """Postman Collection v2.0/v2.1 -> collection. Thư mục lồng nhau thành "a/b"; auth kế thừa từ collection/thư
    mục; script test chỉ lấy assert mã status (`pm.response.to.have.status(200)`)."""
    out: list = []

    def walk(items, folder: str, auth) -> None:
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                continue
            if isinstance(it.get("item"), list):
                sub = f"{folder}/{it.get('name') or ''}".strip("/")
                walk(it["item"], sub, _pm_auth(it.get("auth")) or auth)
                continue
            rq = it.get("request")
            if isinstance(rq, str):
                rq = {"url": rq}
            if not isinstance(rq, dict):
                continue
            u = rq.get("url")
            url = (u.get("raw") or "") if isinstance(u, dict) else str(u or "")
            query = _pm_rows(u.get("query")) if isinstance(u, dict) else []
            if query and "?" in url:
                url = url.split("?", 1)[0]
            b, body = rq.get("body") if isinstance(rq.get("body"), dict) else {}, {"type": "none"}
            if b.get("mode") == "raw" and str(b.get("raw") or "").strip():
                lang = (((b.get("options") or {}).get("raw") or {}).get("language") or "")
                kind = "json" if lang == "json" or str(b["raw"]).lstrip()[:1] in "{[" else "raw"
                body = {"type": kind, "text": str(b["raw"])}
            elif b.get("mode") in ("urlencoded", "formdata"):
                body = {"type": "form", "form": _pm_rows(b.get(b["mode"]))}
            codes = [a or b2 for a, b2 in PM_STATUS.findall(_pm_tests(it))]
            out.append(clean_request({"name": it.get("name") or "", "folder": folder, "method": rq.get("method") or "GET",
                                      "url": url, "query": query, "headers": _pm_rows(rq.get("header")), "body": body,
                                      "auth": _pm_auth(rq.get("auth")) or auth or {"type": "none"},
                                      "asserts": [f"status == {codes[0]}"] if codes else []}))

    walk(data.get("item"), "", _pm_auth(data.get("auth")))
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    vs = {str(v.get("key")): str(v.get("value") or "") for v in data.get("variable") or []
          if isinstance(v, dict) and v.get("key")}
    return {"name": str(info.get("name") or "postman"), "vars": vs, "requests": out}


def _example(schema, root: dict, depth: int = 0):
    """Giá trị ví dụ dựng từ JSON schema (example/default/enum, theo kiểu), $ref nội bộ; giới hạn độ sâu."""
    if not isinstance(schema, dict) or depth > 6:
        return None
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/"):
        node = root
        for part in ref[2:].split("/"):
            node = node.get(part, {}) if isinstance(node, dict) else {}
        return _example(node, root, depth + 1)
    for k in ("example", "default"):
        if k in schema:
            return schema[k]
    if isinstance(schema.get("enum"), list) and schema["enum"]:
        return schema["enum"][0]
    for k in ("allOf", "oneOf", "anyOf"):
        if isinstance(schema.get(k), list) and schema[k]:
            parts = [_example(x, root, depth + 1) for x in schema[k]]
            if k == "allOf" and all(isinstance(x, dict) for x in parts):
                return {kk: vv for x in parts for kk, vv in x.items()}
            return parts[0]
    t = schema.get("type")
    if t == "object" or isinstance(schema.get("properties"), dict):
        return {k: _example(v, root, depth + 1) for k, v in (schema.get("properties") or {}).items()}
    if t == "array":
        item = _example(schema.get("items"), root, depth + 1)
        return [item] if item is not None else []
    if t == "string":
        return {"date-time": "2026-01-01T00:00:00Z", "date": "2026-01-01", "email": "a@b.vn",
                "uuid": str(uuid.UUID(int=0))}.get(schema.get("format"), "string")
    return {"integer": 0, "number": 0, "boolean": False}.get(t)


def from_openapi(data: dict) -> dict:
    """OpenAPI 3.x hoặc Swagger 2.0 (JSON) -> collection: thư mục theo tag, {id} -> {{id}}, tham số query/header,
    body ví dụ dựng từ schema, route có security -> Bearer {{token}}, assert mã 2xx đầu tiên."""
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    if data.get("swagger"):
        host = str(data.get("host") or "")
        base = (f"{(data.get('schemes') or ['http'])[0]}://{host}" if host else "") + str(data.get("basePath") or "")
    else:
        srv = (data.get("servers") or [{}])[0]
        base = str(srv.get("url") or "") if isinstance(srv, dict) else ""
    glob_sec = bool(data.get("security"))
    out = []
    for path, ops in (data.get("paths") or {}).items():
        if not isinstance(ops, dict):
            continue
        shared = ops.get("parameters") if isinstance(ops.get("parameters"), list) else []
        for m, op in ops.items():
            if m.upper() not in METHODS or not isinstance(op, dict):
                continue
            params = [_resolve(p, data) for p in shared + (op.get("parameters") or [])]
            q = [[p["name"], _text(_example(p.get("schema") or p, data)), bool(p.get("required"))]
                 for p in params if isinstance(p, dict) and p.get("in") == "query" and p.get("name")]
            h = [[p["name"], _text(_example(p.get("schema") or p, data)), True]
                 for p in params if isinstance(p, dict) and p.get("in") == "header" and p.get("name")]
            body: dict = {"type": "none"}
            rb = _resolve(op.get("requestBody"), data) if op.get("requestBody") else None
            schema = None
            if isinstance(rb, dict):
                content = rb.get("content") or {}
                js = next((v for k, v in content.items() if "json" in k), None)
                if isinstance(js, dict):
                    schema = js.get("example", None)
                    schema = schema if schema is not None else _example(js.get("schema"), data)
            else:
                bp = next((p for p in params if isinstance(p, dict) and p.get("in") == "body"), None)
                schema = _example(bp.get("schema"), data) if bp else None
            if schema is not None:
                body = {"type": "json", "text": json.dumps(schema, ensure_ascii=False, indent=2)}
            codes = sorted(c for c in (op.get("responses") or {}) if str(c).startswith("2") and str(c).isdigit())
            sec = op.get("security", None)
            secured = bool(sec) if sec is not None else glob_sec
            out.append(clean_request({
                "name": op.get("summary") or op.get("operationId") or f"{m.upper()} {path}",
                "folder": (op.get("tags") or [""])[0], "method": m, "url": re.sub(r"\{(\w+)\}", r"{{\1}}", path),
                "query": q, "headers": h, "body": body,
                "auth": {"type": "bearer", "token": "{{token}}"} if secured else {"type": "none"},
                "asserts": [f"status == {codes[0]}"] if codes else []}))
    return {"name": str(info.get("title") or "openapi"), "vars": {"base_url": base} if base else {}, "requests": out}


def _text(v) -> str:
    """Giá trị ví dụ -> chữ cho ô query/header (true/false/số kiểu JSON, None -> trống)."""
    return "" if v is None else v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def _resolve(node, root: dict):
    for _ in range(5):
        if isinstance(node, dict) and isinstance(node.get("$ref"), str) and node["$ref"].startswith("#/"):
            cur = root
            for part in node["$ref"][2:].split("/"):
                cur = cur.get(part, {}) if isinstance(cur, dict) else {}
            node = cur
        else:
            break
    return node


def import_text(text: str) -> dict:
    """Nhận dạng nội dung dán / file: lệnh curl -> {"request"}; JSON Postman / OpenAPI -> {"collection"}.
    Ném ValueError kèm lời nhắn cho người dùng."""
    t = text.strip()
    if t.startswith("curl"):
        return {"request": from_curl(t)}
    try:
        data = json.loads(t)
    except ValueError:
        raise ValueError(tr("Không nhận ra nội dung — dán lệnh curl, hoặc file JSON của Postman / OpenAPI "
                            "(OpenAPI dạng YAML: đổi sang JSON trước)")) from None
    if not isinstance(data, dict):
        raise ValueError(tr("Không nhận ra nội dung — dán lệnh curl, hoặc file JSON của Postman / OpenAPI "
                            "(OpenAPI dạng YAML: đổi sang JSON trước)"))
    if data.get("openapi") or data.get("swagger"):
        coll = from_openapi(data)
    elif isinstance(data.get("item"), list):
        coll = from_postman(data)
    else:
        raise ValueError(tr("JSON này không phải collection Postman hay đặc tả OpenAPI"))
    for i, r in enumerate(coll["requests"], 1):
        r["id"] = i
    return {"collection": coll}


def unique_name(root: Path, name: str) -> str:
    stem, have, n = slug(name), set(list_collections(root)), 2
    out = stem
    while out in have:
        out, n = f"{stem}-{n}", n + 1
    return out


# ---------------------------------------------------------------------------- curl
def to_curl(p: dict, secrets: Optional[dict] = None) -> str:
    """Lệnh curl tương đương request đã prepare (secret thay bằng {{tên}})."""
    s = secrets or {}
    parts = ["curl"]
    if p["method"] != "GET":
        parts += ["-X", p["method"]]
    parts.append(shlex.quote(mask(p["url"], s)))
    for k, v in p["headers"]:
        parts += ["-H", shlex.quote(mask(f"{k}: {v}", s))]
    if p["body"]:
        parts += ["--data-raw", shlex.quote(mask(p["body"].decode("utf-8", "replace"), s))]
    return " ".join(parts)


def from_curl(cmd: str) -> dict:
    """Lệnh curl (dán từ DevTools/tài liệu) -> request mẫu. Ném ValueError nếu không phải curl."""
    try:
        argv = shlex.split(re.sub(r"\\\r?\n", " ", cmd.strip()))
    except ValueError as e:
        raise ValueError(tr("Lệnh curl không hợp lệ: {e}", e=e)) from None
    if not argv or argv[0] != "curl":
        raise ValueError(tr("Không phải lệnh curl"))
    req = {"method": "", "url": "", "headers": [], "query": [], "body": {"type": "none", "text": ""},
           "auth": {"type": "none"}}
    data, is_json, i = [], False, 1
    takes = {"-X", "--request", "-H", "--header", "-d", "--data", "--data-raw", "--data-binary", "--data-ascii",
             "--data-urlencode", "--json", "-u", "--user", "--url", "-A", "--user-agent", "-b", "--cookie",
             "-e", "--referer", "-o", "--output", "-m", "--max-time", "--connect-timeout"}
    while i < len(argv):
        a = argv[i]
        v = argv[i + 1] if a in takes and i + 1 < len(argv) else None
        i += 2 if a in takes else 1
        if a in ("-X", "--request"):
            req["method"] = (v or "").upper()
        elif a in ("-H", "--header") and v and ":" in v:
            k, _, val = v.partition(":")
            req["headers"].append([k.strip(), val.strip(), True])
        elif a in ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii", "--data-urlencode") and v is not None:
            data.append(v)
        elif a == "--json" and v is not None:
            data.append(v)
            is_json = True
        elif a in ("-u", "--user") and v:
            user, _, pw = v.partition(":")
            req["auth"] = {"type": "basic", "user": user, "password": pw}
        elif a in ("-A", "--user-agent") and v:
            req["headers"].append(["User-Agent", v, True])
        elif a in ("-b", "--cookie") and v:
            req["headers"].append(["Cookie", v, True])
        elif a in ("-e", "--referer") and v:
            req["headers"].append(["Referer", v, True])
        elif a == "-I" or a == "--head":
            req["method"] = "HEAD"
        elif a in ("-k", "--insecure"):
            req["insecure"] = True
        elif a == "--url" and v:
            req["url"] = v
        elif not a.startswith("-") and not req["url"]:
            req["url"] = a
    if not req["url"]:
        raise ValueError(tr("Lệnh curl thiếu URL"))
    ctype = next((h[1] for h in req["headers"] if h[0].lower() == "content-type"), "")
    if data:
        text = "&".join(data)
        if is_json or "json" in ctype.lower() or text.lstrip()[:1] in ("{", "["):
            req["body"] = {"type": "json", "text": text}
        elif "=" in text and not ctype:
            req["body"] = {"type": "form", "form": [[k, v, True] for k, v in urllib.parse.parse_qsl(text, True)]}
        else:
            req["body"] = {"type": "raw", "text": text}
    req["method"] = req["method"] or ("POST" if data else "GET")
    u = urllib.parse.urlsplit(req["url"])
    if u.query:
        req["query"] = [[k, v, True] for k, v in urllib.parse.parse_qsl(u.query, True)]
        req["url"] = urllib.parse.urlunsplit(u._replace(query=""))
    req["name"] = f"{req['method']} {u.path or '/'}"
    return req
