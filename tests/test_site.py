"""Trang docs (scripts/build_site.py): dựng cả bản tiếng Việt lẫn tiếng Anh, điền hết placeholder, changelog lấy từ
CHANGELOG.md, mọi ảnh/asset được tham chiếu đều có thật."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _build_site():
    spec = importlib.util.spec_from_file_location("build_site", ROOT / "scripts" / "build_site.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_releases_from_changelog():
    bs = _build_site()
    text = ("# Changelog\n\n## Chưa phát hành\n\n- **Chưa ra** abc\n\n"
            "## 1.2.0 — 21/10/2026\n\n- **Bảng việc `mới`** (web): x\n- **Khác**\n\n"
            "## 1.1.0 — 20/10/2026\n\nTUI và web đồng bộ hơn:\n\n- **a**\n")
    assert bs.releases(text) == [("1.2.0", "21/10/2026", "Bảng việc mới"),
                                 ("1.1.0", "20/10/2026", "TUI và web đồng bộ hơn")]
    rows = bs.changelog_html(bs.releases(text), "en")
    assert 'lang="vi"' in rows and "v1.2.0" in rows


def test_build_site_vi_en(tmp_path):
    bs = _build_site()
    dist = tmp_path / "dist"
    bs.main(dist)
    v = bs.version()
    pages = {p: (dist / p).read_text(encoding="utf-8") for p in ("index.html", "en/index.html", "404.html")}
    latest = bs.releases((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))[0]
    for name, html in pages.items():
        assert "{{" not in html, name
    for name in ("index.html", "en/index.html"):
        html = pages[name]
        assert f"v{v}" in html and f"v{latest[0]}" in html
        # mọi file nội bộ được tham chiếu (ảnh chụp, css, js, zip) đều nằm trong dist/
        for ref in re.findall(r'(?:src|href)="(/[^"#?]*)', html):
            if ref in ("/", "/en/"):
                continue
            assert (dist / ref.lstrip("/")).is_file(), f"{name}: thiếu {ref}"
    assert 'hreflang="en"' in pages["index.html"] and 'hreflang="vi"' in pages["en/index.html"]
    assert "/shots/en/" in pages["en/index.html"] and "/shots/en/" not in pages["index.html"]
    assert (dist / "version.txt").read_text().strip() == v
