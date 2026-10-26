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

### Khi CI hỏng

Bước cuối của job ghi các dòng `FAILED …`/`E …` của pytest thành annotation, đọc được kể cả khi không
tải được log:

```bash
RID=$(gh run list -R khoaace/ateam --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view -R khoaace/ateam $RID --json jobs --jq '.jobs[] | select(.conclusion!="success") | .databaseId' |
  while read J; do gh api repos/khoaace/ateam/check-runs/$J/annotations --jq '.[].message'; done
```

Tái hiện lỗi chỉ có trên Ubuntu: chạy test với `HOME` trống và `GIT_CONFIG_GLOBAL=/dev/null`
(xem `docs/DEVELOPMENT.md`).

## Trang docs

- Nội dung: `site/index.html` (tiếng Việt) và `site/en/index.html` (tiếng Anh) — cùng bố cục, sửa một trang thì sửa
  cả trang kia. CSS/JS dùng chung ở `site/assets/site.css`, `site/assets/site.js` (phong cách terminal như `ateam web`;
  font Be Vietnam Pro + JetBrains Mono từ Google Fonts). Kịch bản terminal ở hero nằm trong
  `<script type="application/json" id="hero-script">` của từng trang.
- Placeholder trong mọi trang `.html` của `site/` do `build_site.py` điền: `{{VERSION}}`, `{{ZIP_NAME}}`, `{{ZIP_SIZE}}`,
  `{{BUILD_DATE}}`, `{{LATEST}}` / `{{LATEST_DATE}}` (bản mới nhất), `{{CHANGELOG}}` / `{{CHANGELOG_EN}}` (5 bản mới
  nhất, bóc từ `CHANGELOG.md`: tiêu đề `## x — ngày` + chữ **đậm** đầu tiên hoặc câu mở đầu của bản đó — viết mục
  CHANGELOG sao cho dòng đầu tóm được cả bản). Build báo lỗi nếu còn placeholder chưa điền.
- Cả `site/` (vd `404.html`, `assets/`, `en/`, `shots/`) được chép sang `dist/`.
- `site/shots/*.svg` là ảnh chụp TUI thật cho gallery "Một vòng làm việc", tạo bằng `python scripts/site_shots.py`
  (dự án demo + agent giả lập có nội dung thật, `App.run_test()` + `save_screenshot()`; không gọi CLI thật).
  Chạy lại và commit khi giao diện đổi đáng kể.
- `site/shots/web-*.webp` là ảnh giao diện web: `python scripts/site_shots.py --web` (chạy `ateam web` trên cùng dự
  án demo, chụp bằng Chrome headless qua DevTools protocol; cần `aiohttp` và Chrome/Chromium, biến `CHROME` nếu ở chỗ khác).
  Gồm cả cảnh breadcrumb, Source Control (`web-scm`), Terminal (shell tương tác), Skills và Thống kê với thanh bên thu
  gọn (vòng tròn hạn mức — CLI giả trả `/usage`). Trên Linux: `CHROME=/đường/dẫn/chromium`.
- Bản tiếng Anh: thêm `--lang en` (cả hai lệnh trên) → `site/shots/en/`; app chạy tiếng Anh, dữ liệu demo dịch theo
  bảng `EN` trong `site_shots.py` (thiếu bản dịch thì script dừng và chỉ ra chỗ còn chữ Việt).
- Gói zip chứa thư mục `ateam/` với `pyproject.toml`, `README.md`, `install.sh` và package `ateam/`
  (xem `PACKAGE_FILES`/`PACKAGE_DIRS` trong `build_site.py`).
- Xem thử cục bộ: `python scripts/build_site.py && python -m http.server -d dist 8000` (mở `/` và `/en/`).
- Deploy tay (cần đăng nhập wrangler): `npx wrangler deploy`.

## Khi deploy lỗi

Dashboard Cloudflare → Workers & Pages → `ateam` → Deployments → bản build lỗi → log. Lỗi hay gặp:
placeholder chưa điền trong `site/index.html`, script build đổi tên file, `wrangler.jsonc` sai cú pháp.
Build cho nhánh PR chạy `npx wrangler preview`, lệnh này bắt buộc `wrangler.jsonc` có khối `"previews": {}`.
Workers Builds tự chạy `pip install .` vì thấy `pyproject.toml` — bước thừa nhưng vô hại (~10 giây).
