#!/usr/bin/env bash
# Cài AI Team (lệnh `ateam`) trên macOS / Linux.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${ATEAM_HOME:-$HOME/.ateam}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"

# Tìm Python >= 3.9 (ưu tiên bản mới của Homebrew)
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
      PY="$(command -v "$c")"; break
    fi
  fi
done
if [ -z "$PY" ]; then
  echo "✗ Cần Python 3.9+.  Cài bằng:  brew install python"
  exit 1
fi
echo "→ Dùng $("$PY" --version) tại $PY"

echo "→ Tạo môi trường ảo tại $PREFIX/venv"
"$PY" -m venv "$PREFIX/venv"
"$PREFIX/venv/bin/python" -m pip install --quiet --upgrade pip
"$PREFIX/venv/bin/python" -m pip install --quiet --upgrade "$HERE"

mkdir -p "$BIN_DIR"
ln -sf "$PREFIX/venv/bin/ateam" "$BIN_DIR/ateam"
echo "→ Đã tạo lệnh: $BIN_DIR/ateam"

"$PREFIX/venv/bin/ateam" init

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo
    echo "⚠ $BIN_DIR chưa có trong PATH. Chạy lệnh sau rồi mở terminal mới:"
    echo "    echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.zshrc"
    ;;
esac

echo
echo "✓ Xong. Tiếp theo:"
echo "    ateam doctor        # kiểm tra claude / codex / agy / opencode"
echo "    cd <dự án> && ateam # mở giao diện"
