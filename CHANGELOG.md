# Changelog

## 0.13.0 — 17/10/2026

- **Giữ phiên agent**: `/retry`, từ chối kèm góp ý, vòng sửa khi kiểm tra fail, trả lời câu hỏi của agent và
  `/continue` (thread `/task`) tiếp tục đúng phiên CLI (`claude --resume`, `codex exec resume`, `grok --resume`), chỉ
  gửi phần mới thay vì nhồi lại cả ngữ cảnh; `/continue m<id>` tiếp tục phiên lập kế hoạch của trưởng nhóm. Phiên
  không còn thì tự chạy lại với đủ ngữ cảnh. Token/cost của lượt resume đọc đúng file phiên. Cấu hình: `session_args`,
  `resume_args`, `session_re`.
- **Agent hỏi lại giữa task** bằng `<<<ASK>>>`: task chuyển sang *đang hỏi bạn*, câu hỏi hiện ở khung /grill (terminal
  và web) với phương án gợi ý; trả lời là agent làm tiếp trong cùng phiên, phần làm dở được giữ. Có thông báo.
  `ateam goal -y` / `ateam run` tự chọn phương án khuyên dùng.
- **Dùng từ điện thoại**: `ateam web --tunnel` (Cloudflare quick tunnel, https, không cần tài khoản), `--host 0.0.0.0`
  (LAN), `--public-url` (named tunnel / domain riêng). Chế độ từ xa bắt buộc token (`.ateam/web_token`), in URL + mã
  QR ra terminal và nút 📱 Điện thoại trên web; cookie HttpOnly, chặn Origin lạ, khoá khi sai token nhiều lần;
  `--readonly` chỉ xem, `--new-token` đổi token. Giao diện web gọn hơn ở màn hình ≤ 480px.

## 0.12.0 — 17/10/2026

- **Thông báo** khi có việc cần bạn: kế hoạch chờ duyệt, task chờ duyệt diff, task lỗi hoặc xung đột merge.
  Terminal: toast + chuông + thông báo macOS (Notification Center; Linux `notify-send`). Web: toast + thông báo của
  trình duyệt khi tab đang ẩn, tiêu đề tab hiện số việc chờ "(2) ateam". `/notify on|app|off|test`.
- **Tab 🧩 Tuỳ chỉnh** (terminal) / mục **Tuỳ chỉnh** ở sidebar (web): agent & workflow tuỳ chỉnh không còn chỉ là
  popup; `/custom` mở tab này.
- **Popup "Luồng mặc định"** (`/flow-setup`, nút ở tab Tuỳ chỉnh và ở bước *Kiểu làm việc* của `/setup`): chọn
  agent · model · effort cho từng bước của workflow chạy khi gõ mục tiêu, bật/tắt review cuối.
- **Dashboard** — tab 📊 Thống kê (terminal), mục Thống kê (web), `/dash`: token, cost, lượt, thời gian hôm nay /
  7 / 30 ngày, biểu đồ token 14 ngày, theo agent và theo model, lịch sử mục tiêu (task, agent, token, cost, kết quả;
  Enter / nút để `/continue`). Token của Claude Code và Codex đọc từ file phiên CLI tự ghi; agent khác ước tính.
  Cost theo bảng giá công khai, ghi đè bằng `[prices."<model>"]`. `/usage` dùng số thật này.
- Tab Git: commit xong thì xoá ô message (web trước đây giữ lại); chọn agent viết commit message (mặc định trưởng
  nhóm), lưu `commit_agent` dùng chung terminal và web.
- Web: JS/CSS có `?v=` theo phiên bản — nâng cấp xong không bị trình duyệt dùng file cũ trong cache.

## 0.11.2 — 16/10/2026

- Agent báo không nhận effort với model đang chọn (vd Antigravity + `claude-opus-4-6-thinking`: "--effort is not
  supported for model …") thì tự chạy lại ngay không kèm effort và ghi nhớ model đó, không còn lỗi task.

## 0.11.1 — 16/10/2026

- Sửa lỗi Antigravity `--model gemini-4-argon-medium conflicts with --effort=high`: model đã có effort trong tên
  thì không thêm cờ `--effort` nữa mà đổi sang biến thể đúng effort (vd `gemini-4-argon-high`) nếu `agy models` có.

## 0.11.0 — 16/10/2026

- **`ateam web` — giao diện web hiện đại, đủ chức năng như terminal** (http://127.0.0.1:8000, `--open`, `--port`):
  - Bảng Kanban, thẻ mục tiêu có tiến độ, duyệt kế hoạch bằng nút (đổi agent, sửa task), `/grill` bấm chọn, ngăn chi
    tiết task (log trực tiếp, diff, merge/từ chối, chạy lại, hỏi tiếp), tab Đội (bấm agent để đổi model/effort),
    Terminal (`!lệnh`, gợi ý script, link port).
  - Tab **Git**: stage/unstage/bỏ thay đổi, commit (trưởng nhóm viết message, amend, `--no-verify`), lịch sử, xem
    commit, revert, bỏ commit cuối, nhánh (tạo/chuyển/merge/đổi tên/xoá), stash, fetch/pull/push; phím như TUI.
  - Tab **Code**: cây thư mục + tìm file, nhiều file, editor CodeMirror 6 có phím vim (`:w :q :wq :e! :bn :bp`),
    tô cú pháp ~25 ngôn ngữ, giữ CRLF, hỏi khi file đổi trên đĩa, tự nạp lại khi agent sửa file đang mở.
  - Diff kiểu VS Code (2 cột / 1 cột, chữ đổi trong dòng, tô cú pháp, nhảy hunk, mở dòng đó ở tab Code) cho task và git.
  - `/setup` (wizard 7 bước), `/custom` (agent nhanh/nâng cao có xem trước lệnh, workflow), `/help`, `/usage`,
    `/models`, `/agents`, `/model`/`/effort` (bảng chọn), `/theme` (sáng/tối + màu nhấn dùng chung terminal), `/vim`,
    `/lang`, `/update` — mọi lệnh của TUI.
  - Ô nhập gợi ý cả tham số: `/task ` → agent → `:model` → `@effort`, task/mục tiêu/nhánh/workflow/file…; dòng giải
    thích `/continue`, F6 tiếp tục.
  - Một server cho mọi tab — không chạy trùng task. Cần `aiohttp` (extra `ateam[web]`).
- `ateam web --tui`: chính giao diện terminal trong trình duyệt (cần `textual-serve`).
- Mỗi dự án chỉ mở 1 phiên giao diện (terminal, `ateam web`, hoặc tab `--tui`) — phiên thứ hai báo đang mở ở
  phiên khác thay vì chạy bộ lập lịch thứ hai có thể chạy trùng task.
- Trang docs: mục mới giới thiệu `ateam web` kèm ảnh chụp thật (`scripts/site_shots.py --web`).
- Bên trong: logic wizard /setup, form /custom và báo cáo /usage, /agents… tách khỏi `tui.py` sang `wizard.py`,
  `reports.py` để TUI và web dùng chung.

## 0.10.0 — 16/10/2026

- **Tab 📝 Code — xem & sửa source ngay trong app, phím vim**: `/code @file[:dòng]` (hoặc `/edit @file`, phím
  `e` ở tab Git và màn hình diff). Tô màu cú pháp (pygments, không cần cài thêm), số dòng, nhiều file, lọc file
  ở cột trái. Phím vim cốt lõi: normal/insert/visual, `hjkl w b e 0 ^ $ gg G Ctrl+D/U`, số đếm, `x dd D dw cw cc yy
  p P J r u Ctrl+R`, `v V`, `/ ? n N *`, `:w :q :wq :q! :e! :<dòng> :bn :bp`. `/vim off` để sửa kiểu thường
  (Ctrl+S lưu).
- An toàn: agent sửa file đang mở → tự nạp lại nếu bạn chưa sửa, không thì báo (`:e!` / `:w!`); lưu khi file
  trên đĩa đã đổi thì hỏi trước khi ghi đè; ghi qua file tạm; giữ CRLF; file nhị phân không mở; thoát app khi
  còn file chưa lưu thì hỏi lại.
- Hiệu năng: chỉ vẽ dòng đang hiện, tô màu chạy nền sau khi ngừng gõ, file lớn tắt tô màu / chỉ đọc; vá hai chỗ
  của Textual tính lại toàn file mỗi khung hình / mỗi phím (file 60 000 dòng mở < 1 giây, gõ không giật).

## 0.9.0 — 16/10/2026

- **Đa ngôn ngữ — tiếng Việt / English** cho toàn bộ app: TUI, trợ giúp, thông báo, log hệ thống, wizard, tab
  Git, lệnh `ateam …`. Đổi bằng `/lang en|vi` (app tự mở lại), `ateam lang en|vi` (lưu lâu dài) hoặc
  `ateam --lang en …` (một lần) / biến `ATEAM_LANG`. Máy mới tự chọn theo `LANG`; người dùng cũ giữ tiếng Việt.
  Prompt gửi agent vẫn tiếng Anh như trước.
- **Theme màu**: `/theme` mở màn hình chọn 1 trong 21 theme dựng sẵn (tối/sáng: nord, dracula, gruvbox,
  tokyo-night, catppuccin, solarized…) cộng màu nhấn tuỳ chọn (xanh dương, tím, xanh lá, cam, hồng, vàng, xanh
  ngọc, đỏ), xem trước trực tiếp khi di chuyển, Esc trả theme cũ. Lệnh nhanh `/theme nord tím`. Màu trạng thái
  (đang chạy, xong, lỗi, chờ duyệt), viền popup, khung agent và diff đổi theo theme (diff dùng màu nền sáng trên
  theme sáng). Lựa chọn lưu ở `state.json`, dùng chung mọi dự án.
- **Thanh trạng thái** phía trên phím tắt: nhánh git ↑↓ và số file đổi, số task đang chạy / chờ / chờ duyệt /
  lỗi, tạm dừng, agent đang nghỉ vì hết hạn mức, theme và ngôn ngữ hiện tại (bấm để đổi).
- Tab Đội: viền khung agent theo trạng thái (đang chạy, đang nghỉ, lỗi gần nhất). Bảng việc: cột thời gian
  căn phải. Popup dùng viền màu chủ đạo của theme.

## 0.8.1 — 16/10/2026

- Khung hỏi đáp `/grill` dễ đọc hơn: phương án là chữ thường trên nền mặc định (trước đây nền cyan/xanh lá + chữ
  đen, khó đọc trên Terminal.app), số thứ tự có màu, phương án khuyên dùng in đậm kèm ★; dòng dài xuống hàng
  thụt lề thẳng chữ; dòng trống tách câu hỏi với phương án.

## 0.8.0 — 16/10/2026

- **`/grill <mục tiêu>` — trưởng nhóm "grill" bạn trước khi làm**: hỏi từng câu một (phạm vi, luồng, dữ liệu, ca
  biên, tiêu chí xong) kèm phương án gợi ý và phương án khuyên dùng, tự đọc code thay vì hỏi khi được. Trả lời ở
  ô nhập (gõ số / bấm để chọn phương án), "Để trưởng nhóm tự quyết", "Đủ rồi" để chốt. Xong thì trưởng nhóm viết
  bản đặc tả rồi lập kế hoạch; đặc tả đi kèm mục tiêu trong mọi prompt sau. Chạy được với mọi CLI.
- Tab 🌿 Git: ô **Bỏ qua hook (--no-verify)** dưới nút Commit và `/commit --no-verify <message>` (hoặc `-n`) để
  commit khi hook pre-commit/commit-msg (husky, lint-staged…) chặn. Commit bị hook chặn thì thông báo nhắc cách này.
- Tab Git: nút hàng stage gọn lại, không bị cắt ở terminal ~130 cột.

## 0.7.0 — 16/10/2026

- **Sửa: task của OpenCode lỗi "Unrecognized flag: --variant in command opencode run"** khi đặt effort. Bản
  OpenCode mới bỏ `--variant`; variant giờ ghi liền model (`--model xai/grok-4.7#medium`). Agent cũ và agent tuỳ
  chỉnh (vd `opencode-research`) tự được đổi khi đọc cấu hình. Cấu hình lên bản 8.
- **Tab 🌿 Git — quản lý git ngay trong app** (`/git`, Ctrl+T): nhánh, upstream, ↑ chưa push / ↓ chưa pull;
  file thay đổi theo nhóm (xung đột / đã stage / chưa stage) — Space stage/bỏ stage, `a` stage tất cả, `u` bỏ
  stage, Enter xem diff, `x` bỏ thay đổi (hỏi lại); commit, sửa commit trước (amend); **✨ trưởng nhóm viết commit
  message** từ diff theo kiểu các commit trước; lịch sử commit (xem diff, revert, bỏ commit cuối chưa push);
  nhánh (chuyển, tạo, đổi tên, merge, xoá, nhánh remote → nhánh local); fetch / pull / push (lần đầu tự tạo nhánh
  trên remote); stash (cất, lấy lại, áp dụng, xoá); huỷ merge dở. Lệnh tắt `/commit`, `/push`, `/pull`, `/fetch`,
  `/branch`, `/checkout`, `/stash`; `/git <lệnh>` chạy git bất kỳ ở tab Terminal. Không bao giờ hỏi mật khẩu
  trong app; đổi nhánh/pull/stash bị chặn khi agent đang chạy task.
- Cấu hình lên bản 8 (vì sửa OpenCode ở trên): file `~/.config/ateam/config.toml` cũ được sao lưu rồi thay
  bằng bản mới; model/effort đã chọn vẫn giữ.

## 0.6.1 — 16/10/2026

- **Sửa: Grok Build không sửa được file** (đã thử với grok thật): ở chế độ `-p`, `--permission-mode acceptEdits` của
  grok chặn cả việc sửa file ("permission required: Edit … headless run cannot ask for approval") mà task vẫn báo
  "xong". Giờ "chỉ sửa file" = `--permission-mode auto --deny Bash` (sửa/tạo file được, không chạy lệnh shell);
  Toàn quyền = `bypassPermissions`. Cấu hình cũ còn `acceptEdits` cũng được đổi khi chạy. Cấu hình lên bản 7.
- Grok bị chặn lệnh shell chỉ kể lại bằng lời (tiếng Anh/Việt) rồi thoát 0 — ateam nhận ra và báo task lỗi kèm
  hướng dẫn bật Toàn quyền.
- Grok Build có thêm mức effort `xhigh` (grok nhận: low, medium, high, xhigh); mức Tối đa ở wizard dùng `xhigh`.

## 0.6.0 — 16/10/2026

- **Tiếp tục mục tiêu hoặc thread đã xong**: chọn task rồi **F6** (Ctrl+O), bấm **↪ Tiếp tục** trong khung mục
  tiêu, hoặc `/continue` (gợi ý danh sách mục tiêu/thread đã kết thúc, dòng giải thích phía trên ô nhập).
  Mục tiêu được mở lại — trưởng nhóm lập task bổ sung dựa trên kết quả đã có; task giao tay thì cùng agent
  nhận các lượt trước kèm yêu cầu mới. Dòng lệnh: `ateam continue m12|t40 "yêu cầu"`. Báo khi mục tiêu xong.
- **Sửa: task của OpenCode (Grok) lỗi "File not found: You are …" khi mục tiêu/task nhắc `@file`**. `-f/--file`
  của `opencode run` là mảng nhận nhiều giá trị nên nuốt luôn prompt đứng sau thành tên file. Giờ ateam chèn
  `--` trước prompt khi cờ file đứng ngay trước nó.
- **Hỗ trợ Grok Build CLI** (`grok -p`, `-m`, `--reasoning-effort`, `--permission-mode`; model hỏi bằng `grok models`).
  Agent `grok` giờ chạy Grok Build; OpenCode thành agent riêng `opencode`. Cấu hình lên bản 6 (file cũ được sao
  lưu), lựa chọn đã lưu cho `grok` cũ (qua OpenCode) tự chuyển sang `opencode`.
- **Wizard thiết lập mới** (`/setup`, lần đầu mở app): hỏi từng bước — CLI đang dùng, kiểu làm việc, mức chi phí,
  CLI · model · effort cho từng vai trò (Trưởng nhóm, Code, Review, UI, Test, Nghiên cứu; một CLI hai model thì tự
  tạo thêm agent như `claude-review`), an toàn & duyệt code (quyền, worktree, duyệt diff), lệnh kiểm tra — rồi xem
  lại và lưu. Esc quay lại bước trước.
- **Nhanh hơn**: lướt bảng việc chỉ nạp log của dòng dừng lại và chỉ đọc phần cuối file log (log 5 MB: ~0,43 s →
  ~0,06 s mỗi dòng); đổi tab không còn hiệu ứng trượt và không vẽ tab đang ẩn (~0,4 s → ~0,1 s); mỗi lần làm mới
  chỉ đọc DB một lần, chỉ vẽ lại phần có thay đổi.
- **Sửa: log hiện mỗi chữ một dòng** khi terminal hẹp (cột log chỉ còn vài ký tự). Terminal dưới 110 cột thì bảng
  việc và log xếp dọc; đổi bề rộng cửa sổ thì log tự dàn lại.
- **Nút và popup gọn hơn**: nút chỉ có chữ `[ … ]` (màu chữ phân biệt, không nền), viền popup màu trung tính. Mọi
  popup có nút ✕; Esc chỉ đóng lớp trên cùng (đang mở danh sách chọn thì chỉ đóng danh sách); form đang sửa dở cần
  Esc hai lần.
- **Log bên phải**: prompt ateam bị CLI in lại được gập thành một dòng "‹prompt ateam gửi agent — đã ẩn›"; nút
  **🗑 Xoá log** phía trên ô log (chỉ ẩn trên màn hình, file log giữ nguyên; task chạy lại thì hiện log mới).

## 0.5.6 — 15/10/2026

- **Sửa: bật Toàn quyền cho agent ở /custom rồi quay lại /setup thì bị đè về "sửa file"**. Khi quay lại từ màn hình
  tuỳ chỉnh, form thiết lập khôi phục lựa chọn cũ của mọi ô (kể cả ô người dùng không đụng tới) và Ctrl+S ghi
  `full_access = false` vào `state.json`, đè lên `custom.toml`. Giờ chỉ giữ những ô đã đổi trong /setup; lưu
  agent ở /custom cũng bỏ các giá trị cũ của agent đó trong `state.json` (model, effort, vai trò, quyền).

## 0.5.5 — 15/10/2026

- **Quyền chạy lệnh cho agent**: cột *Quyền* mới ở `/setup` (cả agent có sẵn) và trong form agent — *sửa file*
  (mặc định) hoặc *toàn quyền* (chạy lệnh shell, mạng: lint, build, git push). ateam tự đổi cờ đúng từng CLI
  (claude `bypassPermissions`, codex `danger-full-access`, agy `--dangerously-skip-permissions`, opencode
  `--auto`); khoá cấu hình mới `full_access`.
- **Sửa: task bị tính "xong" dù agent bị từ chối quyền chạy lệnh** (agy in "a tool required the "command"
  permission … auto-denied" rồi thoát 0). Giờ task lỗi kèm hướng dẫn bật Toàn quyền.
- **Thêm agent đơn giản**: chọn nhà cung cấp (Claude Code, Codex, Antigravity, OpenCode), model, effort, quyền,
  vai trò — không còn phải điền lệnh và cờ CLI. Form đầy đủ vẫn ở nút *Nâng cao…* (cho Gemini, Aider, lệnh riêng).

## 0.5.4 — 15/10/2026

- **Chạy lệnh terminal trong app**: gõ `!yarn dev` (hoặc `/sh …`) — lệnh chạy trong thư mục dự án, output trực
  tiếp ở tab mới **💻 Terminal** (Ctrl+T xoay vòng ba tab): danh sách lệnh với trạng thái, thời gian, port phát
  hiện được (`:3000` + link), nút Dừng / Chạy lại / Xoá, nhiều lệnh song song. Gõ `!` để xem gợi ý: lệnh gần
  đây, script `package.json` (đúng pnpm/yarn/bun/npm theo lockfile), target `Makefile`. `/stop [số]`, `/term`.
  Thoát app dừng mọi lệnh đang chạy (không để lại dev server mồ côi).
- **`/update`** (và `ateam update`): kiểm tra phiên bản mới trên trang docs, có bản mới thì chạy lệnh cài một
  dòng (`get.sh`) ngay trong app, in tiến trình vào log hệ thống, xong nhắc thoát rồi mở lại. Bản cài từ mã
  nguồn (`pip install -e`) không bị ghi đè mà được chỉ dẫn `git pull`.
- **`/usage` hỏi hạn mức thật từ từng CLI** (song song, kết quả hiện khi xong): Claude Code `claude -p /usage`,
  Antigravity `agy -p /usage`, OpenCode `opencode stats --days 7`, Codex đọc `rate_limits` trong file phiên gần
  nhất. Khoá cấu hình mới `usage_command` theo agent; `ateam usage --local` chỉ in thống kê của ateam.

## 0.5.3 — 15/10/2026

- Cấu hình chung nâng lên bản 5: lần mở đầu tiên sau khi nâng cấp, `~/.config/ateam/config.toml` được sao lưu
  (`config.v4.….bak.toml`) và thay bằng file mặc định mới (effort codex mới); lựa chọn trong `state.json` và
  `custom.toml` giữ nguyên.
- **Sửa: danh sách model của Codex sai** (`gpt-5.5` báo lỗi *not supported when using Codex with a
  ChatGPT account*). ateam giờ hỏi danh sách thật bằng `codex debug models` (JSON, bỏ model ẩn) ở màn
  hình thiết lập / `/models codex làm mới`; danh mục dự phòng đổi sang `gpt-6.1-sol`, `gpt-6-astra`,
  `gpt-6-sol`, `gpt-6-luna`, `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`; effort `low…max, ultra`
  (bỏ `minimal`). Model đang chọn không còn trong danh sách thì được nhắc chọn lại.
- **Log dễ đọc hơn** (cột log và ô agent ở tab Đội): tiêu đề mỗi lượt chạy tô màu; header và prompt mà
  Codex in lại được làm mờ/ẩn; lỗi JSON của CLI rút gọn thành `✗ Lỗi: …` (không lặp); `SUMMARY:`,
  `<<<NOTE>>>`, `<<<DELEGATE>>>` hiện thành *Tóm tắt*, *Ghi chú*, *Giao cho …*; `**đậm**`, `` `code` ``,
  gạch đầu dòng; log hệ thống tô theo biểu tượng ✓ ✗ ⚠. File log trên đĩa giữ nguyên.
- **`/task`**: gõ `/task ` hiện danh sách agent (model · effort · vai trò), gõ để lọc, Tab/Enter chọn.
  Prompt gửi agent giờ **đúng nguyên văn** bạn gõ, không còn bọc vai trò và luật DELEGATE/NOTE/SUMMARY.
- **Sửa: gõ tiếng Việt bằng OpenKey trong ô nhập bị mất chữ** ("xin chào" thành "xin cà", "việt" thành
  "iệt"). OpenKey gửi ký tự mồi U+202F trước khi xoá chữ cũ và tính nó vào số Backspace; Textual bỏ qua
  ký tự này nên Backspace thừa xoá mất một chữ thật. Ô nhập giờ ghi nhận ký tự mồi và nuốt đúng Backspace đi kèm.
  Thêm nữa, khi gõ nhanh bộ gõ bắn Backspace và chữ mới liền một lượt; Backspace trước đây đi vòng qua
  phím tắt của app nên chạy *sau* chữ mới và xoá luôn chữ vừa gõ ("tôi muốn" thành "to mun", lúc bị lúc
  không). Backspace/Delete giờ được ô nhập xử lý ngay, đúng thứ tự.
- **Thiết lập đội: sửa vai trò và chọn workflow mặc định** (`/setup`). Cột *Vai trò* giờ là ô nhập sửa được
  (lưu ở `state.json`, chỉ khi khác file cấu hình); hàng mới *⚙ Workflow mặc định*: chọn một workflow thì gõ
  mục tiêu là chạy theo workflow đó (ô nhập ghi rõ đang dùng workflow nào), không cần `/flow`. Lệnh mới
  `/goal <mục tiêu>` luôn để trưởng nhóm lập kế hoạch. `ateam goal` trên dòng lệnh không đổi.
- **Màn hình xem diff kiểu VS Code** (Ctrl+D, `/diff N`) thay cho việc in `git diff` thô vào cột log:
  danh sách file bên trái (trạng thái M/A/D/R, +/−), diff từng file bên phải có số dòng, tô màu cú pháp,
  nền xanh/đỏ cho dòng thêm/xoá và tô đậm đúng từ bị đổi. Mặc định hai cột (cũ | mới), `s` đổi một cột
  (terminal < 120 cột tự dùng một cột); `]` `[` nhảy giữa các đoạn đổi; `o` mở file trong VS Code bằng
  `code --diff`; Ctrl+Y merge ngay từ màn hình diff. Chế độ shared hiện cả file mới chưa track.
- **Kế hoạch dễ đọc và dễ duyệt hơn**: trong log, JSON kế hoạch / review của trưởng nhóm (kể cả khối
  ```` ```json ```` nhiều dòng) hiện thành danh sách *📋 Kế hoạch: N task* — mỗi task một dòng `#id agent@effort
  tiêu đề ⟵ sau #…` kèm đoạn đầu nội dung; review hiện *🔎 Review* + tóm tắt + việc giao thêm. Khung
  **Duyệt kế hoạch** có thêm ô chi tiết: ↑↓ chọn task nào thì thấy toàn bộ nội dung, agent, model · effort,
  phụ thuộc của task đó trước khi duyệt; mục tiêu hiện đủ (tới 300 ký tự).
- **Dọn bảng việc**: nút *🗑 Dọn N task đã xong* phía trên bảng (chỉ hiện khi có gì để dọn) và lệnh `/clear`
  xoá task xong/lỗi/huỷ/bị chặn của mục tiêu đã kết thúc (hoặc giao tay), mục tiêu đã kết thúc, cùng file log;
  task còn được task khác chờ thì giữ lại. Thống kê `/usage` không đổi.
- Trạng thái **đang chạy** (task, spinner, đồng hồ, thanh timeline, mục tiêu đang lập kế hoạch/review)
  đổi từ tím (magenta) sang **xanh dương**: Terminal.app vẽ magenta gần như đỏ, dễ nhầm với lỗi.

## 0.5.2 — 14/10/2026

- Cấu hình chung nâng lên bản 4: lần mở đầu tiên sau khi nâng cấp, `~/.config/ateam/config.toml` được
  sao lưu (`config.v3.….bak.toml`) và thay bằng file mặc định mới; lựa chọn trong `state.json` và
  `custom.toml` giữ nguyên.
- **Sửa: gõ tiếng Việt trong ô nhập bị lỗi font** (dấu rời khỏi chữ, sót dấu khi bộ gõ sửa chữ). Bộ gõ
  để bảng mã Unicode tổ hợp gửi chữ và dấu thành các ký tự riêng; terminal vẽ dấu lệch, còn Backspace của
  bộ gõ chỉ xoá một ký tự nên dấu cũ sót lại. Mọi ô nhập giờ gộp chữ về dạng dựng sẵn (NFC) và
  Backspace/Delete xoá trọn một chữ cùng dấu của nó.
- **Khung Duyệt kế hoạch**: khi trưởng nhóm (hoặc workflow, hoặc vòng review) có kế hoạch nháp, một khung
  viền vàng hiện ngay trên ô nhập ở cả tab Bảng việc và Đội, liệt kê từng task (agent, effort, tiêu đề,
  phụ thuộc) với nút *Duyệt & chạy*, *Sửa task*, *Đổi agent*, *Bỏ kế hoạch*. Kế hoạch mới tới thì con
  trỏ nhảy vào nút duyệt (Enter là chạy) nếu bạn không đang gõ dở; Esc quay về ô nhập.
- Ctrl+G duyệt kế hoạch đang hiện trong khung (trước đây duyệt mọi kế hoạch nháp cùng lúc).
- Phím thay thế **F2** (= Ctrl+G, duyệt & chạy) và **F5** (= Ctrl+R, chạy lại): terminal tích hợp của
  VS Code/Cursor trên macOS chặn Ctrl+G (Go to Line) và Ctrl+R (Run Recent Command). Footer và gợi ý
  giờ hiện F2/F5; phím Ctrl cũ vẫn dùng được.
- Lệnh mới `/drop [mục tiêu]`: bỏ kế hoạch nháp, huỷ mọi task nháp của nó.
- **Sửa: mọi task của Codex lỗi ngay** với `error: unexpected argument '--full-auto' found` — Codex 0.152
  đã bỏ cờ này. Lệnh mặc định đổi sang `codex exec --sandbox workspace-write` (cũng chạy trên bản Codex
  cũ). Cấu hình cũ còn `--full-auto` được tự đổi khi đọc; cấu hình chung nâng lên bản 4.
- `ateam doctor` so từng cờ trong `command` với `<lệnh> --help` (vd `codex exec --help`) và báo cờ
  CLI không còn nhận. Task lỗi vì CLI không nhận cờ thì thông báo lỗi nhắc chạy `ateam doctor`.
- **Sửa lỗi** `Lỗi: not enough values to unpack (expected at least 2, got 0)` khi gõ `/se` (hoặc `/set`)
  rồi Enter: danh sách gợi ý chèn `/set `, Enter lần nữa chạy `/set` không có tham số. Giờ gõ đủ tên một
  lệnh bắt buộc tham số rồi Enter chỉ chèn dấu cách chờ gõ tiếp; lệnh thiếu/sai tham số (`/set`, `/assign 3`,
  `/retry abc`, …) hiện cách dùng kèm gợi ý lệnh cùng tiền tố (`/set` → *hay ý bạn là /setup?*) thay vì lỗi.
- **`/compact [trọng tâm]`** (và `ateam compact`): trưởng nhóm tóm tắt ghi chú chung, mục tiêu gần đây và
  log hệ thống thành một ghi chú ngắn; prompt gửi agent về sau chỉ mang bản tóm tắt này cùng ghi chú mới
  hơn, thay vì cả chuỗi ghi chú cũ.
- **Tab Đội không còn bị trôi khi cuộn**: log của từng agent tự xuống dòng theo bề rộng ô (trước đây
  ô hẹp hơn 78 cột thì sinh thanh cuộn ngang, chữ bị cắt và vuốt trackpad làm log trôi ngang); màn hình,
  tab và lưới ô agent bị khoá không cuộn, chỉ log trong từng ô cuộn. Output agent được lọc thêm ký tự
  điều khiển C1 (U+0080–U+009F) và DEL, vốn có thể làm terminal xuống dòng/cuộn ngược và đẩy lệch TUI.

## 0.5.1 — 14/10/2026

- **Gõ `/` ở đầu ô nhập** hiện danh sách lệnh kèm tham số và mô tả, gõ tiếp để lọc; Tab chèn lệnh,
  Enter chạy luôn với lệnh không cần tham số. Gõ sai lệnh thì gợi ý lệnh gần nhất (`/stup` → `/setup`).
- **Trợ giúp trong bảng nổi** (`F1` hoặc `/help`): lệnh tô màu theo mục, đủ rộng để không bị gãy dòng
  như khi in vào cột log. Lần đầu mở app chỉ in phần *bắt đầu nhanh* thay vì toàn bộ trợ giúp.
- Bảng việc trống có hướng dẫn cách giao việc; mục tiêu chờ duyệt nhắc Ctrl+G; mục tiêu đang lập kế
  hoạch/review có spinner; cột trạng thái có biểu tượng (✓ ✗ ✎ ◆ …, spinner khi đang chạy).
- Thanh agent chỉ xuống dòng giữa các agent (không cắt đôi "(mặc định)"); terminal hẹp (< 140 cột) nới
  cột bảng việc để cột *Task* không bị đẩy mất; ô agent ở tab Đội gọn hơn (token ước tính xem ở `/usage`).
- Form workflow: tiêu đề cột thẳng hàng với ô nhập, ô chọn agent không còn bị gãy thành 2 dòng.

## 0.5.0 — 14/10/2026

- Thêm **agent và workflow tuỳ chỉnh**: `/custom` (hoặc nút *Agent & workflow tuỳ chỉnh…* ở màn hình
  thiết lập) mở màn hình quản lý cùng kiểu màn hình thiết lập. Form thêm agent có mẫu (claude, codex,
  agy, opencode, Gemini CLI, Aider, trống), các ô lệnh/vai trò/model/effort/cú pháp `@file`/dự phòng và
  dòng xem trước lệnh thật. Agent mới vào đội ngay, không cần mở lại app.
- Workflow = chuỗi bước dựng sẵn (agent, tiêu đề, prompt có `{goal}`, chạy sau bước nào, effort riêng),
  chạy bằng `/flow <tên> <mục tiêu>` hoặc `ateam flow <tên> <mục tiêu>` mà không cần trưởng nhóm lập kế
  hoạch; có mẫu tính năng mới, sửa lỗi, review code. `ateam flows` / `/flow` liệt kê.
- Lưu ở `~/.config/ateam/custom.toml` (khoá `[agents.*]`, `[workflows.*]` dùng được cả trong file cấu
  hình); file này không bị thay khi `config.toml` nâng cấp. DB thêm cột `goals.workflow`.

- Thêm màn hình **Thiết lập đội AI** khi mở app lần đầu (mở lại: `/setup` hoặc `ateam setup`): chọn
  agent nào tham gia, trưởng nhóm, model và effort từng agent trong một màn hình; Ctrl+S lưu, Esc bỏ
  qua. Trước khi hiện form, ateam hỏi **song song** các CLI có lệnh liệt kê model (`opencode models`,
  `agy models`, tối đa 20 giây) để bảng chọn có sẵn model thật; lỗi hoặc hết giờ thì dùng danh mục có sẵn.
- Lựa chọn lưu ở `state.json` (`agents.<tên>.enabled`, `lead`, `onboarded`); chỉ ghi giá trị khác file
  cấu hình, nên sửa file vẫn có tác dụng.
- `ateam models --refresh` và lần hỏi model khi mở app giờ chạy song song.
- **Dán ảnh** vào ô nhập bằng **Ctrl+V** (macOS: `osascript`/`pngpaste`; Linux: `wl-paste`/`xclip`):
  ảnh lưu ở `.ateam/images/` và được chèn dạng `@ảnh`; kéo-thả file ảnh vào terminal cũng thành `@ảnh`.
  Mỗi agent nhận ảnh theo CLI của nó: Codex thêm cờ `--image=…`, OpenCode `-f`, Claude/agy `@ảnh`.
  Khoá mới `image_args` theo agent. Ảnh trong `.ateam/` (không có ở worktree) được truyền bằng đường dẫn tuyệt đối.

## 0.4.0 — 14/10/2026

- Gõ `@` trong ô nhập để chọn file/thư mục của dự án (lọc khi gõ, ↑↓ chọn, Tab/Enter chèn, Esc đóng).
  Khi chạy, `@đường/dẫn` được đổi sang cú pháp của từng agent: `@path` cho Claude Code và agy, đường
  dẫn thường cho Codex, đường dẫn + `-f path` cho OpenCode. Khoá mới `file_ref`/`file_args` theo agent
  để tự chỉnh; `ateam doctor` và `/agents` in cú pháp đang dùng.
- Thêm: xem model và effort mỗi agent hỗ trợ. Tab Đội hiện danh sách ngay trong ô từng agent (mục đang
  dùng tô đậm); `/model <agent>` và `/effort <agent>` (không kèm giá trị) hoặc bấm vào tiêu đề ô agent
  mở bảng chọn; lựa chọn được lưu và đi thẳng vào cờ CLI như `/model <agent> <tên>`.
- Thêm `/models [agent]`, `ateam models [agent] [--refresh]`. Danh mục model/effort có sẵn cho
  claude, codex, agy, opencode; với `opencode models` / `agy models`, ateam hỏi CLI danh sách thật
  (lần đầu mở app, hoặc `/models <agent> làm mới`) và lưu vào `state.json`.
- Khoá cấu hình mới (không bắt buộc): `models`, `models_command`, `models_filter`.
- Trang docs: thêm khối `previews` vào `wrangler.jsonc` để Workers Builds dựng được bản xem trước cho
  nhánh PR.

## 0.3.1 — 14/10/2026

- Sửa: phím tắt Ctrl+D, Ctrl+K… không có tác dụng khi con trỏ đang ở ô nhập (mặc định khi mở app) —
  ô nhập của Textual nuốt phím. Các phím tắt của app giờ có `priority=True`.
- Sửa: `ateam merge` (dòng lệnh) thất bại trên máy chưa cấu hình git identity vì không chạy bước
  setup; identity dự phòng `ateam <ateam@localhost>` giờ được kiểm tra ngay trước mỗi commit/merge.
- Thêm bộ test tự động (19 test, agent giả lập trong `tests/fakebin`) và CI GitHub Actions
  (Ubuntu + macOS, Python 3.9 và 3.13).
- Thêm tài liệu cho người phát triển và AI agent: `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `docs/`.
- Bỏ hàm thừa `runner.build_argv`.

## 0.3.0 — 14/10/2026

- Tự kiểm tra sau mỗi task: `[verify]`, `/verify <lệnh>`; test fail thì giao sửa kèm log (tối đa
  `max_fix_attempts`), bỏ qua khi task không đổi file.
- Chế độ worktree `merge = "review"`: task dừng ở "chờ duyệt"; `/diff` (Ctrl+D), `/merge` (Ctrl+Y),
  `/reject <task> [góp ý]`; CLI `ateam diff|merge|reject`.
- Hạn mức: nhận diện thông báo rate limit/usage limit, tạm nghỉ đến giờ hồi, chuyển task sang
  `fallback`, trưởng nhóm dự phòng `lead_fallback`; `/usage`, `/cooldown`, `ateam usage|cooldown`.
- Bảng `runs` thống kê lượt chạy; cột task `base`, `head`, `attempts`.
- Cấu hình lên `config_version = 3` (file cũ được sao lưu và thay).
- Trang docs + gói tải trên Cloudflare Workers; cài một lệnh qua `scripts/get.sh`.

## 0.2.0 — 14/10/2026

- Tab "Đội" (Ctrl+T): ô log trực tiếp cho từng agent, task đang chạy, thời gian, cảnh báo im lặng,
  timeline Gantt.
- Model và effort theo agent (`/model`, `/effort`, `ateam set`, lưu ở `state.json`) và theo task
  (`/task agent:model@effort`, `/set`); trưởng nhóm tự chọn effort (`lead_sets_effort`).
- Cấu hình `config_version = 2` với `model_args`/`effort_args`/`efforts`; agy chạy với
  `--mode accept-edits --print-timeout 0`; grok dùng `opencode run` + `model`.

## 0.1.0 — 14/10/2026

- Bản đầu: TUI Textual, bảng việc SQLite, trưởng nhóm lập kế hoạch/review, phụ thuộc, giao việc chéo
  (`<<<DELEGATE>>>`), ghi chú (`<<<NOTE>>>`), chế độ shared/worktree, CLI headless, `install.sh`.
