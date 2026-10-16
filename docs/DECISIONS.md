# Các quyết định thiết kế

Mỗi mục: quyết định, lý do, và điều sẽ khiến nên xem lại. Đọc trước khi "dọn" code — nhiều chỗ trông
thừa là có chủ đích.

## 1. Gọi CLI headless, không gọi API mô hình

**Quyết định**: mỗi agent là một CLI có sẵn (`claude -p`, `codex exec`, `agy -p`, `opencode run`) chạy
như tiến trình con. **Lý do**: dùng gói đăng ký và cấu hình sẵn có của người dùng, không cần API key,
mỗi CLI tự lo đọc/sửa file và công cụ của nó; thêm agent mới chỉ là thêm vài dòng cấu hình.
**Đánh đổi**: không có số token chính xác, phụ thuộc định dạng output và cờ của từng CLI.

## 2. Giao thức bằng văn bản trong output, không bằng MCP

**Quyết định**: agent báo kết quả bằng dòng `SUMMARY:`, giao việc bằng khối `<<<DELEGATE …>>>`,
ghi chú bằng `<<<NOTE>>>`; trưởng nhóm trả JSON. **Lý do**: hoạt động với mọi CLI kể cả khi agent bị
sandbox chặn ghi ra ngoài thư mục làm việc (Codex `--sandbox workspace-write` không ghi được `.ateam/team.db` từ
worktree) hoặc không được chạy lệnh shell. Lệnh `ateam add/note` vẫn có cho agent chạy được shell.
**Xem lại nếu**: muốn agent giao việc *giữa chừng* và chờ kết quả — khi đó cần MCP server của ateam.

## 3. SQLite làm bảng việc

**Lý do**: nhiều tiến trình (TUI, `ateam add` do agent gọi, CLI khác) cùng ghi; WAL + `busy_timeout`
đủ cho vài chục task; không cần server. TUI đọc lại DB định kỳ thay vì nghe sự kiện nên thấy cả thay
đổi từ ngoài.

## 4. Một vòng lặp asyncio, không thread

**Lý do**: Textual đã chạy asyncio; tiến trình con và pty đọc qua `asyncio`/`add_reader`. Tránh khoá
và race giữa thread với DB/TUI. **Hệ quả**: không bao giờ gọi API chặn (`subprocess.run`,
`time.sleep`) trong orchestrator/TUI.

## 5. Chạy `agy` qua pty

**Lý do**: `agy -p` không in gì (thoát 0) hoặc treo khi stdout không phải terminal. Pty 220 cột cho
output đầy đủ; `clean_line` bỏ mã ANSI và `\r`. Task thoát 0 nhưng không in gì bị coi là lỗi để lộ
ra tình huống này.

## 6. Chèn cờ model/effort ngay trước prompt

**Lý do**: một số CLI viết bằng Go `flag` dừng đọc cờ ở đối số vị trí đầu tiên, và `-p` của vài CLI
nhận prompt làm giá trị; đặt cờ trước `-p`/prompt an toàn cho cả hai kiểu. Cờ nằm trong cấu hình
(`model_args`/`effort_args`) vì mỗi CLI gọi khác nhau (Codex dùng `-c model_reasoning_effort=…`,
OpenCode dùng `--variant`).

## 7. Kế hoạch ở trạng thái nháp mặc định

**Lý do**: nhìn kế hoạch vài giây rẻ hơn nhiều so với 4 agent chạy sai hướng hàng chục phút. Tắt bằng
`approve_plan = false`. Task bổ sung sau review cũng đi qua bước này.

## 8. Worktree theo task, merge `--no-ff`, xung đột thì dừng

**Lý do**: cho phép nhiều agent sửa code song song mà không ghi đè nhau; mỗi task là một commit merge
rõ ràng, dễ revert. ateam không tự giải xung đột (agent có thể giải sai một cách âm thầm) — task chuyển
`conflict`, nhánh được giữ. Task phụ thuộc chạy trên HEAD *sau khi* task trước đã merge.
**Hạn chế**: worktree yêu cầu chạy ở gốc repo đã có commit; ở chế độ shared không tách được diff theo task.

## 9. Verify chạy trong thư mục của task và giao sửa kèm log

**Lý do**: agent hay báo "xong" khi test còn đỏ. Chạy lệnh của người dùng là phán quyết khách quan; giao
lại kèm 120 dòng cuối output cho đúng agent (đã có ngữ cảnh) hoặc agent sửa lỗi chỉ định. `only_when_changed`
tránh chạy test cho task chỉ đọc/nghiên cứu. Ở chế độ shared, test thấy cả thay đổi của task khác
đang chạy song song — chấp nhận được; dùng worktree nếu cần tách bạch.

## 10. Nhận diện hết hạn mức bằng mẫu chữ, chỉ khi agent thất bại hoặc in ít

**Lý do**: không CLI nào có mã thoát riêng cho rate limit. Giới hạn ở "rc ≠ 0 hoặc ≤ 15 dòng" để không
nhầm task đang viết code về rate limiter. Cooldown lưu toàn cục vì hạn mức theo tài khoản, không theo
dự án. **Xem lại nếu**: thêm CLI có output JSON nêu rõ lỗi hạn mức — nên đọc trường đó thay vì regex.

## 11. UI tiếng Việt, prompt tiếng Anh

**Lý do**: người dùng là developer Việt Nam; mô hình tuân thủ định dạng (JSON, SUMMARY) ổn định hơn
với hướng dẫn tiếng Anh. Prompt dặn agent viết tiêu đề/nội dung theo ngôn ngữ của mục tiêu.

## 12. Trang docs trên Cloudflare Workers (static assets), build bằng Python

**Lý do**: tài khoản người dùng đã dùng nhiều Workers; Workers Builds nối với GitHub nên mỗi push lên
`main` tự deploy; `wrangler.jsonc` có `build.command` nên `npx wrangler deploy` tự dựng `dist/`.
Python có sẵn trong image build (không cần npm package để nén zip). Cài một lệnh (`scripts/get.sh`)
tải từ GitHub nên không phụ thuộc domain của trang docs.

## 13. Giao diện web riêng (aiohttp + JS thuần), một server một bộ lập lịch

**Lý do**: người dùng muốn giao diện web hiện đại (Kanban, nút bấm) và đủ chức năng như terminal. Server aiohttp
giữ *một* `Orchestrator` cho mọi tab → mở nhiều tab không chạy trùng task (bảng việc chưa có bước "nhận task" nguyên
tử). Trang là HTML/CSS/JS thuần trong gói: không cần npm/build lúc chạy (CI và gói zip chỉ có Python), chạy offline.
aiohttp là extra không bắt buộc (`ateam[web]`). Đẩy *ảnh chụp* trạng thái thay vì diff sự kiện: đơn giản, đúng cả khi
CLI/agent khác ghi DB. Logic nằm trong màn hình Textual (wizard /setup, form /custom, báo cáo /usage…) được tách ra
`wizard.py`/`reports.py` để hai giao diện dùng chung; riêng bộ điều phối lệnh `/…` viết hai nơi (lệnh TUI gắn chặt
widget) — test đối chiếu `tui.COMMANDS` giữ chúng đồng bộ. Chỉ nghe `127.0.0.1` + kiểm Host/Origin vì giao diện chạy
được shell.
**Editor**: CodeMirror 6 + `@replit/codemirror-vim` đóng gói một lần (`scripts/editor/`, esbuild) thành
`webui/vendor/codemirror.js` (~1,2 MB, ~400 KB nén) và commit vào repo — không CDN, không Node lúc chạy; chỉ gói
~25 ngôn ngữ phổ biến (gói `language-data` đầy đủ 1,7 MB). Vim thật (`:w`, chế độ, thanh ghi) thay vì port `VimState`
của TUI sang JS.
`ateam web --tui` giữ cách cũ (textual-serve chạy chính `ateam tui`, mỗi tab một tiến trình → khoá
`.ateam/tui.lock`, phiên thứ hai thấy `BusyApp`; `/lang` không `execv` vì tiến trình mới sẽ mồ côi, giữ khoá).
**Xem lại nếu**: cần truy cập từ máy khác (cần token + TLS); cần nhiều tiến trình cùng lập lịch (nhận task nguyên
tử trong SQLite); cần đổi theme Textual trên web (hiện web chỉ dùng chung màu nhấn).
