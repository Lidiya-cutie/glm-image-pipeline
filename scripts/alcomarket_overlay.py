#!/usr/bin/env python3
"""
Алкомаркет — наложение текста на баннеры алкогольной продукции.

Поддержка:
- Product-type: бутылки, банки, продуктовая реклама (без людей или с людьми в сцене)
- Venues: магазины, бары, лаунджи — крафтовый бейдж вместо продукта

Обязательно: дисклеймер 18+, предупреждение о вреде алкоголя.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CONFIG_PATH = PROJECT_ROOT / "configs" / "alcomarket_config.json"
_config_cache: Optional[Dict[str, Any]] = None

try:
    from scripts.text_overlay import TextRenderer, LAYOUTS, get_layout_by_name
except ImportError:
    TextRenderer = None
    LAYOUTS = [{"name": "classic_left"}]

    def get_layout_by_name(name: str) -> Dict:
        return LAYOUTS[0] if LAYOUTS else {}


def create_oval_promotional_badge(
    text: str,
    font_size: int = 14,
    padding_x: int = 14,
    padding_y: int = 8,
    bg_color: tuple = (40, 40, 50, 220),
    text_color: tuple = (255, 255, 255),
) -> Image.Image:
    """
    Создаёт овальный промо-бейдж с текстом.
    Используется для бейджей типа «АКЦИЯ», «НОВИНКА», названий магазинов.
    """
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size
        )
    except OSError:
        font = ImageFont.load_default()
    draw_temp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = draw_temp.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    w = tw + padding_x * 2
    h = th + padding_y * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r = min(w, h) // 2
    draw.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=r, fill=bg_color)
    draw.text((padding_x, padding_y), text, font=font, fill=text_color)
    return img


def _load_config() -> Dict[str, Any]:
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _config_cache = json.load(f)
    else:
        _config_cache = {}
    return _config_cache


def _style_to_tuples(style: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(style)
    for k in ("headline_color", "text_color", "accent_color", "shadow_color", "color"):
        if k in out and isinstance(out[k], list):
            out[k] = tuple(out[k][:3]) if len(out[k]) >= 3 else tuple(out[k])
    return out


def build_alcomarket_text_bundle(
    headline: Optional[str] = None,
    description: Optional[str] = None,
    disclaimer: Optional[str] = None,
    product_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Собирает текст для баннера алкомаркета.
    product_type: "products" — продукт (бутылки, банки),
                  "venues" — магазин/бар/лаундж (крафтовый бейдж).
    """
    cfg = _load_config()
    if product_type is None:
        product_type = random.choice(["products", "venues"])

    if product_type == "products":
        hl = cfg.get("headlines", cfg.get("headlines_advertising", []))
        desc = cfg.get("descriptions", cfg.get("descriptions_advertising", []))
    else:
        hl = cfg.get("headlines_venues", cfg.get("headlines", []))
        desc = cfg.get("descriptions_venues", cfg.get("descriptions", []))

    disc = cfg.get("disclaimers", [])
    default_disc = "Чрезмерное употребление алкоголя вредит здоровью. 18+."
    return {
        "headline": headline or (random.choice(hl) if hl else "АЛКОМАРКЕТ"),
        "description": description or (random.choice(desc) if desc else ""),
        "disclaimer": disclaimer or (random.choice(disc) if disc else default_disc),
        "product_type": product_type,
    }


def _draw_venue_badge(
    image: Image.Image,
    text: str,
    text_zones: List[tuple],
) -> None:
    """Накладывает крафтовый бейдж (магазин, бар, лаундж) на свободную зону."""
    try:
        cfg = _load_config()
        badges = cfg.get("venue_badges", ["ЛАУНДЖ", "АЛКОМАРКЕТ", "ВИННЫЙ БУТИК"])
        badge_text = text or random.choice(badges)
        img_w, img_h = image.size
        scale = min(img_w, img_h) / 1024
        font_size = max(18, int(28 * scale))
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size
            )
        except OSError:
            font = ImageFont.load_default()
        bbox = ImageDraw.Draw(image).textbbox((0, 0), badge_text, font=font)
        pw = bbox[2] - bbox[0] + 24
        ph = bbox[3] - bbox[1] + 16
        pos = _find_safe_position(img_w, img_h, text_zones, pw, ph)
        if not pos:
            return
        badge = Image.new("RGBA", (pw, ph), (40, 40, 50, 200))
        draw = ImageDraw.Draw(badge)
        draw.rounded_rectangle(
            [(0, 0), (pw - 1, ph - 1)], radius=8, outline=(200, 200, 200, 255), width=1
        )
        draw.text((12, 8), badge_text, font=font, fill=(255, 255, 255, 255))
        image.paste(badge, pos, badge)
    except Exception:
        pass


def _find_safe_position(
    img_width: int,
    img_height: int,
    text_zones: List[tuple],
    pw: int,
    ph: int,
) -> Optional[tuple]:
    margin = 20
    candidates = [
        (img_width - pw - margin, margin),
        (margin, margin),
        (int(img_width * 0.5 - pw * 0.5), margin),
    ]
    for px, py in candidates:
        px = max(margin, min(px, img_width - pw - margin))
        py = max(margin, min(py, img_height - ph - margin))
        rect = (px, py, px + pw, py + ph)
        overlaps = any(_rects_overlap(rect, tz) for tz in text_zones)
        if not overlaps:
            return (px, py)
    return None


def _rects_overlap(a: tuple, b: tuple) -> bool:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return not (ax2 <= bx1 or ax1 >= bx2 or ay2 <= by1 or ay1 >= by2)


def _get_text_zones(img_width: int, img_height: int, margin: int) -> List[tuple]:
    zones = []
    text_right = int(img_width * 0.55)
    h_zone_top = int(img_height * 0.25)
    desc_bottom = int(img_height * 0.72)
    disc_top = int(img_height * 0.82)
    zones.append((margin, margin, text_right, h_zone_top))
    zones.append((margin, h_zone_top, text_right, desc_bottom))
    zones.append((margin, disc_top, img_width - margin, img_height - margin))
    return zones


class AlcomarketBannerOverlay:
    """Наложение текста на баннеры категории «алкомаркет»."""

    REF_WIDTH = 1024

    def __init__(
        self,
        layout: Optional[Dict[str, Any]] = None,
        style: Optional[Dict[str, Any]] = None,
        disclaimer_bg_style: Optional[Dict[str, Any]] = None,
    ) -> None:
        cfg = _load_config()
        styles = cfg.get("styles", [])
        disc_styles = cfg.get("disclaimer_bg_styles", [])
        self.layout = layout or (LAYOUTS[0] if LAYOUTS else {})
        self.style = _style_to_tuples(style or (styles[0] if styles else {}))
        self.disclaimer_bg_style = disclaimer_bg_style or (
            disc_styles[0] if disc_styles else {}
        )

    def apply(
        self,
        image: Image.Image,
        headline: str,
        description: str,
        disclaimer: str,
        product_type: str = "products",
        venue_badge_text: Optional[str] = None,
    ) -> Image.Image:
        """Накладывает текст и при product_type=venues — крафтовый бейдж."""
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        img_w, img_h = image.size
        margin = int(min(img_w, img_h) * 0.06)
        text_zones = _get_text_zones(img_w, img_h, margin)

        draw = ImageDraw.Draw(image)
        scale = min(img_w, img_h) / self.REF_WIDTH
        font_sizes = {
            "headline": max(28, int(50 * scale)),
            "text": max(14, int(24 * scale)),
            "disclaimer": max(10, int(14 * scale)),
        }
        safe_left, max_w = margin, int(img_w * 0.5)
        hl_color = self.style.get("headline_color", (255, 255, 255))
        if isinstance(hl_color, list):
            hl_color = tuple(hl_color[:3])
        txt_color = self.style.get("text_color", (240, 240, 240))
        if isinstance(txt_color, list):
            txt_color = tuple(txt_color[:3])

        try:
            hl_font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                font_sizes["headline"],
            )
            txt_font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_sizes["text"]
            )
            disc_font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                font_sizes["disclaimer"],
            )
        except OSError:
            hl_font = txt_font = disc_font = ImageFont.load_default()

        def _draw_with_shadow(d, pos, text, font, color, shadow=(0, 0, 0)):
            x, y = pos
            d.text((x + 1, y + 1), text, font=font, fill=shadow)
            d.text((x, y), text, font=font, fill=color)

        hl_y = margin
        _draw_with_shadow(draw, (safe_left, hl_y), headline, hl_font, hl_color)
        desc_y = int(img_h * 0.35)
        _draw_with_shadow(draw, (safe_left, desc_y), description, txt_font, txt_color)
        disc_y = img_h - margin - font_sizes["disclaimer"] * 3
        disc_x = img_w // 2
        bbox = draw.textbbox((0, 0), disclaimer, font=disc_font)
        tw = bbox[2] - bbox[0]
        _draw_with_shadow(
            draw, (disc_x - tw // 2, disc_y), disclaimer, disc_font, (255, 255, 255)
        )

        if product_type == "venues":
            _draw_venue_badge(image, venue_badge_text, text_zones)

        return image


if __name__ == "__main__":
    print("Alcomarket overlay. Use generate_alcomarket_banners.py for generation.")
