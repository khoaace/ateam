# Dùng chung cho các agent giả lập (source từ từng script).
# Biến môi trường điều khiển:
#   ATEAM_FAKE_SLOW       giây nghỉ giữa các dòng output (mặc định 0)
#   ATEAM_FAKE_LIMIT_DIR  nếu có file <tên agent> trong thư mục này -> giả lập hết hạn mức
#   ATEAM_FAKE_ARGS_LOG   nếu đặt, ghi toàn bộ argv (trừ prompt) vào file này để test kiểm tra cờ
#   ATEAM_FAKE_FULL_LOG   nếu đặt, ghi toàn bộ argv kể cả prompt (để test nội dung prompt)
fake_name="$(basename "$0")"
fake_prompt="${@: -1}"
if [ -n "${ATEAM_FAKE_ARGS_LOG:-}" ]; then
  args=("$@"); unset 'args[${#args[@]}-1]'
  echo "$fake_name ${args[*]}" >> "$ATEAM_FAKE_ARGS_LOG"
fi
if [ -n "${ATEAM_FAKE_FULL_LOG:-}" ]; then
  echo "<<$fake_name>> $*" >> "$ATEAM_FAKE_FULL_LOG"
fi
fake_limited() { [ -n "${ATEAM_FAKE_LIMIT_DIR:-}" ] && [ -f "$ATEAM_FAKE_LIMIT_DIR/$1" ]; }
fake_sleep() { sleep "${ATEAM_FAKE_SLOW:-0}"; }
