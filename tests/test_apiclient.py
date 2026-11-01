"""Tab 🛰 API — phần lõi (ateam/apiclient.py): biến, gửi HTTP tới server cục bộ, assert/extract, curl, che secret,
`ateam api run` (dùng làm lệnh kiểm tra) và .ateam/.gitignore chừa api/ để commit collection."""
from __future__ import annotations

import asyncio
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from conftest import ateam, git_init
from ateam import apiclient as A
from ateam import config


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _reply(self, code: int, obj, headers=()):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _any(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode() if n else ""
        if self.path == "/login":
            return self._reply(200, {"data": {"token": "tok-secret-123"}}, [("X-Session", "s-42")])
        if self.path == "/me":
            if self.headers.get("Authorization") != "Bearer tok-secret-123":
                return self._reply(401, {"error": "unauthorized"})
            return self._reply(200, {"name": "Khoa", "items": [1, 2, 3]})
        if self.path == "/old":
            self.send_response(302)
            self.send_header("Location", "/echo")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        return self._reply(200, {"method": self.command, "path": self.path, "body": body,
                                 "ctype": self.headers.get("Content-Type"), "auth": self.headers.get("Authorization")})

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _any


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GLOBAL_DIR", tmp_path / "cfg")
    p = tmp_path / "proj"
    (p / ".ateam").mkdir(parents=True)
    return p


def run(coro):
    return asyncio.run(coro)


def test_render_and_prepare():
    vs = {"base_url": "http://x.test/api/", "id": "7", "tok": "abc"}
    p = A.prepare({"method": "post", "url": "/users/{{id}}", "query": [["q", "{{id}}", True], ["off", "1", False]],
                   "headers": [["X-A", "{{missing}}", True]], "auth": {"type": "bearer", "token": "{{tok}}"},
                   "body": {"type": "json", "text": '{"id": {{id}}}'}}, vs)
    assert p["method"] == "POST" and p["url"] == "http://x.test/api/users/7?q=7"
    assert ("X-A", "{{missing}}") in p["headers"]               # biến chưa có: giữ nguyên để người dùng thấy
    assert ("Authorization", "Bearer abc") in p["headers"] and ("Content-Type", "application/json") in p["headers"]
    assert p["body"] == b'{"id": 7}'
    assert len(A.render("{{$uuid}}", {})) == 36 and A.render("{{$timestamp}}", {}).isdigit()
    f = A.prepare({"url": "http://x", "body": {"type": "form", "form": [["a", "1 2", True]]},
                   "auth": {"type": "basic", "user": "u", "password": "p"}}, {})
    assert f["body"] == b"a=1+2" and ("Authorization", "Basic dTpw") in f["headers"]


def test_variable_precedence(root):
    A.save_env(root, "dev", {"base_url": "http://env", "a": "env"})
    A.save_secrets(root, {"a": "secret"})
    vs = A.variables(root, {"vars": {"base_url": "http://coll", "a": "coll", "b": "coll"}}, "dev")
    assert vs == {"base_url": "http://env", "a": "secret", "b": "coll"}
    assert not str(A.secrets_path(root)).startswith(str(root))  # secret nằm ngoài repo


def test_send_assert_extract_chain(root, server):
    coll = {"name": "smoke", "vars": {"base_url": server}, "requests": [
        {"name": "login", "method": "POST", "url": "/login", "body": {"type": "json", "text": '{"u": 1}'},
         "asserts": ["status == 200", "json $.data.token exists", "header content-type contains json", "time < 5000"],
         "extract": ["token = json $.data.token", "sid = header X-Session"]},
        {"name": "me", "url": "/me", "auth": {"type": "bearer", "token": "{{token}}"},
         "asserts": ["status == 200", 'json $.name == "Khoa"', "json $.items.length == 3", "json $.items[1] == 2",
                     "json $.nope !exists", "body contains Khoa"]},
    ]}
    res = run(A.run_collection(root, coll))
    assert [r["ok"] for r in res] == [True, True], [a for r in res for a in r["asserts"] if not a["ok"]]
    assert A.load_secrets(root)["token"] == "tok-secret-123" and A.load_secrets(root)["sid"] == "s-42"
    # secret không lộ ở request hiển thị (header Authorization)
    assert ["Authorization", "Bearer {{token}}"] in res[1]["request"]["headers"]


def test_failures_are_reported(root, server):
    r = run(A.run_request(root, None, {"url": server + "/me", "asserts": ["status == 200", "json $.name exists",
                                                                         "time <"]}))
    assert r["response"]["status"] == 401 and not r["ok"]
    assert [a["ok"] for a in r["asserts"]] == [False, False, False]
    assert "401" in r["asserts"][0]["msg"]
    down = run(A.run_request(root, None, {"url": "http://127.0.0.1:9/x", "asserts": ["status == 200"]}))
    assert down["response"]["error"] and not down["ok"] and not down["asserts"][0]["ok"]
    bad = run(A.run_request(root, None, {"url": "ftp://x"}))
    assert "http" in bad["response"]["error"]
    assert len(A.load_history(root)) == 3


def test_redirects(root, server):
    follow = run(A.run_request(root, None, {"url": server + "/old"}))
    assert follow["response"]["status"] == 200 and '"/echo"' in follow["response"]["body"]
    stay = run(A.run_request(root, None, {"url": server + "/old", "follow": False}))
    assert stay["response"]["status"] == 302


def test_curl_roundtrip():
    r = A.from_curl("curl 'https://api.test/v1/items?page=2' \\\n  -H 'Authorization: Bearer xyz' "
                    "-H 'Content-Type: application/json' --data-raw '{\"a\":1}'")
    assert r["method"] == "POST" and r["url"] == "https://api.test/v1/items"
    assert r["query"] == [["page", "2", True]] and r["body"] == {"type": "json", "text": '{"a":1}'}
    assert ["Authorization", "Bearer xyz", True] in r["headers"]
    f = A.from_curl("curl -u bob:pw -d a=1 -d b=2 http://h/form")
    assert f["auth"] == {"type": "basic", "user": "bob", "password": "pw"}
    assert f["body"]["type"] == "form" and f["body"]["form"] == [["a", "1", True], ["b", "2", True]]
    assert A.from_curl("curl -I http://h")["method"] == "HEAD"
    for bad in ("wget http://h", "curl -X GET", "curl 'unclosed"):
        with pytest.raises(ValueError):
            A.from_curl(bad)
    p = A.prepare({"method": "POST", "url": "http://h/x", "headers": [["Authorization", "Bearer sekret-1", True]],
                   "body": {"type": "raw", "text": "hi"}}, {})
    cmd = A.to_curl(p, {"tok": "sekret-1"})
    assert "sekret-1" not in cmd and "{{tok}}" in cmd and cmd.startswith("curl -X POST http://h/x -H")


def test_collection_storage(root):
    stem = A.save_collection(root, {"name": "My API!", "requests": [{"name": "a"}, {"name": "b"}]})
    assert stem == "My-API" and A.list_collections(root) == ["My-API"]
    c = A.load_collection(root, "My-API")
    assert [r["id"] for r in c["requests"]] == [1, 2] and c["vars"] == {}
    assert A.load_collection(root, "khong-co") is None


def test_gitignore_keeps_api_committable(tmp_path):
    git_init(tmp_path)
    state = tmp_path / ".ateam"
    state.mkdir()
    (state / ".gitignore").write_text("*\n")      # dự án cũ: nâng cấp
    A.ensure_gitignore(state)
    assert (state / ".gitignore").read_text() == A.GITIGNORE
    (state / "api" / "env").mkdir(parents=True)
    for f in ("api/smoke.json", "api/env/dev.json", "api-history.json", "team.db"):
        (state / f).write_text("{}")
    out = subprocess.run(["git", "status", "--porcelain", "-uall"], cwd=tmp_path, capture_output=True, text=True).stdout
    assert ".ateam/api/smoke.json" in out and ".ateam/api/env/dev.json" in out
    assert "api-history" not in out and "team.db" not in out
    (state / ".gitignore").write_text("*\n!mine\n")  # người dùng tự sửa: giữ nguyên
    A.ensure_gitignore(state)
    assert (state / ".gitignore").read_text() == "*\n!mine\n"


def test_cli_api_run(env, project, server):
    (project / ".ateam" / "api").mkdir(parents=True)
    A.save_env(project, "local", {"base_url": server})
    A.save_collection(project, {"name": "smoke", "requests": [
        {"name": "login", "method": "POST", "url": "/login", "asserts": ["status == 200"],
         "extract": ["token = json $.data.token"]},
        {"name": "me", "url": "/me", "headers": [["Authorization", "Bearer {{token}}", True]],
         "asserts": ["status == 200"]}]})
    r = ateam(env, project, "api", "run", "--env", "local")      # chỉ có một collection: không cần tên
    assert r.returncode == 0, r.stdout + r.stderr
    assert "✓ POST" in r.stdout and "2/2" in r.stdout and "tok-secret-123" not in r.stdout
    A.save_collection(project, {"name": "bad", "requests": [{"url": server + "/me", "asserts": ["status == 200"]}]})
    r = ateam(env, project, "api", "run", "bad", check=False)
    assert r.returncode == 1 and "✗" in r.stdout and "0/1" in r.stdout
    r = ateam(env, project, "api", "run", "smoke", "--env", "local", "--only", "login")
    assert "1/1" in r.stdout
    r = ateam(env, project, "api", "run")                         # hai collection: phải nêu tên
    assert r.returncode == 2 and "bad" in r.stdout and "smoke" in r.stdout
    r = ateam(env, project, "api", "list")
    assert "smoke  (2 request)" in r.stdout and "local" in r.stdout
