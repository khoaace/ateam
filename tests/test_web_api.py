"""Tab 🛰 API trên web (op http — ateam/web_api.py): tạo collection (gợi ý base_url từ dev server), lưu, gửi request đang
soạn, chạy cả collection, nhập curl, môi trường + secret (chỉ trả tên), --readonly chỉ cho đọc; trang có mục API."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from test_apiclient import server  # noqa: F401 — fixture server HTTP cục bộ
from test_web import _web_app

ROOT = Path(__file__).resolve().parent.parent


def test_web_http_ops(env, project, monkeypatch, server):  # noqa: F811
    pytest.importorskip("aiohttp")
    from ateam import apiclient as A
    wa = _web_app(env, project, monkeypatch)
    port = int(server.rsplit(":", 1)[1])
    monkeypatch.setattr(wa.api, "ports", lambda: [port])

    async def main():
        h = lambda **d: wa.handle({"op": "http", **d})  # noqa: E731
        st = (await h(action="state"))[2]["http"]
        assert st["collections"] == [] and st["ports"] == [port]
        assert (await h(action="new", name=" "))[1] == "warn"
        r = (await h(action="new", name="shop"))[2]["http"]
        assert r["created"] == "shop" and r["collections"] == [{"name": "shop", "count": 0}]
        assert (await h(action="new", name="shop"))[1] == "warn"
        c = (await h(action="get", collection="shop"))[2]["http"]["collection"]
        assert c["vars"] == {"base_url": f"http://localhost:{port}"}
        c["vars"]["base_url"] = server  # 127.0.0.1: không phụ thuộc localhost phân giải ra IPv6
        login = {"name": "login", "method": "POST", "url": "/login", "asserts": ["status == 200", "json $.data.token exists"],
                 "extract": ["token = json $.data.token"]}
        c["requests"] = [login, {"name": "me", "url": "/me", "auth": {"type": "bearer", "token": "{{token}}"},
                                 "asserts": ["status == 200"]}]
        saved = (await h(action="save", collection="shop", data=c))[2]["http"]
        assert [q["id"] for q in saved["collection"]["requests"]] == [1, 2]
        assert A.load_collection(project, "shop")["requests"][0]["name"] == "login"
        # gửi request đang soạn (chưa lưu): secret lấy được không lộ ở body / assert / curl
        res = (await h(action="send", collection="shop", request=login))[2]["http"]
        assert res["result"]["ok"] and res["secrets"] == ["token"]
        assert "tok-secret-123" not in str(res)
        assert "{{token}}" in res["result"]["response"]["body"] and res["result"]["curl"].startswith("curl -X POST")
        cu = (await h(action="curl", collection="shop", request=c["requests"][1]))[2]["http"]["curl"]
        assert "Bearer {{token}}" in cu and "tok-secret-123" not in cu
        text, lvl, extra = await h(action="run", collection="shop")
        assert lvl == "ok" and "2/2" in text and [x["ok"] for x in extra["http"]["run"]] == [True, True]
        assert len((await h(action="history"))[2]["http"]["history"]) == 1  # chỉ lần gửi tay, không tính lần chạy
        imp = (await h(action="import", text="curl -X DELETE http://h/items/1"))[2]["http"]["request"]
        assert imp["method"] == "DELETE"
        assert (await h(action="import", text="ls"))[1] == "warn"
        # môi trường (commit được) + secret (ngoài repo, chỉ trả tên)
        assert (await h(action="env_save", env="local", values={"base_url": server, " ": "x"}))[1] == "ok"
        assert (await h(action="env_get", env="local"))[2]["http"]["values"] == {"base_url": server}
        st = (await h(action="secret_set", key="pw", value="hunter2"))[2]["http"]
        assert st["secrets"] == ["pw", "token"] and "hunter2" not in str(st) and st["envs"] == ["local"]
        assert (await h(action="secret_delete", key="pw"))[2]["http"]["secrets"] == ["token"]
        assert (await h(action="env_delete", env="local"))[2]["http"]["envs"] == []
        assert (await h(action="delete", collection="shop"))[2]["http"]["collections"] == []
        # chỉ xem: đọc được, không gửi / lưu được
        wa.remote.readonly = True
        assert (await h(action="state"))[2]["http"]["collections"] == []
        assert (await h(action="send", request=login))[1] == "warn"
        assert (await h(action="save", collection="x", data={}))[1] == "warn"
        assert A.list_collections(project) == []

    asyncio.run(main())
    assert wa.slow_op({"op": "http", "action": "send"}) and not wa.slow_op({"op": "http", "action": "save"})
    assert {"api", "ap_send", "ap_asserts"} <= set(wa.hello()["T"])


def test_web_page_has_api_view():
    html = (ROOT / "ateam/webui/index.html").read_text(encoding="utf-8")
    assert 'data-view="api"' in html and 'id="view-api"' in html and "/static/api.js" in html
    js = (ROOT / "ateam/webui/app.js").read_text(encoding="utf-8")
    assert '"api"]' in js and "ApiView.show()" in js


def test_extract_api_parser():
    from ateam import prompts as P
    assert P.extract_api("không có gì") is None
    assert P.extract_api("<<<API>>>\n{hỏng\n<<<END>>>") is None
    assert P.extract_api('<<<API>>>\n{"requests": 1}\n<<<END>>>') is None
    d = P.extract_api('mẫu <<<API>>> {"requests": []} <<<END>>>\nthật:\n<<<API>>>\n```json\n'
                      '[{"url": "/a"}]\n```\n<<<END>>>')
    assert d == {"requests": [{"url": "/a"}]}  # khối cuối cùng; mảng trần = danh sách request


def test_web_http_scan_fix_verify(env, project, monkeypatch):
    """✨ Quét code (agent giả lập): chuẩn hoá request, bỏ request đã có; 🛠 Giao agent sửa: task có prompt đủ
    request/response/assert sai/log dev server, secret bị che; ✅ đặt collection làm lệnh kiểm tra."""
    pytest.importorskip("aiohttp")
    from ateam import apiclient as A
    from ateam import prompts as P
    wa = _web_app(env, project, monkeypatch)
    A.save_collection(project, {"name": "shop", "requests": [{"id": 1, "name": "health", "method": "GET", "url": "/health"}]})
    A.save_secrets(project, {"token": "tok-secret-123"})
    monkeypatch.setattr(wa.api, "server_log", lambda n=80: "GET /orders 500\nKeyError: user tok-secret-123")

    async def main():
        h = lambda **d: wa.handle({"op": "http", **d})  # noqa: E731
        sc = (await h(action="scan", collection="shop", focus="đơn hàng"))[2]["http"]["scan"]
        assert sc["base_url"] == "http://localhost:8000"
        by = {r["url"]: r for r in sc["requests"]}
        assert sorted(by) == ["/login", "/products/{{id}}", "/x"]      # bỏ /health (đã có) và dòng thiếu url
        assert by["/login"]["method"] == "POST" and by["/x"]["method"] == "GET"
        assert by["/login"]["body"] == {"type": "json", "text": '{\n  "email": "a@b.vn"\n}'}
        assert by["/login"]["extract"] == ["token = json $.token"]
        assert by["/products/{{id}}"]["query"] == [["page", "1", True]]
        assert by["/products/{{id}}"]["auth"] == {"type": "bearer", "token": "{{token}}"}
        req = {"name": "orders", "method": "GET", "url": "http://127.0.0.1:9/orders",
               "headers": [["Authorization", "Bearer {{token}}", True]], "asserts": ["status == 200"]}
        result = {"response": {"status": 500, "reason": "Internal Server Error", "ms": 3, "headers": [["X-A", "1"]],
                               "body": '{"error": "boom"}'},
                  "asserts": [{"line": "status == 200", "ok": False, "msg": "status == 200 (thực tế: 500)"}]}
        text, lvl, extra = await h(action="fix", collection="shop", request=req, result=result, agent="codex",
                                   note="phải trả danh sách rỗng")
        tid = extra["open"]["task_link"]
        t = wa.db.task(tid)
        assert lvl == "ok" and t.agent == "codex" and t.title.startswith("Sửa API: GET http://127.0.0.1:9/orders")
        assert "tok-secret-123" not in t.prompt and "Bearer {{token}}" in t.prompt
        for part in ("FIX AN HTTP ENDPOINT", "HTTP 500 Internal Server Error", '{"error": "boom"}',
                     "status == 200 (thực tế: 500)", "KeyError: user {{token}}", "phải trả danh sách rỗng",
                     "api run shop --only orders"):
            assert part in t.prompt, part
        t2 = (await h(action="fix", request=req, result={"response": {"error": "Connection refused"}}, agent="ghost"))
        assert wa.db.task(t2[2]["open"]["task_link"]).agent == wa.cfg.lead  # agent lạ: trưởng nhóm
        assert "(no response) Connection refused" in wa.db.task(t2[2]["open"]["task_link"]).prompt
        assert (await h(action="verify", collection="khong-co"))[1] == "warn"
        assert (await h(action="verify", collection="shop", env="local"))[1] == "ok"
        assert wa.cfg.verify.command.endswith("api run shop --env local")
        wa.remote.readonly = True
        for act in ("scan", "fix", "verify"):
            assert "readonly" in (await h(action=act, collection="shop"))[0]

    asyncio.run(main())
    assert wa.slow_op({"op": "http", "action": "scan"})
    assert "SCAN HTTP API" in P.api_scan_prompt(cwd="/x", existing=["GET /a"], focus="", lang="vi")
