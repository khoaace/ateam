"""Theme màu của TUI: theme dựng sẵn của Textual + một màu nhấn tuỳ chọn, và bảng màu ngữ nghĩa (đang chạy,
xong, lỗi…) lấy từ theme cho các đoạn chữ Rich (không đi qua CSS). Lựa chọn lưu ở state.json (`theme`,
`accent`), dùng chung mọi dự án."""

from __future__ import annotations

import dataclasses

from textual.color import Color
from textual.theme import BUILTIN_THEMES, Theme

from .i18n import tr

DEFAULT_THEME = "textual-dark"
# màu nhấn: khoá (lưu trong state.json) -> mã màu. Không chọn = màu của theme
ACCENTS: dict[str, str] = {
    "blue": "#3B82F6", "purple": "#8B5CF6", "green": "#22C55E", "orange": "#F97316",
    "pink": "#EC4899", "yellow": "#EAB308", "cyan": "#06B6D4", "red": "#EF4444",
}
# tên gõ được ở /theme (tiếng Việt không dấu / có dấu, tiếng Anh)
ACCENT_ALIASES = {
    "xanh-duong": "blue", "xanhduong": "blue", "xanh dương": "blue", "xanh-dương": "blue",
    "tim": "purple", "tím": "purple", "xanh-la": "green", "xanhla": "green", "xanh lá": "green",
    "xanh-lá": "green", "cam": "orange", "hong": "pink", "hồng": "pink", "vang": "yellow",
    "vàng": "yellow", "do": "red", "đỏ": "red", "xanh-ngoc": "cyan", "ngọc": "cyan",
    "none": "", "default": "", "mac-dinh": "", "mặc-định": "", "-": "",
}


def accent_label(key: str) -> str:
    return {"": tr("Màu của theme"), "blue": tr("Xanh dương"), "purple": tr("Tím"), "green": tr("Xanh lá"),
            "orange": tr("Cam"), "pink": tr("Hồng"), "yellow": tr("Vàng"), "cyan": tr("Xanh ngọc"),
            "red": tr("Đỏ")}.get(key, key)


def normalize_accent(name: str | None) -> str | None:
    """Khoá màu nhấn từ tên người dùng gõ; "" = màu của theme; None = không nhận ra."""
    n = (name or "").strip().lower()
    if n in ACCENTS:
        return n
    if n in ACCENT_ALIASES:
        return ACCENT_ALIASES[n]
    return None


def theme_names() -> list[str]:
    """Theme dựng sẵn: tối trước, sáng sau, mỗi nhóm theo tên."""
    return sorted(BUILTIN_THEMES, key=lambda n: (not BUILTIN_THEMES[n].dark, n))


def is_dark(name: str) -> bool:
    base = BUILTIN_THEMES.get(name.split("+", 1)[0])
    return base.dark if base else True


def theme_id(base: str, accent: str) -> str:
    return f"{base}+{accent}" if accent else base


def make_theme(base: str, accent: str) -> Theme | None:
    """Theme `base` với màu nhấn `accent` (đổi cả primary và accent: viền, nút chính, tiêu đề). None nếu
    không cần theme mới (không có màu nhấn) hoặc base không tồn tại."""
    src = BUILTIN_THEMES.get(base)
    if src is None or not accent or accent not in ACCENTS:
        return None
    color = ACCENTS[accent]
    return dataclasses.replace(src, name=theme_id(base, accent), primary=color, accent=color)


# nền xám ấm của giao diện web (app.css --bg/--surface/--surface-2…): theme tối của Textual pha primary vào panel,
# thanh cuộn, dòng chọn mất focus → nền ngả xanh đậm/tím; giữ primary/accent làm màu nhấn
GRAY = {"background": "#10110e", "surface": "#1c1d18", "panel": "#24261f"}
GRAY_VARS = {
    "footer-background": "#161713", "block-cursor-blurred-background": "#2c2e26",
    "block-hover-background": "#2c2e26", "scrollbar": "#35372f", "scrollbar-hover": "#484b40",
    "scrollbar-background": "#161713", "scrollbar-background-hover": "#161713",
    "scrollbar-background-active": "#161713", "scrollbar-corner-color": "#161713",
}


def grayed(t: Theme) -> Theme:
    """Theme tối `t` với nền xám (giữ tên — đăng ký đè theme dựng sẵn). Theme sáng / theme ANSI giữ nguyên."""
    if not t.dark or (t.background or "").startswith("ansi"):
        return t
    secondary = t.secondary
    if secondary and not secondary.startswith("ansi"):
        c = Color.parse(secondary)
        if c.brightness < 0.45:  # secondary xanh navy (textual-dark #004578): chữ "info" khó đọc trên nền xám
            secondary = c.lighten(0.3).hex
    return dataclasses.replace(t, **GRAY, secondary=secondary, variables={**t.variables, **GRAY_VARS})


def _rich(value: str | None, fallback: str) -> str:
    """Màu theme (hex hoặc ansi_*) -> chuỗi màu Rich hiểu được."""
    if not value:
        return fallback
    if value.startswith("ansi_"):
        return value[len("ansi_"):]
    try:
        return Color.parse(value).hex
    except Exception:
        return fallback


def palette(theme: Theme | None) -> dict[str, str]:
    """Màu ngữ nghĩa cho chữ Rich: running (đang chạy/xử lý), ok, warn, err, info."""
    if theme is None:
        return {"running": "dodger_blue1", "ok": "green", "warn": "yellow", "err": "red", "info": "cyan"}
    return {
        "running": _rich(theme.primary, "dodger_blue1"),
        "ok": _rich(theme.success, "green"),
        "warn": _rich(theme.warning, "yellow"),
        "err": _rich(theme.error, "red"),
        "info": _rich(theme.secondary or theme.accent, "cyan"),
    }
