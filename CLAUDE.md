# CLAUDE.md

@AGENTS.md

## Ghi chú riêng cho Claude Code

- Mọi quy tắc nằm trong `AGENTS.md` (đã import ở trên) và `docs/`. Nếu import không hoạt động, mở
  `AGENTS.md` đọc trước.
- Trước khi sửa: `python -m pytest -q` để chắc nền đang xanh. Sau khi sửa: chạy lại.
- Thay đổi giao diện: chụp màn hình bằng `App.run_test()` + `save_screenshot()` để tự xem lại
  (xem mục "Kiểm tra giao diện" trong `docs/DEVELOPMENT.md`).
- Commit message tiếng Việt, mô tả *vì sao*; không commit `dist/`, `.ateam/`, `__pycache__/`.
