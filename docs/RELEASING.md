# Phát hành và deploy

## Phát hành phiên bản mới

1. `python -m pytest -q` xanh.
2. Tăng phiên bản ở **cả hai** chỗ: `ateam/__init__.py` (`__version__`) và `pyproject.toml` (`version`).
   Trang docs và tên file zip lấy phiên bản từ `__init__.py`; `install.sh` dùng `pip install --upgrade`
   nên cần `pyproject.toml` tăng thì máy người dùng mới cài lại.
3. Ghi `CHANGELOG.md` (mục mới trên cùng).
4. Nếu đổi mặc định cấu hình: tăng `CONFIG_VERSION` trong `config.py` và `config_version` trong
   `DEFAULT_CONFIG`; ghi trong CHANGELOG rằng file cấu hình sẽ được thay (có sao lưu).
5. Commit, push lên `main`.

Sau khi push:

- **GitHub Actions** (`.github/workflows/ci.yml`) chạy test trên Ubuntu + macOS, Python 3.9 và 3.13,
  và dựng thử trang docs.
- **Cloudflare Workers Builds** (Worker `ateam`, account "Khoaace@gmail.com's Account", nối repo
  `khoaace/ateam`, nhánh `main`) chạy `npx wrangler deploy` → `build.command` trong `wrangler.jsonc`
  chạy `python3 scripts/build_site.py` → upload `dist/`. Mất khoảng 30 giây.
  Trang: https://ateam.khoaace.workers.dev — file tải: `/ateam.zip` (luôn mới nhất) và
  `/ateam-<phiên bản>.zip`; `/version.txt` để kiểm tra nhanh bản đang chạy.

Người dùng nâng cấp bằng lệnh cài một dòng (tải nhánh `main` từ GitHub):

```bash
curl -fsSL https://raw.githubusercontent.com/khoaace/ateam/main/scripts/get.sh | bash
```

## Trang docs

- Nội dung: `site/index.html` (một file, CSS/JS nội tuyến, font Be Vietnam Pro + JetBrains Mono từ
  Google Fonts). Placeholder `{{VERSION}}`, `{{ZIP_NAME}}`, `{{ZIP_SIZE}}`, `{{BUILD_DATE}}` do
  `build_site.py` điền; build báo lỗi nếu còn placeholder chưa điền.
- File khác trong `site/` (vd `404.html`) được chép nguyên vào `dist/`.
- Gói zip chứa thư mục `ateam/` với `pyproject.toml`, `README.md`, `install.sh` và package `ateam/`
  (xem `PACKAGE_FILES`/`PACKAGE_DIRS` trong `build_site.py`).
- Xem thử cục bộ: `python scripts/build_site.py && python -m http.server -d dist 8000`.
- Deploy tay (cần đăng nhập wrangler): `npx wrangler deploy`.

## Khi deploy lỗi

Dashboard Cloudflare → Workers & Pages → `ateam` → Deployments → bản build lỗi → log. Lỗi hay gặp:
placeholder chưa điền trong `site/index.html`, script build đổi tên file, `wrangler.jsonc` sai cú pháp.
Workers Builds tự chạy `pip install .` vì thấy `pyproject.toml` — bước thừa nhưng vô hại (~10 giây).
