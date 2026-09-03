"""Custom caption card renderer (CSS-card style, drawn into pixels).

Renders an Arabic caption as a styled card — rounded panel, accent color bar,
title + optional subtitle, RTL-aligned, with a soft shadow. Drawn with Pillow
so the card is physically part of the video.

Styles:
  - card:   rounded panel, accent bar on the right, title + subtitle
  - pill:   single rounded pill, one line, small
  - banner: full-width bar, centered text

Used by scripts/tiktok_vertical.py and template01.
"""
from __future__ import annotations

from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

FONT_AR = Path(r"C:\Windows\Fonts\majallab.ttf")      # Sakkal Majalla Bold — full presentation forms (ت ا ة)
FONT_AR_BODY = Path(r"C:\Windows\Fonts\majalla.ttf")       # Sakkal Majalla — elegant Naskh
FONT_HANDLE = Path(r"C:\Windows\Fonts\segoeui.ttf")        # clean Latin for @handle


def shape_ar(text: str) -> str:
    """Reshape Arabic glyphs + fix RTL direction for Pillow rendering."""
    if not text:
        return text
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    p = path if path.exists() else FONT_AR
    return ImageFont.truetype(str(p), size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for wd in words:
        probe = (cur + " " + wd).strip()
        if draw.textlength(probe, font=font) <= max_w:
            cur = probe
        else:
            lines.append(cur); cur = wd
    if cur:
        lines.append(cur)
    return lines or [""]


def _rounded(draw: ImageDraw.ImageDraw, box, radius: int, fill, outline=None, width=0):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


# --- TikTok note logo (drawn, two-tone offset shadow) -----------------------

def draw_tiktok_note(draw: ImageDraw.ImageDraw, cx: float, cy: float, size: float, opacity=255):
    """Draw a TikTok-style musical note (head + stem + flag) with the red/teal
    offset shadow layers, around (cx, cy), roughly `size` tall.
    """
    teal = (37, 244, 238, opacity)
    red = (254, 44, 85, opacity)
    white = (255, 255, 255, opacity)

    def _note(ox: float, oy: float, color: tuple):
        x, y = cx + ox, cy + oy
        head_r = size * 0.26
        # stem
        sx = x + head_r * 0.85
        draw.rectangle((sx, y - size * 0.62, sx + size * 0.075, y + head_r * 0.4), fill=color)
        # head (ellipse, slight tilt via offset top-left)
        draw.ellipse((x - head_r, y, x + head_r, y + head_r * 1.35), fill=color)
        # flag
        fw = size * 0.34
        draw.polygon(
            [
                (sx, y - size * 0.62),
                (sx + fw, y - size * 0.88),
                (sx + fw * 0.8, y - size * 0.62),
                (sx, y - size * 0.42),
            ],
            fill=color,
        )

    _note(-size * 0.10, -size * 0.08, teal)   # teal offset
    _note(size * 0.10, size * 0.06, red)      # red offset
    _note(0, 0, white)                        # main


def tiktok_watermark(img: Image.Image, handle: str = "@mventor", size_frac: float = 0.032,
                     pad_frac: float = 0.035, corner: str = "top-left") -> Image.Image:
    """TikTok note logo + @handle watermark — small, clean, top-left corner."""
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    # Latin handle: clean Segoe UI, not Arabic font, smaller
    font = _font(FONT_HANDLE, max(16, int(h * 0.028)))
    note_size = h * size_frac
    text = handle  # Latin, no shaping
    tw = draw.textlength(text, font=font)
    th = font.size
    pad = int(w * pad_frac)

    if corner == "top-left":
        nx, ny = pad, pad
    elif corner == "top-right":
        nx, ny = w - pad - note_size - tw - 14, pad
    elif corner == "bottom-left":
        nx, ny = pad, h - pad - note_size
    else:  # bottom-right
        nx, ny = w - pad - note_size - tw - 14, h - pad - note_size

    # logo centered in its box
    draw_tiktok_note(draw, nx + note_size / 2, ny + note_size / 2, note_size * 0.9)
    # handle text to the right of the logo
    ty = ny + (note_size - th) / 2
    draw.text((nx + note_size + 10, ty), text, font=font, fill=(255, 255, 255, 255),
              stroke_width=2, stroke_fill=(0, 0, 0, 200))
    return img



def card(img: Image.Image, title: str, subtitle: str = "",
         accent: tuple = (234, 179, 8, 255),            # gold
         panel: tuple = (0, 0, 0, 200),
         text_color: tuple = (255, 255, 255, 255),
         max_width_frac: float = 0.94, panel_pad: int = 36) -> Image.Image:
    """Rounded card — wide + tall (Template 01: 9:16 TikTok for 16:9 source).
    Right-aligned Arabic title + subtitle, accent bar on the RTL edge.
    """
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    max_w = int(w * max_width_frac)

    # larger Arabic fonts
    t_font = _font(FONT_AR, max(32, int(h * 0.052)))
    s_font = _font(FONT_AR_BODY, max(24, int(h * 0.040)))
    title_lines = _wrap(draw, shape_ar(title), t_font, max_w - panel_pad * 2 - 12)
    sub_lines = _wrap(draw, shape_ar(subtitle), s_font, max_w - panel_pad * 2 - 12) if subtitle else []

    title_h = t_font.size + 10
    sub_h = (s_font.size + 8) * len(sub_lines)
    base_h = panel_pad * 2 + title_h * len(title_lines) + (sub_h + 10 if sub_lines else 0)
    card_h = int(base_h * 1.95)  # ~2x taller

    x0 = int((w - max_w) / 2)
    y0 = int(h - card_h - h * 0.04)
    x1 = x0 + max_w
    y1 = y0 + card_h

    # soft shadow
    _rounded(draw, (x0 + 4, y0 + 8, x1 + 4, y1 + 8), radius=22, fill=(0, 0, 0, 90))
    # panel
    _rounded(draw, (x0, y0, x1, y1), radius=22, fill=panel)
    # accent bar (right edge, RTL side)
    _rounded(draw, (x1 - 10, y0 + 14, x1 - 2, y1 - 14), radius=5, fill=accent)

    # center text vertically inside the taller card
    content_h = title_h * len(title_lines) + (sub_h + 10 if sub_lines else 0)
    ty = y0 + (card_h - content_h) // 2
    tx = x1 - panel_pad - 12
    for ln in title_lines:
        tw = draw.textlength(ln, font=t_font)
        draw.text((tx - tw, ty), ln, font=t_font, fill=text_color,
                  stroke_width=1, stroke_fill=(0, 0, 0, 90))
        ty += title_h
    ty += 6
    for ln in sub_lines:
        tw = draw.textlength(ln, font=s_font)
        draw.text((tx - tw, ty), ln, font=s_font, fill=(226, 226, 226, 255),
                  stroke_width=1, stroke_fill=(0, 0, 0, 80))
        ty += s_font.size + 8
    return img


def pill(img: Image.Image, text: str, accent: tuple = (234, 179, 8, 255),
         panel: tuple = (0, 0, 0, 190)) -> Image.Image:
    """Single rounded pill, one line, RTL text."""
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    font = _font(FONT_AR, max(24, int(h * 0.04)))
    text = shape_ar(text)
    tw = draw.textlength(text, font=font)
    pad_x, pad_y = 26, 14
    x0 = int((w - tw - pad_x * 2) / 2)
    y0 = int(h - font.size - pad_y * 2 - h * 0.05)
    x1 = x0 + tw + pad_x * 2
    y1 = y0 + font.size + pad_y * 2
    _rounded(draw, (x1, y0, x1 + 4, y1), radius=3, fill=accent)
    _rounded(draw, (x0 + 3, y0 + 4, x1 + 3, y1 + 4), radius=28, fill=(0, 0, 0, 80))
    _rounded(draw, (x0, y0, x1, y1), radius=28, fill=panel)
    draw.text((x0 + pad_x, y0 + pad_y), text, font=font, fill=(255, 255, 255, 255))
    return img


def banner(img: Image.Image, text: str, accent: tuple = (234, 179, 8, 255),
           panel: tuple = (0, 0, 0, 210)) -> Image.Image:
    """Full-width centered bar."""
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    font = _font(FONT_AR, max(26, int(h * 0.045)))
    text = shape_ar(text)
    bar_h = int(font.size * 1.7)
    y0 = int(h - bar_h - h * 0.03)
    draw.rectangle((0, y0, w, y0 + bar_h), fill=panel)
    draw.rectangle((0, y0, w, y0 + 5), fill=accent)
    tw = draw.textlength(text, font=font)
    draw.text((int((w - tw) / 2), y0 + int(bar_h / 2 - font.size / 2)), text,
              font=font, fill=(255, 255, 255, 255))
    return img


_STYLES = {"card": card, "pill": pill, "banner": banner}


def render(img: Image.Image, text: str, subtitle: str = "", style: str = "card", **kw) -> Image.Image:
    if style not in _STYLES:
        raise SystemExit(f"unknown caption style: {style}")
    if style == "card":
        return card(img, text, subtitle, **kw)
    if style == "pill":
        return pill(img, text, **kw)
    return banner(img, text, **kw)
