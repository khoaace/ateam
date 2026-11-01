"""Tab 🛰 API của TUI (tui_api.py): mở bằng /api, sửa request → tự lưu vào .ateam/api/, Enter ở ô URL gửi tới server
cục bộ (assert, extract, che secret), ＋ Request, /api run, 🛠 giao trưởng nhóm sửa; nhập Postman/OpenAPI (lõi)."""
from __future__ import annotations

import asyncio
import importlib
import json

from conftest import ateam, git_init, wait_for
from test_apiclient import server  # noqa: F401 — fixture server HTTP cục bộ

from ateam import apiclient as A
from ateam.tui_api import rows_to_text, text_to_rows


def test_rows_text_roundtrip():
    rows = [["page", "1", True], ["debug", "x=y", False]]
    assert rows_to_text(rows, "=") == "page=1\n# debug=x=y"
    assert text_to_rows("page=1\n# debug=x=y\n\n  =bỏ\n", "=") == rows
    assert text_to_rows("Authorization: Bearer {{token}}\n#X-A: 1", ":") == [
        ["Authorization", "Bearer {{token}}", True], ["X-A", "1", False]]


def test_tui_api_tab(env, project, monkeypatch, server):  # noqa: F811
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    git_init(project)
    import ateam.config
    importlib.reload(ateam.config)
    from textual.widgets import Input, TabbedContent, TextArea

    from ateam.config import ensure_global_config, load_config
    from ateam.db import DB
    from ateam.tui import TeamApp
    from ateam.tui_api import ApiPanel

    A.save_collection(project, {"name": "shop", "vars": {"base_url": server}, "requests": [
        {"id": 1, "name": "login", "method": "POST", "url": "/login", "asserts": ["status == 200"],
         "extract": ["token = json $.data.token"]},
        {"id": 2, "name": "me", "url": "/me", "headers": [["Authorization", "Bearer {{token}}", True]],
         "asserts": ["status == 200", "json $.name == \"Khoa\""]}]})

    async def main():
        ensure_global_config()
        app = TeamApp(project, load_config(project), DB(project / ".ateam/team.db"))
        async with app.run_test(size=(170, 50)) as pilot:
            app.run_command("/api")
            panel = app.query_one("#api-tab", ApiPanel)
            assert await wait_for(pilot, lambda: app.query_one("#tabs", TabbedContent).active == "tab-api"
                                  and panel.current() is not None)
            assert panel.coll_name == "shop" and panel.cur_id == 1
            url = panel.query_one("#api-url", Input)
            url.focus()
            await pilot.press("enter")                                  # Enter ở ô URL = Gửi
            assert await wait_for(pilot, lambda: 1 in panel.results)
            assert panel.results[1]["ok"] and A.load_secrets(project)["token"] == "tok-secret-123"
            panel.open_request(2)
            await pilot.pause(0.2)
            assert "Bearer {{token}}" in panel.query_one("#api-headers", TextArea).text
            panel.send()
            assert await wait_for(pilot, lambda: 2 in panel.results)
            assert panel.results[2]["ok"], panel.results[2]["asserts"]
            assert "tok-secret-123" not in json.dumps(panel.results[2]["request"])
            # sửa assert cho sai → tự lưu, gửi lại → nút 🛠 hiện, giao trưởng nhóm sửa
            panel.reload()  # vòng làm mới chạy đúng lúc đang gõ: thay đổi vẫn phải được tự lưu
            panel.query_one("#api-asserts", TextArea).load_text("status == 201")
            assert await wait_for(pilot, lambda: A.load_collection(project, "shop")["requests"][1]["asserts"]
                                  == ["status == 201"])
            panel.send()
            assert await wait_for(pilot, lambda: 2 in panel.results and not panel.results[2]["ok"])
            assert panel.query_one("#api-fix").display
            n = len(app.db.tasks())
            panel.fix()
            t = app.db.tasks()[-1]
            assert len(app.db.tasks()) == n + 1 and t.agent == app.cfg.lead and "status == 201" in t.prompt
            assert "tok-secret-123" not in t.prompt
            # ＋ Request: thêm vào collection đang mở, ô URL có focus
            await pilot.click("#api-new")
            assert await wait_for(pilot, lambda: len(A.load_collection(project, "shop")["requests"]) == 3)
            assert panel.cur_id == 3 and url.has_focus
            seen: list = []
            monkeypatch.setattr(app, "write_sys", seen.append)
            app.run_command("/api run shop")
            assert await wait_for(pilot, lambda: any("/3 request đạt" in x for x in seen))
            assert "✗" in seen[-1] and "tok-secret-123" not in seen[-1]
            app.save_screenshot(str(project / "api-tab.svg"))
            await pilot.press("ctrl+q")

    asyncio.run(main())


POSTMAN = {
    "info": {"name": "Shop API", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
    "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{token}}"}]},
    "variable": [{"key": "base_url", "value": "http://localhost:3000"}],
    "item": [
        {"name": "Auth", "auth": {"type": "noauth"}, "item": [
            {"name": "Login", "request": {"method": "POST", "url": "{{base_url}}/login", "body": {
                "mode": "raw", "raw": "{\"email\": \"a@b.vn\"}", "options": {"raw": {"language": "json"}}}},
             "event": [{"listen": "test", "script": {"exec": ["pm.test('ok', () => {", "  pm.response.to.have.status(200);",
                                                             "});"]}}]}]},
        {"name": "List", "request": {"method": "GET", "header": [{"key": "X-A", "value": "1", "disabled": True}],
                                     "url": {"raw": "{{base_url}}/items?page=2", "query": [{"key": "page", "value": "2"}]}}},
        {"name": "Form", "request": {"method": "POST", "url": "{{base_url}}/f",
                                     "body": {"mode": "urlencoded", "urlencoded": [{"key": "a", "value": "1"}]}}},
    ]}

OPENAPI = {
    "openapi": "3.0.0", "info": {"title": "Pet Store"}, "servers": [{"url": "http://localhost:8000/api"}],
    "security": [{"bearer": []}],
    "components": {"schemas": {"Pet": {"type": "object", "required": ["name"], "properties": {
        "name": {"type": "string", "example": "Mèo"}, "age": {"type": "integer"}, "born": {"type": "string", "format": "date"},
        "tags": {"type": "array", "items": {"type": "string"}}}}}},
    "paths": {
        "/pets/{petId}": {"parameters": [{"name": "petId", "in": "path", "required": True}],
                          "get": {"summary": "Xem thú", "tags": ["pets"], "responses": {"200": {}, "404": {}}}},
        "/pets": {"post": {"operationId": "createPet", "tags": ["pets"],
                           "parameters": [{"name": "dry", "in": "query", "schema": {"type": "boolean"}}],
                           "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Pet"}}}},
                           "responses": {"201": {}}},
                  "get": {"security": [], "responses": {"200": {}}}},
    }}


def test_import_postman_and_openapi(env, project):
    c = A.import_text(json.dumps(POSTMAN))["collection"]
    assert c["name"] == "Shop API" and c["vars"] == {"base_url": "http://localhost:3000"}
    login, lst, form = c["requests"]
    assert (login["folder"], login["method"], login["url"]) == ("Auth", "POST", "{{base_url}}/login")
    assert login["body"] == {"type": "json", "text": "{\"email\": \"a@b.vn\"}"} and login["asserts"] == ["status == 200"]
    assert login["auth"] == {"type": "none"}                                   # thư mục noauth
    assert lst["auth"] == {"type": "bearer", "token": "{{token}}"}             # kế thừa từ collection
    assert lst["url"] == "{{base_url}}/items" and lst["query"] == [["page", "2", True]]
    assert lst["headers"] == [["X-A", "1", False]] and [r["id"] for r in c["requests"]] == [1, 2, 3]
    assert form["body"] == {"type": "form", "form": [["a", "1", True]]}

    o = A.import_text(json.dumps(OPENAPI))["collection"]
    assert o["name"] == "Pet Store" and o["vars"] == {"base_url": "http://localhost:8000/api"}
    by = {(r["method"], r["url"]): r for r in o["requests"]}
    get = by[("GET", "/pets/{{petId}}")]
    assert get["name"] == "Xem thú" and get["folder"] == "pets" and get["asserts"] == ["status == 200"]
    assert get["auth"]["type"] == "bearer"                                     # security chung
    post = by[("POST", "/pets")]
    assert post["name"] == "createPet" and post["asserts"] == ["status == 201"]
    assert json.loads(post["body"]["text"]) == {"name": "Mèo", "age": 0, "born": "2026-01-01", "tags": ["string"]}
    assert post["query"] == [["dry", "false", False]]
    assert by[("GET", "/pets")]["auth"] == {"type": "none"}                    # security: [] = bỏ auth
    sw = A.import_text(json.dumps({"swagger": "2.0", "host": "api.test", "basePath": "/v1", "schemes": ["https"],
                                   "paths": {"/x": {"post": {"parameters": [{"in": "body", "name": "b", "schema": {
                                       "type": "object", "properties": {"q": {"type": "string"}}}}],
                                       "responses": {"204": {}}}}}}))["collection"]
    assert sw["vars"] == {"base_url": "https://api.test/v1"} and json.loads(sw["requests"][0]["body"]["text"]) == {"q": "string"}
    for bad in ("{}", "[1]", "không phải json"):
        try:
            A.import_text(bad)
            raise AssertionError(bad)
        except ValueError:
            pass
    # CLI: ateam api import — trùng tên thì thêm hậu tố
    f = project / "pm.json"
    f.write_text(json.dumps(POSTMAN), encoding="utf-8")
    for want in ("Shop-API", "Shop-API-2"):
        r = ateam(env, project, "api", "import", str(f))
        assert r.returncode == 0 and want in r.stdout, r.stdout
    assert A.list_collections(project) == ["Shop-API", "Shop-API-2"]
    assert ateam(env, project, "api", "import", str(project / "khong-co.json")).returncode == 2
