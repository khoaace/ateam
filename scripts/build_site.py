#!/usr/bin/env python3
"""Dựng trang docs vào dist/: các trang HTML trong site/ (điền phiên bản, changelog) + gói ateam-<version>.zip để tải.

Chạy tự động khi deploy (wrangler.jsonc -> build.command), hoặc tay: python3 scripts/build_site.py
"""

from __future__ import annotations

import html
import re
import shutil
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
# những gì nằm trong gói tải về (thư mục gốc trong zip là "ateam/")
PACKAGE_FILES = ["pyproject.toml", "README.md", "install.sh"]
PACKAGE_DIRS = ["ateam"]


def version() -> str:
    text = (ROOT / "ateam" / "__init__.py").read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    return m.group(1) if m else "dev"


def build_zip(dest: Path) -> None:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for name in PACKAGE_FILES:
            src = ROOT / name
            info = zipfile.ZipInfo.from_file(src, f"ateam/{name}")
            if name.endswith(".sh"):
                info.external_attr = 0o100755 << 16  # giữ quyền chạy
            z.writestr(info, src.read_bytes(), zipfile.ZIP_DEFLATED)
        for d in PACKAGE_DIRS:
            for src in sorted((ROOT / d).rglob("*")):
                if src.is_file() and "__pycache__" not in src.parts and src.suffix != ".pyc":
                    z.write(src, f"ateam/{src.relative_to(ROOT)}")


def releases(text: str, n: int = 5) -> list[tuple[str, str, str]]:
    """(phiên bản, ngày, tiêu đề) của n bản mới nhất trong CHANGELOG.md, bỏ mục "Chưa phát hành". Tiêu đề = chữ
    **đậm** đầu tiên của bản đó, hoặc dòng mô tả đầu tiên nếu bản mở đầu bằng một câu."""
    out = []
    for m in re.finditer(r"^## (\d[\w.]*) — (\S+)\n(.*?)(?=^## |\Z)", text, re.M | re.S):
        lines = [ln.strip() for ln in m.group(3).splitlines() if ln.strip()]
        first = lines[0] if lines else ""
        bold = re.search(r"\*\*(.+?)\*\*", first)
        title = bold.group(1) if bold else first.rstrip(":")
        title = re.sub(r"[`*]", "", title).strip()
        out.append((m.group(1), m.group(2), title))
        if len(out) >= n:
            break
    return out


def changelog_html(items: list[tuple[str, str, str]], page_lang: str) -> str:
    """Các dòng log của mục "Có gì mới"; tiêu đề lấy từ CHANGELOG.md (tiếng Việt) nên trang khác gắn lang="vi"."""
    attr = "" if page_lang == "vi" else ' lang="vi"'
    return "\n".join(f'        <div class="row"><span class="v">v{v}</span><span class="d">{d}</span>'
                     f'<span class="t"{attr}>{html.escape(t)}</span></div>' for v, d, t in items)


def human(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def main(dist: Path = DIST) -> None:
    v = version()
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir()
    zip_name = f"ateam-{v}.zip"
    build_zip(dist / zip_name)
    shutil.copy2(dist / zip_name, dist / "ateam.zip")  # link "bản mới nhất" cố định
    size = human((dist / zip_name).stat().st_size)

    rel = releases((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    latest = rel[0] if rel else (v, "", "")
    values = {"VERSION": v, "ZIP_NAME": zip_name, "ZIP_SIZE": size, "BUILD_DATE": time.strftime("%d/%m/%Y"),
              "LATEST": html.escape(latest[2]), "LATEST_DATE": latest[1],
              "CHANGELOG": changelog_html(rel, "vi"), "CHANGELOG_EN": changelog_html(rel, "en")}
    # site/ chép nguyên sang dist/ (shots/, assets/, en/…); trang HTML được điền placeholder
    shutil.copytree(ROOT / "site", dist, dirs_exist_ok=True)
    for page in sorted(dist.rglob("*.html")):
        text = page.read_text(encoding="utf-8")
        for key, val in values.items():
            text = text.replace("{{" + key + "}}", val)
        left = re.findall(r"\{\{[A-Z_]+\}\}", text)
        if left:
            raise SystemExit(f"{page.relative_to(dist)}: còn placeholder chưa điền: {left}")
        page.write_text(text, encoding="utf-8")
    (dist / "version.txt").write_text(v + "\n", encoding="utf-8")
    print(f"{dist.name}/ sẵn sàng: ateam {v}, {zip_name} ({size})")


if __name__ == "__main__":
    main()
