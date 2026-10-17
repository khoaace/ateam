"""🔍 Tìm & thay trong toàn dự án (ateam/search.py, tab Code của web)."""

from __future__ import annotations

import asyncio
import os
import stat

import pytest

from ateam import search


def _proj(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_text("const parseFilm = 1;\nparseFilmQuery(parseFilm)\n", encoding="utf-8")
    (tmp_path / "src" / "a.test.ts").write_text("parseFilm()\n", encoding="utf-8")
    (tmp_path / "docs.md").write_bytes("﻿ParseFilm trong tài liệu\r\ndòng 2\r\n".encode("utf-8"))
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00parseFilm")
    return ["src/", "src/a.ts", "src/a.test.ts", "docs.md", "logo.png"]


def test_search_options_and_filters(tmp_path):
    files = _proj(tmp_path)
    r = search.search(tmp_path, files, "parsefilm")
    assert r["total"] == 5 and {f["path"] for f in r["files"]} == {"src/a.ts", "src/a.test.ts", "docs.md"}  # bỏ ảnh
    first = r["files"][0]["matches"][0]
    assert (first["line"], first["col"], first["len"]) == (1, 6, 9)
    assert first["text"][first["s"]:first["e"]] == "parseFilm"
    assert search.search(tmp_path, files, "parsefilm", case=True)["total"] == 0
    assert search.search(tmp_path, files, "parseFilm", case=True, word=True)["total"] == 3  # không tính parseFilmQuery
    assert search.search(tmp_path, files, r"parse\w+Query", regex=True)["total"] == 1
    assert [f["path"] for f in search.search(tmp_path, files, "parseFilm", include="src", exclude="*.test.ts")["files"]] \
        == ["src/a.ts"]
    assert [f["path"] for f in search.search(tmp_path, files, "film", include="*.md")["files"]] == ["docs.md"]
    md = search.search(tmp_path, files, "film", include="*.md")["files"][0]["matches"][0]
    assert md["text"] == "ParseFilm trong tài liệu"  # bỏ BOM ở đầu, không dính \r
    assert search.search(tmp_path, files, "parseFilm", limit=2)["truncated"]
    with pytest.raises(ValueError):
        search.search(tmp_path, files, "(", regex=True)
    rep = search.search(tmp_path, files, r"parse(\w+)Query", regex=True, replace="get$1")["files"][0]["matches"][0]
    assert rep["repl"] == "getFilm"


def test_replace_keeps_crlf_bom_and_mode(tmp_path):
    files = _proj(tmp_path)
    os.chmod(tmp_path / "src" / "a.ts", 0o755)
    r = search.replace_in(tmp_path, ["src/a.ts", "docs.md", "logo.png"], "parseFilm", "loadFilm", word=True)
    assert r == {"files": {"src/a.ts": 2, "docs.md": 1}, "total": 3}
    assert (tmp_path / "src" / "a.ts").read_text() == "const loadFilm = 1;\nparseFilmQuery(loadFilm)\n"
    assert (tmp_path / "docs.md").read_bytes() == "﻿loadFilm trong tài liệu\r\ndòng 2\r\n".encode("utf-8")
    assert stat.S_IMODE((tmp_path / "src" / "a.ts").stat().st_mode) == 0o755
    assert b"parseFilm" in (tmp_path / "logo.png").read_bytes()  # file nhị phân không đụng tới
    search.replace_in(tmp_path, ["src/a.ts"], r"(\w+)Film(\w*)", "$2_$1$$\\n", regex=True)
    assert (tmp_path / "src" / "a.ts").read_text() == "const _load$\n = 1;\nQuery_parse$\n(_load$\n)\n"


def test_web_code_search_replace(env, project, monkeypatch):
    pytest.importorskip("aiohttp")
    from test_web import _web_app
    wa = _web_app(env, project, monkeypatch)
    (project / "a.py").write_text("x = 'cũ'\nprint('cũ')\n", encoding="utf-8")
    (project / "b.py").write_text("cũ\n", encoding="utf-8")

    async def main():
        r = await wa.handle({"op": "code_search", "query": "cũ", "replace": "mới"})
        res = r[2]["search"]
        assert res["total"] == 3 and all(m["repl"] == "mới" for f in res["files"] for m in f["matches"])
        assert "error" in (await wa.handle({"op": "code_search", "query": "(", "regex": True}))[2]["search"]
        r = await wa.handle({"op": "code_replace", "query": "cũ", "replacement": "mới",
                             "files": ["a.py", "../ngoai.py", ".git/config"]})  # đường ra ngoài / .git bị bỏ
        assert r[1] == "ok" and r[2]["replaced"] == {"files": {"a.py": 2}, "total": 2}
        assert (project / "a.py").read_text(encoding="utf-8") == "x = 'mới'\nprint('mới')\n"
        assert (project / "b.py").read_text(encoding="utf-8") == "cũ\n"
        wa.remote.readonly = True
        assert (await wa.handle({"op": "code_search", "query": "cũ"}))[2]["search"]["total"] == 1  # chỉ xem: tìm được
        assert (await wa.handle({"op": "code_replace", "query": "cũ", "replacement": "x", "files": ["b.py"]}))[1] == "warn"

    asyncio.run(main())
