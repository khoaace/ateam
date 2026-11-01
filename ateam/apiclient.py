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
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Callable, Optional

from . import todos
from .i18n import tr

MAX_BODY = 2 * 1024 ** 2   # byte body response giữ lại
HISTORY_MAX = 50
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
