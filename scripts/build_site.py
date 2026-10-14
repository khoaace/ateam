#!/usr/bin/env python3
"""Dựng trang docs vào dist/: index.html (điền phiên bản) + gói ateam-<version>.zip để tải.

Chạy tự động khi deploy (wrangler.jsonc -> build.command), hoặc tay: python3 scripts/build_site.py
"""

from __future__ import annotations

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


def human(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def main() -> None:
    v = version()
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()
    zip_name = f"ateam-{v}.zip"
    build_zip(DIST / zip_name)
    shutil.copy2(DIST / zip_name, DIST / "ateam.zip")  # link "bản mới nhất" cố định
    size = human((DIST / zip_name).stat().st_size)

    html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    for key, val in {"VERSION": v, "ZIP_NAME": zip_name, "ZIP_SIZE": size,
                     "BUILD_DATE": time.strftime("%d/%m/%Y")}.items():
        html = html.replace("{{" + key + "}}", val)
    left = re.findall(r"\{\{[A-Z_]+\}\}", html)
    if left:
        raise SystemExit(f"Còn placeholder chưa điền: {left}")
    (DIST / "index.html").write_text(html, encoding="utf-8")
    (DIST / "version.txt").write_text(v + "\n", encoding="utf-8")
    for extra in (ROOT / "site").iterdir():
        if extra.name != "index.html" and extra.is_file():
            shutil.copy2(extra, DIST / extra.name)
    print(f"dist/ sẵn sàng: ateam {v}, {zip_name} ({size})")


if __name__ == "__main__":
    main()
