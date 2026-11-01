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
        imp = (await h(action="import_curl", text="curl -X DELETE http://h/items/1"))[2]["http"]["request"]
        assert imp["method"] == "DELETE"
        assert (await h(action="import_curl", text="ls"))[1] == "warn"
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
