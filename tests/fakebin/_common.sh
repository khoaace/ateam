# Dùng chung cho các agent giả lập (source từ từng script).
# Biến môi trường điều khiển:
#   ATEAM_FAKE_SLOW       giây nghỉ giữa các dòng output (mặc định 0)
#   ATEAM_FAKE_LIMIT_DIR  nếu có file <tên agent> trong thư mục này -> giả lập hết hạn mức
#   ATEAM_FAKE_ARGS_LOG   nếu đặt, ghi toàn bộ argv (trừ prompt) vào file này để test kiểm tra cờ
#   ATEAM_FAKE_FULL_LOG   nếu đặt, ghi toàn bộ argv kể cả prompt (để test nội dung prompt)
#   fake_flags            (đặt trước khi source) các cờ CLI "biết", in ra ở --help cho `ateam doctor`
fake_name="$(basename "$0")"
fake_prompt="${@: -1}"
case "$fake_prompt" in
  --version) echo "$fake_name 0.0.0-fake"; exit 0 ;;
  --help) echo "Usage: $fake_name [OPTIONS] (giả lập)"; for f in ${fake_flags:-}; do echo "  $f"; done; exit 0 ;;
esac
if [ -n "${ATEAM_FAKE_ARGS_LOG:-}" ]; then
  args=("$@"); unset 'args[${#args[@]}-1]'
  echo "$fake_name ${args[*]}" >> "$ATEAM_FAKE_ARGS_LOG"
fi
if [ -n "${ATEAM_FAKE_FULL_LOG:-}" ]; then
  echo "<<$fake_name>> $*" >> "$ATEAM_FAKE_FULL_LOG"
fi
# Chế độ tương tác (tab 🔲 Lưới, ⌨ Mở trong terminal): stdin là terminal và không có cờ headless → REPL nhỏ:
# in lại dòng gõ vào; "size" in kích thước pty; "exit" thoát
fake_headless=0
for a in "$@"; do case "$a" in -p|--print|exec|run) fake_headless=1 ;; esac; done
if [ "$fake_headless" = 0 ] && [ -t 0 ]; then
  printf '\033[1;35m* %s (gia lap tuong tac)\033[0m args: %s\n' "$fake_name" "$*"
  while IFS= read -r line; do
    case "$line" in
      exit) exit 0 ;;
      size) stty size ;;
      *) printf '\033[36m%s>\033[0m %s\n' "$fake_name" "$line" ;;
    esac
  done
  exit 0
fi
fake_limited() { [ -n "${ATEAM_FAKE_LIMIT_DIR:-}" ] && [ -f "$ATEAM_FAKE_LIMIT_DIR/$1" ]; }
fake_sleep() { sleep "${ATEAM_FAKE_SLOW:-0}"; }
