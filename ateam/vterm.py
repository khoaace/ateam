"""Bộ giả lập terminal VT100/xterm thuần Python cho tab 🔲 Lưới của TUI (không thêm dependency).

`Screen.feed(bytes)` nhận output thô của CLI trong pty và giữ lưới ô chữ + kiểu (màu 16/256/truecolor, đậm,
nghiêng, gạch chân, đảo màu…), con trỏ, vùng cuộn, màn hình phụ (alt screen của CLI toàn màn hình), lịch sử cuộn
của màn hình chính. Truy vấn của CLI (vị trí con trỏ, thuộc tính thiết bị) được trả lời qua `reply` — crossterm
(Codex) và Ink (Claude Code) hỏi trước khi vẽ. Đủ cho các CLI agent; không nhằm thay một terminal đầy đủ.

`keys.encode(key, character, app_cursor)` đổi tên phím của Textual sang byte gửi vào pty."""

from __future__ import annotations

import codecs
import unicodedata
from typing import Callable

# Kiểu một ô: (fg, bg, bold, dim, italic, underline, reverse, strike, hidden). Màu: None = mặc định,
# int 0..255 = bảng màu xterm, "#rrggbb" = truecolor
Attr = tuple
DEFAULT: Attr = (None, None, False, False, False, False, False, False, False)
BLANK = (" ", DEFAULT)
HISTORY_MAX = 3000

# DEC Special Graphics (ESC ( 0): vẽ khung bằng chữ cái
DEC_GRAPHICS = {
    "j": "┘", "k": "┐", "l": "┌", "m": "└", "n": "┼", "q": "─", "t": "├", "u": "┤", "v": "┴", "w": "┬",
    "x": "│", "a": "▒", "`": "◆", "f": "°", "g": "±", "o": "⎺", "s": "⎽", "y": "≤", "z": "≥", "~": "·",
}


def char_width(ch: str) -> int:
    """Độ rộng hiển thị: 2 cho chữ Đông Á / emoji rộng, 0 cho dấu kết hợp, 1 còn lại."""
    o = ord(ch)
    if o < 0x300:
        return 1
    if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf") or 0xFE00 <= o <= 0xFE0F:
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F") or 0x1F300 <= o <= 0x1FAFF:
        return 2
    return 1


class Screen:
    def __init__(self, rows: int = 24, cols: int = 80, reply: Callable[[bytes], None] | None = None):
        self.rows, self.cols = max(1, rows), max(2, cols)
        self.reply = reply or (lambda b: None)
        self.history: list[list] = []
        self._dec = codecs.getincrementaldecoder("utf-8")("replace")
        self.reset()

    # ---- trạng thái
    def reset(self) -> None:
        self.main = [self._blank_line() for _ in range(self.rows)]
        self.alt = None             # màn hình phụ khi CLI bật ?1049
        self.lines = self.main
        self.x = self.y = 0
        self.attr: Attr = DEFAULT
        self.wrap_pending = False
        self.top, self.bottom = 0, self.rows - 1
        self.saved = (0, 0, DEFAULT)
        self.cursor_visible = True
        self.app_cursor = False     # ?1: phím mũi tên gửi ESC O A
        self.bracketed_paste = False
        self.autowrap = True
        self.charset_g0 = "B"
        self.title = ""
        self.version = 0            # tăng mỗi lần màn hình đổi (widget biết khi nào cần vẽ lại)
        self._state = "ground"
        self._buf = ""

    def _blank_line(self) -> list:
        return [BLANK] * self.cols

    @property
    def in_alt(self) -> bool:
        return self.alt is not None and self.lines is self.alt

    def text(self) -> str:
        """Chữ trên màn hình (bỏ khoảng trắng cuối dòng) — dùng cho test và chép."""
        return "\n".join("".join(c[0] for c in line).rstrip() for line in self.lines)

    def resize(self, rows: int, cols: int) -> None:
        rows, cols = max(1, rows), max(2, cols)
        if (rows, cols) == (self.rows, self.cols):
            return
        for buf_name in ("main", "alt"):
            buf = getattr(self, buf_name)
            if buf is None:
                continue
            for i, line in enumerate(buf):
                buf[i] = (line + [BLANK] * (cols - len(line)))[:cols]
            if rows < len(buf):
                # bớt dòng: bỏ dòng trên (vào lịch sử) nếu con trỏ ở thấp, không thì bỏ dòng trống dưới cùng
                extra = len(buf) - rows
                cut_top = min(extra, max(0, self.y - rows + 1)) if buf is self.lines else 0
                if buf_name == "main":
                    self.history.extend(buf[:cut_top])
                del buf[:cut_top]
                del buf[rows:]
                if buf is self.lines:
                    self.y -= cut_top
            while len(buf) < rows:
                buf.append([BLANK] * cols)
        self.history = [(line + [BLANK] * (cols - len(line)))[:cols] for line in self.history[-HISTORY_MAX:]]
        self.rows, self.cols = rows, cols
        self.top, self.bottom = 0, rows - 1
        self.x, self.y = min(self.x, cols - 1), min(max(self.y, 0), rows - 1)
        self.wrap_pending = False
        self.version += 1

    # ---- nhận byte
    def feed(self, data: bytes) -> None:
        s = self._dec.decode(data)
        if not s:
            return
        i, n = 0, len(s)
        while i < n:
            ch = s[i]
            st = self._state
            if st == "ground":
                # đoạn chữ thường liền nhau: in một lượt
                j = i
                while j < n and s[j] >= " " and s[j] != "\x7f":
                    j += 1
                if j > i:
                    self._print(s[i:j])
                    i = j
                    continue
                self._control(ch)
            elif st == "esc":
                self._esc(ch)
            elif st == "csi":
                if "@" <= ch <= "~":
                    self._state = "ground"
                    self._csi(self._buf, ch)
                elif ch == "\x1b":
                    self._state = "esc"
                elif ch in "\x18\x1a":
                    self._state = "ground"
                elif len(self._buf) < 256:
                    self._buf += ch
            elif st in ("osc", "str"):  # OSC / DCS / APC / PM / SOS: tới BEL hoặc ESC \
                if ch == "\x07" or (ch == "\\" and self._buf.endswith("\x1b")):
                    if st == "osc":
                        self._osc(self._buf.rstrip("\x1b"))
                    self._state = "ground"
                elif len(self._buf) < 4096:
                    self._buf += ch
            elif st == "charset":
                if self._buf == "(":
                    self.charset_g0 = ch
                self._state = "ground"
            elif st == "skip1":
                self._state = "ground"
            i += 1
        self.version += 1

    def _control(self, ch: str) -> None:
        if ch == "\x1b":
            self._state, self._buf = "esc", ""
        elif ch == "\r":
            self.x, self.wrap_pending = 0, False
        elif ch in "\n\x0b\x0c":
            self._linefeed()
        elif ch == "\x08":
            if self.x > 0:
                self.x -= 1
            self.wrap_pending = False
        elif ch == "\t":
            self.x = min(self.cols - 1, (self.x // 8 + 1) * 8)
            self.wrap_pending = False
        # BEL, SO/SI, NUL, DEL: bỏ qua

    def _esc(self, ch: str) -> None:
        self._state = "ground"
        if ch == "[":
            self._state, self._buf = "csi", ""
        elif ch == "]":
            self._state, self._buf = "osc", ""
        elif ch in "P_^X":
            self._state, self._buf = "str", ""
        elif ch in "()*+":
            self._state, self._buf = "charset", ch
        elif ch in "#% ":
            self._state = "skip1"
        elif ch == "7":
            self.saved = (self.x, self.y, self.attr)
        elif ch == "8":
            self.x, self.y, self.attr = self.saved
            self.wrap_pending = False
        elif ch == "D":
            self._linefeed()
        elif ch == "E":
            self.x = 0
            self._linefeed()
        elif ch == "M":
            self._reverse_index()
        elif ch == "c":
            rows, cols, hist = self.rows, self.cols, self.history
            self.reset()
            self.rows, self.cols, self.history = rows, cols, hist
        # ESC = / ESC > (bàn phím số), ESC \ lạc: bỏ qua

    def _osc(self, body: str) -> None:
        code, _, rest = body.partition(";")
        if code in ("0", "2"):
            self.title = rest[:200]

    # ---- in chữ
    def _print(self, s: str) -> None:
        if self.charset_g0 == "0":
            s = "".join(DEC_GRAPHICS.get(c, c) for c in s)
        lines, cols = self.lines, self.cols
        for ch in s:
            w = char_width(ch)
            if w == 0:  # dấu kết hợp: gắn vào ô trước
                px = self.x - 1 if not self.wrap_pending else self.x
                if 0 <= px < cols:
                    c, a = lines[self.y][px]
                    if c:
                        lines[self.y][px] = (c + ch, a)
                continue
            if self.wrap_pending:
                if self.autowrap:
                    self.x = 0
                    self._linefeed()
                self.wrap_pending = False
            if w == 2 and self.x == cols - 1:
                if self.autowrap:
                    lines[self.y][self.x] = (" ", self.attr)
                    self.x = 0
                    self._linefeed()
                else:
                    continue
            row = lines[self.y]
            if row[self.x][0] == "" and self.x > 0:  # ghi đè nửa sau chữ rộng
                row[self.x - 1] = (" ", row[self.x - 1][1])
            if w == 1 and self.x + 1 < cols and row[self.x + 1][0] == "":  # ghi đè nửa đầu chữ rộng
                row[self.x + 1] = (" ", row[self.x + 1][1])
            row[self.x] = (ch, self.attr)
            if w == 2:
                row[self.x + 1] = ("", self.attr)
            if self.x + w >= cols:
                self.x = cols - 1
                self.wrap_pending = True
            else:
                self.x += w

    def _linefeed(self) -> None:
        self.wrap_pending = False
        if self.y == self.bottom:
            self._scroll_up(1)
        elif self.y < self.rows - 1:
            self.y += 1

    def _reverse_index(self) -> None:
        if self.y == self.top:
            self._scroll_down(1)
        elif self.y > 0:
            self.y -= 1

    def _scroll_up(self, n: int) -> None:
        n = max(1, min(n, self.bottom - self.top + 1))
        region = self.lines[self.top:self.bottom + 1]
        if self.top == 0 and not self.in_alt:
            self.history.extend(region[:n])
            if len(self.history) > HISTORY_MAX:
                del self.history[:len(self.history) - HISTORY_MAX]
        blank = [(" ", self._bg_attr())] * self.cols
        self.lines[self.top:self.bottom + 1] = region[n:] + [list(blank) for _ in range(n)]

    def _scroll_down(self, n: int) -> None:
        n = max(1, min(n, self.bottom - self.top + 1))
        region = self.lines[self.top:self.bottom + 1]
        blank = [(" ", self._bg_attr())] * self.cols
        self.lines[self.top:self.bottom + 1] = [list(blank) for _ in range(n)] + region[:-n]

    def _bg_attr(self) -> Attr:
        """Ô bị xoá giữ màu nền hiện tại (như xterm)."""
        return DEFAULT if self.attr[1] is None else (None, self.attr[1]) + DEFAULT[2:]

    # ---- CSI
    def _csi(self, raw: str, final: str) -> None:
        prefix = ""
        if raw and raw[0] in "?<=>":
            prefix, raw = raw[0], raw[1:]
        inter = ""
        while raw and raw[-1] in " !\"#$%&'()*+,-./":
            inter = raw[-1] + inter
            raw = raw[:-1]
        if inter:
            return  # DECSCUSR (kiểu con trỏ), DECRQM…: bỏ qua
        params: list = []
        for part in raw.split(";") if raw else []:
            sub = part.split(":")
            try:
                vals = [int(x) if x else 0 for x in sub]
            except ValueError:
                return
            params.append(vals if len(vals) > 1 else vals[0])

        def p(i: int, default: int = 1) -> int:
            v = params[i] if i < len(params) else 0
            if isinstance(v, list):
                v = v[0]
            return v if v else default

        if prefix == "?" and final in "hl":
            self._dec_mode([x if isinstance(x, int) else x[0] for x in params], final == "h")
            return
        if prefix and final not in "cnm":
            return  # CSI > … (xterm modifyOtherKeys…), CSI ? u (hỏi bàn phím kitty): không hỗ trợ, không trả lời
        if final == "m":
            if prefix:
                return
            self._sgr(params)
            return
        if final not in "cnt":
            self.wrap_pending = False
        if final in "Hf":
            self.y = self._clamp_y(p(0) - 1)
            self.x = min(p(1) - 1, self.cols - 1)
        elif final == "A":
            self.y = max(self.top if self.y >= self.top else 0, self.y - p(0))
        elif final in "Be":
            self.y = min(self.bottom if self.y <= self.bottom else self.rows - 1, self.y + p(0))
        elif final in "Ca":
            self.x = min(self.cols - 1, self.x + p(0))
        elif final == "D":
            self.x = max(0, self.x - p(0))
        elif final == "E":
            self.y = min(self.bottom, self.y + p(0))
            self.x = 0
        elif final == "F":
            self.y = max(self.top, self.y - p(0))
            self.x = 0
        elif final in "G`":
            self.x = min(p(0) - 1, self.cols - 1)
        elif final == "d":
            self.y = self._clamp_y(p(0) - 1)
        elif final == "J":
            self._erase_display(p(0, 0))
        elif final == "K":
            self._erase_line(p(0, 0))
        elif final == "X":
            n = min(p(0), self.cols - self.x)
            self.lines[self.y][self.x:self.x + n] = [(" ", self._bg_attr())] * n
        elif final == "@":
            n = min(p(0), self.cols - self.x)
            row = self.lines[self.y]
            row[self.x:self.x] = [(" ", self._bg_attr())] * n
            del row[self.cols:]
        elif final == "P":
            n = min(p(0), self.cols - self.x)
            row = self.lines[self.y]
            del row[self.x:self.x + n]
            row.extend([(" ", self._bg_attr())] * n)
        elif final == "L":
            if self.top <= self.y <= self.bottom:
                saved = self.top
                self.top = self.y
                self._scroll_down(p(0))
                self.top = saved
                self.x = 0
        elif final == "M":
            if self.top <= self.y <= self.bottom:
                saved = self.top
                self.top = self.y
                n = max(1, min(p(0), self.bottom - self.top + 1))
                region = self.lines[self.top:self.bottom + 1]
                blank = [(" ", self._bg_attr())] * self.cols
                self.lines[self.top:self.bottom + 1] = region[n:] + [list(blank) for _ in range(n)]
                self.top = saved
                self.x = 0
        elif final == "S":
            self._scroll_up_region(p(0))
        elif final == "T":
            self._scroll_down(p(0))
        elif final == "r":
            top, bottom = p(0) - 1, (p(1, self.rows)) - 1
            if 0 <= top < bottom < self.rows:
                self.top, self.bottom = top, bottom
            else:
                self.top, self.bottom = 0, self.rows - 1
            self.x, self.y = 0, 0
        elif final == "s":
            self.saved = (self.x, self.y, self.attr)
        elif final == "u":
            self.x, self.y, self.attr = self.saved
        elif final == "b":  # REP: lặp chữ trước
            prev = self.lines[self.y][self.x - 1][0] if self.x > 0 else " "
            self._print((prev or " ") * min(p(0), self.cols))
        elif final == "I":
            for _ in range(p(0)):
                self.x = min(self.cols - 1, (self.x // 8 + 1) * 8)
        elif final == "Z":
            for _ in range(p(0)):
                self.x = max(0, (self.x - 1) // 8 * 8)
        elif final == "n":
            if p(0, 0) == 6:
                self.reply(f"\x1b[{prefix}{self.y + 1};{self.x + 1}R".encode())
            elif p(0, 0) == 5:
                self.reply(b"\x1b[0n")
        elif final == "c":
            if prefix == ">":
                self.reply(b"\x1b[>0;10;1c")
            elif not prefix and p(0, 0) == 0:
                self.reply(b"\x1b[?62;22c")
        elif final == "t":
            if p(0, 0) == 18:
                self.reply(f"\x1b[8;{self.rows};{self.cols}t".encode())

    def _scroll_up_region(self, n: int) -> None:
        self._scroll_up(n)

    def _clamp_y(self, y: int) -> int:
        return min(max(0, y), self.rows - 1)

    def _erase_display(self, mode: int) -> None:
        a = self._bg_attr()
        if mode == 0:
            self._erase_line(0)
            for r in range(self.y + 1, self.rows):
                self.lines[r] = [(" ", a)] * self.cols
        elif mode == 1:
            self._erase_line(1)
            for r in range(0, self.y):
                self.lines[r] = [(" ", a)] * self.cols
        elif mode in (2, 3):
            if mode == 3:
                self.history.clear()
            for r in range(self.rows):
                self.lines[r] = [(" ", a)] * self.cols

    def _erase_line(self, mode: int) -> None:
        a = self._bg_attr()
        row = self.lines[self.y]
        if mode == 0:
            row[self.x:] = [(" ", a)] * (self.cols - self.x)
        elif mode == 1:
            row[:self.x + 1] = [(" ", a)] * (self.x + 1)
        else:
            self.lines[self.y] = [(" ", a)] * self.cols

    def _dec_mode(self, modes: list, on: bool) -> None:
        for m in modes:
            if m == 1:
                self.app_cursor = on
            elif m == 7:
                self.autowrap = on
            elif m == 25:
                self.cursor_visible = on
            elif m == 2004:
                self.bracketed_paste = on
            elif m in (47, 1047, 1049):
                if on and not self.in_alt:
                    if m == 1049:
                        self.saved = (self.x, self.y, self.attr)
                    self.alt = [self._blank_line() for _ in range(self.rows)]
                    self.lines = self.alt
                    self.top, self.bottom = 0, self.rows - 1
                elif not on and self.in_alt:
                    self.lines = self.main
                    self.alt = None
                    self.top, self.bottom = 0, self.rows - 1
                    if m == 1049:
                        self.x, self.y, self.attr = self.saved
                self.wrap_pending = False
            # chuột (1000/1002/1003/1006), focus (1004)…: bỏ qua

    def _sgr(self, params: list) -> None:
        if not params:
            params = [0]
        fg, bg, bold, dim, italic, under, rev, strike, hidden = self.attr
        i = 0
        while i < len(params):
            v = params[i]
            if isinstance(v, list):  # dạng dấu hai chấm: 38:2::r:g:b, 4:3
                code, rest = v[0], v[1:]
                if code in (38, 48, 58):
                    col = None
                    if rest and rest[0] == 5 and len(rest) > 1:
                        col = rest[1] & 255
                    elif rest and rest[0] == 2 and len(rest) >= 4:
                        rgb = rest[-3:]
                        col = "#%02x%02x%02x" % tuple(x & 255 for x in rgb)
                    if code == 38:
                        fg = col
                    elif code == 48:
                        bg = col
                elif code == 4:
                    under = bool(rest and rest[0])
                i += 1
                continue
            if v == 0:
                fg, bg, bold, dim, italic, under, rev, strike, hidden = DEFAULT
            elif v == 1:
                bold = True
            elif v == 2:
                dim = True
            elif v == 3:
                italic = True
            elif v == 4:
                under = True
            elif v == 7:
                rev = True
            elif v == 8:
                hidden = True
            elif v == 9:
                strike = True
            elif v == 22:
                bold = dim = False
            elif v == 23:
                italic = False
            elif v == 24:
                under = False
            elif v == 27:
                rev = False
            elif v == 28:
                hidden = False
            elif v == 29:
                strike = False
            elif 30 <= v <= 37:
                fg = v - 30
            elif 40 <= v <= 47:
                bg = v - 40
            elif 90 <= v <= 97:
                fg = v - 90 + 8
            elif 100 <= v <= 107:
                bg = v - 100 + 8
            elif v == 39:
                fg = None
            elif v == 49:
                bg = None
            elif v in (38, 48, 58):
                col = None
                mode = params[i + 1] if i + 1 < len(params) else None
                if mode == 5 and i + 2 < len(params):
                    col = params[i + 2] if isinstance(params[i + 2], int) else None
                    col = col & 255 if col is not None else None
                    i += 2
                elif mode == 2 and i + 4 < len(params):
                    rgb = params[i + 2:i + 5]
                    if all(isinstance(x, int) for x in rgb):
                        col = "#%02x%02x%02x" % tuple(x & 255 for x in rgb)
                    i += 4
                if v == 38:
                    fg = col
                elif v == 48:
                    bg = col
            i += 1
        self.attr = (fg, bg, bold, dim, italic, under, rev, strike, hidden)


# ---- phím: tên phím Textual -> byte gửi CLI
_SPECIAL = {
    "enter": "\r", "return": "\r", "tab": "\t", "shift+tab": "\x1b[Z", "backspace": "\x7f",
    "ctrl+h": "\x08", "escape": "\x1b", "delete": "\x1b[3~", "insert": "\x1b[2~",
    "home": "\x1b[H", "end": "\x1b[F", "pageup": "\x1b[5~", "pagedown": "\x1b[6~",
    "f1": "\x1bOP", "f2": "\x1bOQ", "f3": "\x1bOR", "f4": "\x1bOS", "f5": "\x1b[15~", "f6": "\x1b[17~",
    "f7": "\x1b[18~", "f8": "\x1b[19~", "f9": "\x1b[20~", "f10": "\x1b[21~", "f11": "\x1b[23~", "f12": "\x1b[24~",
    "space": " ", "ctrl+space": "\x00", "ctrl+at": "\x00", "shift+enter": "\x1b\r", "alt+enter": "\x1b\r",
    "ctrl+backslash": "\x1c", "ctrl+right_square_bracket": "\x1d", "ctrl+circumflex_accent": "\x1e",
    "ctrl+underscore": "\x1f", "ctrl+left_square_bracket": "\x1b", "shift+backspace": "\x7f",
    "ctrl+backspace": "\x08", "alt+backspace": "\x1b\x7f",
}
_ARROWS = {"up": "A", "down": "B", "right": "C", "left": "D", "home": "H", "end": "F"}
_MODS = {"shift": 2, "alt": 3, "shift+alt": 4, "ctrl": 5, "shift+ctrl": 6, "ctrl+shift": 6, "alt+ctrl": 7,
         "ctrl+alt": 7}


def encode(key: str, character: str | None = None, app_cursor: bool = False) -> bytes:
    """Byte gửi vào pty cho một phím Textual. b"" = không biết phím này."""
    if key in _SPECIAL:
        return _SPECIAL[key].encode()
    mods, _, base = key.rpartition("+")
    if base in _ARROWS:
        if not mods:
            return (("\x1bO" if app_cursor else "\x1b[") + _ARROWS[base]).encode()
        m = _MODS.get(mods)
        if m:
            return f"\x1b[1;{m}{_ARROWS[base]}".encode()
    if mods == "ctrl" and len(base) == 1 and base.isalpha():
        return bytes([ord(base.lower()) - 96])
    if mods == "alt" and character and len(character) == 1:
        return b"\x1b" + character.encode()
    if mods == "alt" and len(base) == 1:
        return b"\x1b" + base.encode()
    if character and (character >= " " or character in "\t\r") and character != "\x7f":
        return character.encode()
    if character and len(character) == 1 and ord(character) < 32:
        return character.encode()
    return b""
