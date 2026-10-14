#!/usr/bin/env bash
# Cài hoặc nâng cấp ateam bằng một lệnh:
#   curl -fsSL https://raw.githubusercontent.com/khoaace/ateam/main/scripts/get.sh | bash
set -euo pipefail

REF="${ATEAM_REF:-main}"
URL="https://github.com/khoaace/ateam/archive/refs/heads/${REF}.tar.gz"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "→ Tải ateam ($REF) từ GitHub"
curl -fsSL "$URL" | tar -xz -C "$TMP"
SRC="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -1)"
bash "$SRC/install.sh"
