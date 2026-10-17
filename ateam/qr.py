"""Mã QR thuần Python (không thêm dependency) cho `ateam web --tunnel/--host`: quét bằng điện thoại để mở
giao diện kèm token. Byte mode, mức sửa lỗi M, version 1–10 (tới ~210 byte — thừa cho một URL).
Thuật toán theo ISO/IEC 18004 (cách đặt module theo bản tham khảo của Nayuki)."""

from __future__ import annotations

# version -> (số codeword sửa lỗi mỗi khối, [(số khối, số codeword dữ liệu mỗi khối), …]) ở mức M
_BLOCKS = {
    1: (10, [(1, 16)]), 2: (16, [(1, 28)]), 3: (26, [(1, 44)]), 4: (18, [(2, 32)]), 5: (24, [(2, 43)]),
    6: (16, [(4, 27)]), 7: (18, [(4, 31)]), 8: (22, [(2, 38), (2, 39)]), 9: (22, [(3, 36), (2, 37)]),
    10: (26, [(4, 43), (1, 44)]),
}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
          9: [6, 26, 46], 10: [6, 28, 50]}
_ECL_M = 0  # bit mức sửa lỗi trong format info: L=1, M=0, Q=3, H=2


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> list[int]:
    out = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(len(out)):
            out[j] = _gf_mul(out[j], root)
            if j + 1 < len(out):
                out[j] ^= out[j + 1]
        root = _gf_mul(root, 0x02)
    return out


def rs_remainder(data: list[int], degree: int) -> list[int]:
    div = _rs_divisor(degree)
    out = [0] * degree
    for b in data:
        factor = b ^ out.pop(0)
        out.append(0)
        for i, coef in enumerate(div):
            out[i] ^= _gf_mul(coef, factor)
    return out


def _data_capacity(version: int) -> int:
    return sum(n * k for n, k in _BLOCKS[version][1])


def codewords(data: bytes) -> tuple[int, list[list[int]], list[list[int]], list[int]]:
    """(version, các khối dữ liệu, các khối sửa lỗi, chuỗi codeword cuối đã xen kẽ)."""
    for version in range(1, 11):
        cc = 8 if version < 10 else 16
        if 4 + cc + 8 * len(data) <= _data_capacity(version) * 8:
            break
    else:
        raise ValueError("data too long for QR version 10")
    bits: list[int] = []

    def put(val: int, n: int) -> None:
        bits.extend((val >> i) & 1 for i in reversed(range(n)))
    put(0b0100, 4)
    put(len(data), cc)
    for b in data:
        put(b, 8)
    cap = _data_capacity(version) * 8
    put(0, min(4, cap - len(bits)))
    put(0, (-len(bits)) % 8)
    raw = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(raw) < cap // 8:
        raw.append(pad)
        pad ^= 0xEC ^ 0x11
    ec_len, groups = _BLOCKS[version]
    blocks, pos = [], 0
    for n, k in groups:
        for _ in range(n):
            blocks.append(raw[pos:pos + k])
            pos += k
    ecs = [rs_remainder(b, ec_len) for b in blocks]
    out = [b[i] for i in range(max(len(b) for b in blocks)) for b in blocks if i < len(b)]
    out += [e[i] for i in range(ec_len) for e in ecs]
    return version, blocks, ecs, out


class QR:
    def __init__(self, data: str | bytes):
        raw = data.encode("utf-8") if isinstance(data, str) else data
        self.version, _, _, words = codewords(raw)
        self.size = self.version * 4 + 17
        n = self.size
        self.m = [[False] * n for _ in range(n)]
        self.fn = [[False] * n for _ in range(n)]
        self._function_patterns()
        self._place(words)
        best = None
        for mask in range(8):
            self._mask(mask)
            self._format(mask)
            score = self._penalty()
            if best is None or score < best[0]:
                best = (score, mask)
            self._mask(mask)  # XOR lần nữa = bỏ mask
        self.mask = best[1]
        self._mask(self.mask)
        self._format(self.mask)

    # ---------------------------------------------------------------- module chức năng
    def _set(self, x: int, y: int, dark: bool) -> None:
        self.m[y][x] = dark
        self.fn[y][x] = True

    def _function_patterns(self) -> None:
        n = self.size
        for i in range(n):
            self._set(6, i, i % 2 == 0)
            self._set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        self._set(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = _ALIGN[self.version]
        last = len(pos) - 1
        for i, ax in enumerate(pos):
            for j, ay in enumerate(pos):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self._set(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
        self._format(0)  # giữ chỗ, vẽ thật sau khi chọn mask
        if self.version >= 7:
            rem = self.version
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.version << 12 | rem
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = n - 11 + i % 3, i // 3
                self._set(a, b, bit)
                self._set(b, a, bit)

    def _format(self, mask: int) -> None:
        n = self.size
        data = _ECL_M << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412

        def bit(i: int) -> bool:
            return (bits >> i) & 1 == 1
        for i in range(6):
            self._set(8, i, bit(i))
        self._set(8, 7, bit(6))
        self._set(8, 8, bit(7))
        self._set(7, 8, bit(8))
        for i in range(9, 15):
            self._set(14 - i, 8, bit(i))
        for i in range(8):
            self._set(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self._set(8, n - 15 + i, bit(i))
        self._set(8, n - 8, True)  # module tối cố định

    # ---------------------------------------------------------------- dữ liệu + mask
    def _place(self, words: list[int]) -> None:
        n, i, total = self.size, 0, len(words) * 8
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(n):
                for j in range(2):
                    x = right - j
                    up = ((right + 1) & 2) == 0
                    y = n - 1 - vert if up else vert
                    if not self.fn[y][x] and i < total:
                        self.m[y][x] = (words[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def _mask(self, mask: int) -> None:
        f = (lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
             lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
             lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
             lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0)[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.fn[y][x] and f(x, y):
                    self.m[y][x] = not self.m[y][x]

    def _penalty(self) -> int:
        n, m, score = self.size, self.m, 0
        lines = [row for row in m] + [[m[y][x] for y in range(n)] for x in range(n)]
        finder = [True, False, True, True, True, False, True]
        for line in lines:
            run = 1
            for i in range(1, n + 1):
                if i < n and line[i] == line[i - 1]:
                    run += 1
                    continue
                if run >= 5:
                    score += run - 2
                run = 1
            for i in range(n - 6):
                if line[i:i + 7] == finder:
                    before = line[max(0, i - 4):i]
                    after = line[i + 7:i + 11]
                    if (len(before) == 4 and not any(before)) or (len(after) == 4 and not any(after)):
                        score += 40
        for y in range(n - 1):
            for x in range(n - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    score += 3
        dark = sum(sum(row) for row in m)
        score += abs(dark * 20 - n * n * 10) // (n * n) * 10
        return score

    # ---------------------------------------------------------------- xuất
    def rows(self, border: int = 4) -> list[list[bool]]:
        n = self.size + 2 * border
        out = [[False] * n for _ in range(n)]
        for y in range(self.size):
            for x in range(self.size):
                out[y + border][x + border] = self.m[y][x]
        return out

    def to_text(self, border: int = 2) -> str:
        """Hai hàng module mỗi dòng chữ (▀ với màu chữ = hàng trên, màu nền = hàng dưới), đen trên trắng
        bằng mã ANSI nên quét được cả trên terminal nền tối lẫn nền sáng."""
        rows = self.rows(border)
        if len(rows) % 2:
            rows.append([False] * len(rows[0]))
        lines = []
        for y in range(0, len(rows), 2):
            parts = []
            for top, bottom in zip(rows[y], rows[y + 1]):
                parts.append(f"\x1b[{30 if top else 97};{40 if bottom else 107}m▀")
            lines.append("".join(parts) + "\x1b[0m")
        return "\n".join(lines)

    def to_svg(self, scale: int = 8, border: int = 4) -> str:
        rows = self.rows(border)
        n = len(rows)
        path = "".join(f"M{x},{y}h1v1h-1z" for y, row in enumerate(rows) for x, d in enumerate(row) if d)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" width="{n * scale}" '
                f'height="{n * scale}" shape-rendering="crispEdges"><rect width="{n}" height="{n}" fill="#fff"/>'
                f'<path d="{path}" fill="#000"/></svg>')
