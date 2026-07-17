#!/usr/bin/env python3
"""
Табак, табачная продукция, курительные принадлежности.

Модуль наложения текста на баннеры категории «табак».
Поддержка наложения пачек сигарет/сигар и логотипов из cigarette_images
только на свободные от текста зоны.
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

CONFIG_PATH = PROJECT_ROOT / "configs" / "tobacco_config.json"
TOBACCO_STORES_PATH = PROJECT_ROOT / "configs" / "tobacco_stores_bars.json"
CRAFT_FONTS_ROOT = PROJECT_ROOT / "fonts" / "craft"

_config_cache: Optional[Dict[str, Any]] = None
_tobacco_stores_cache: Optional[List[Dict[str, Any]]] = None
_craft_fonts_cache: Optional[List[Path]] = None

# Шаблоны фраз про часы работы (используются во втором крафтовом бейдже над дисклеймером)
HOURS_PHRASES: List[str] = [
    # 1. Классические
    "Часы работы заведения: [время]",
    "Режим работы: [время]",
    "График работы: [время]",
    "Время работы кафе: [время]",
    "Время работы кальянной: [время]",
    "Время работы клуба: [время]",
    "Мы открыты: [время]",
    "Заведение работает: [время]",
    "Наш график: [время]",
    "Время работы: [время]",
    # 2. Дружелюбные
    "Ждём вас ежедневно: [время]",
    "Добро пожаловать: мы открыты [время]!",
    "Заходите в гости: работаем [время]",
    "Всегда рады видеть вас: [время]",
    "Двери открыты для вас: [время]",
    "Приходите, когда удобно: [время]",
    "Ваш уютный уголок ждёт: [время]",
    # 3. Энергичные
    "Открыты и заряжены на отличное настроение: [время]!",
    "Время зажигательных вечеров: [время]!",
    "Кальяны дымятся, музыка играет — мы работаем: [время]!",
    "Атмосфера тепла и дыма: [время]!",
    # 4. Премиальные
    "Приглашаем провести вечер в атмосфере уюта: [время]",
    "Изысканная атмосфера ждёт вас: [время]",
    "Элегантный отдых начинается здесь: [время]",
    "Время утончённых удовольствий: [время]",
    # 5. Атмосфера кальянной / лаунжа
    "Дымные вечера: [время]!",
    "Ароматы Востока ждут вас: [время]",
    "Кальяны, чай и душевные разговоры: [время]",
    "Расслабляющая атмосфера: [время]",
    "Время для кальяна и душевных бесед: [время]",
    "Дышите глубже — мы открыты: [время]",
    # 6. Особый график
    "Работаем с полудня до глубокой ночи: [время]",
    "Открыты днём и ночью: [время]",
    "Ночные посиделки: [время]",
    "После работы — к нам: [время]",
    # 7. Призыв к действию
    "Загляните к нам: [время] — вас ждёт идеальный кальян!",
    "Приходите сегодня: мы открыты [время]!",
    "Не пропустите: работаем [время] — ваш вечер станет ярче!",
    "Планируйте вечер с нами: [время]",
    "Забронируйте столик: мы ждём вас [время]",
    "Проведите вечер в кругу друзей: [время]",
    # 8. Креативные
    "Когда мы открыты, время останавливается: [время]",
    "Здесь время течёт медленнее: [время]",
    "Двери в мир уюта открыты: [время]",
    "Время, когда всё возможно: [время]",
    "Магия начинается: [время] — мы открыты для вас!",
    "Отдыхайте, дымите, наслаждайтесь: [время]",
    "Ваше время начинается здесь: [время]",
    "Где время принадлежит вам: [время]",
]

try:
    from scripts.text_overlay import TextRenderer, LAYOUTS, get_layout_by_name
except ImportError:
    TextRenderer = None
    LAYOUTS = [{"name": "classic_left"}]
    def get_layout_by_name(name: str) -> Dict:
        return LAYOUTS[0]

try:
    from scripts.alcomarket_overlay import create_oval_promotional_badge
except ImportError:
    def create_oval_promotional_badge(text: str, font_size: int = 14, padding_x: int = 14, padding_y: int = 8):
        from PIL import Image
        img = Image.new("RGBA", (60, 30), (0, 0, 0, 0))
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


def _load_tobacco_stores() -> List[Dict[str, Any]]:
    """
    Кэширует и возвращает список заведений из tobacco_stores_bars.json.
    """
    global _tobacco_stores_cache
    if _tobacco_stores_cache is not None:
        return _tobacco_stores_cache
    if not TOBACCO_STORES_PATH.exists():
        _tobacco_stores_cache = []
        return _tobacco_stores_cache
    try:
        with open(TOBACCO_STORES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _tobacco_stores_cache = data.get("stores", [])
    except Exception:
        _tobacco_stores_cache = []
    return _tobacco_stores_cache


def get_random_tobacco_venue(kind: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Возвращает случайное заведение (словарь) из tobacco_stores_bars.json.

    kind:
      - "hookah" — отбор по кальянным
      - "vape"   — отбор по вейп-шопам
      - None     — любое табачное заведение
    """
    stores = _load_tobacco_stores()
    if not stores:
        return None

    def _match_hookah(store: Dict[str, Any]) -> bool:
        cat = (store.get("category") or "").lower()
        name = (store.get("name") or "").lower()
        return "кальян" in cat or "hookah" in name

    def _match_vape(store: Dict[str, Any]) -> bool:
        cat = (store.get("category") or "").lower()
        return "вейп" in cat or "vape" in (store.get("name") or "").lower()

    filtered: List[Dict[str, Any]]
    if kind == "hookah":
        filtered = [s for s in stores if _match_hookah(s)]
    elif kind == "vape":
        filtered = [s for s in stores if _match_vape(s)]
    else:
        filtered = stores

    pool = filtered or stores
    if not pool:
        return None
    return random.choice(pool)


def get_random_tobacco_venue_name(kind: Optional[str] = None) -> Optional[str]:
    """
    Обёртка над get_random_tobacco_venue, возвращает только name.
    Сохранена для обратной совместимости.
    """
    v = get_random_tobacco_venue(kind)
    if not v:
        return None
    return v.get("name") or None


def _load_craft_fonts() -> List[Path]:
    """
    Ищет все .ttf в fonts/craft (и подпапках) для крафтовых надписей.
    """
    global _craft_fonts_cache
    if _craft_fonts_cache is not None:
        return _craft_fonts_cache
    fonts: List[Path] = []
    if CRAFT_FONTS_ROOT.exists():
        for p in CRAFT_FONTS_ROOT.rglob("*.ttf"):
            fonts.append(p)
    _craft_fonts_cache = fonts
    return _craft_fonts_cache


def _has_cyrillic(text: str) -> bool:
    """
    Грубая проверка: есть ли кириллица в строке.
    """
    return any("\u0400" <= ch <= "\u04FF" for ch in text)


# Какой файл шрифта выбрал get_cyrillic_craft_font (для отладки / логов).
LAST_CRAFT_FONT_PATH_USED: Optional[str] = None


def _font_renders_cyrillic_credibly(
    font: ImageFont.ImageFont, text: str, size: int
) -> bool:
    """
    Латинские craft-шрифты часто грузятся без ошибки, но дают узкие .notdef для кириллицы.
    Сравниваем ширину глифа с опорным DejaVu.
    """
    sample = sorted({c for c in text if "\u0400" <= c <= "\u04FF"})
    if not sample:
        return True
    ref_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    try:
        ref = ImageFont.truetype(ref_path, size)
    except OSError:
        return True
    d = ImageDraw.Draw(Image.new("RGBA", (512, 96), (0, 0, 0, 0)))
    for ch in sample[:12]:
        br = d.textbbox((0, 0), ch, font=ref)
        bf = d.textbbox((0, 0), ch, font=font)
        rw = max(1, br[2] - br[0])
        fw = bf[2] - bf[0]
        if fw < rw * 0.42:
            return False
    return True


def get_cyrillic_craft_font(text: str, size: int) -> ImageFont.FreeTypeFont:
    """
    Крафтовый шрифт для подписи: случайный из fonts/craft.
    Для кириллицы — только файлы, у которых глифы не «ломаются»; иначе DejaVu Sans Bold.
    Путь последнего выбора: LAST_CRAFT_FONT_PATH_USED (или os.environ DISCREDITATION_DEBUG_CRAFT_FONT=1 — stderr).
    """
    global LAST_CRAFT_FONT_PATH_USED
    LAST_CRAFT_FONT_PATH_USED = None
    prefer_cyrillic = _has_cyrillic(text or "")
    fonts = _load_craft_fonts()
    shuffled = list(fonts)
    random.shuffle(shuffled)

    def _dejavu_bold() -> ImageFont.FreeTypeFont:
        global LAST_CRAFT_FONT_PATH_USED
        p = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        try:
            LAST_CRAFT_FONT_PATH_USED = p
            return ImageFont.truetype(p, size)
        except OSError:
            LAST_CRAFT_FONT_PATH_USED = None
            return ImageFont.load_default()

    if prefer_cyrillic:
        for fp in shuffled:
            try:
                f = ImageFont.truetype(str(fp), size)
            except OSError:
                continue
            if _font_renders_cyrillic_credibly(f, text, size):
                LAST_CRAFT_FONT_PATH_USED = str(fp)
                if os.environ.get("DISCREDITATION_DEBUG_CRAFT_FONT"):
                    print(f"[craft-font] kyrl: {fp}", file=sys.stderr)
                return f
        if os.environ.get("DISCREDITATION_DEBUG_CRAFT_FONT"):
            print("[craft-font] kyrl: fallback DejaVuSans-Bold", file=sys.stderr)
        return _dejavu_bold()

    for fp in shuffled:
        try:
            LAST_CRAFT_FONT_PATH_USED = str(fp)
            f = ImageFont.truetype(str(fp), size)
            if os.environ.get("DISCREDITATION_DEBUG_CRAFT_FONT"):
                print(f"[craft-font] latin: {fp}", file=sys.stderr)
            return f
        except OSError:
            continue

    try:
        p = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        LAST_CRAFT_FONT_PATH_USED = p
        return ImageFont.truetype(p, size)
    except OSError:
        LAST_CRAFT_FONT_PATH_USED = None
        return ImageFont.load_default()


def _style_to_tuples(style: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(style)
    for k in ("headline_color", "text_color", "accent_color", "shadow_color", "color"):
        if k in out and isinstance(out[k], list):
            out[k] = tuple(out[k][:3]) if len(out[k]) >= 3 else tuple(out[k])
    return out


def paint_styled_footer_disclaimer(
    image: Image.Image,
    disclaimer: str,
    disclaimer_bg_style: Dict[str, Any],
    ref_width: int = 1024,
) -> Tuple[int, int]:
    """
    Полоса снизу + стилизованный дисклеймер (та же геометрия, что в TobaccoBannerOverlay.apply).
    Возвращает (disc_y, disc_rect_top) для выставления адреса/часов в apply.
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    disc_txt = (disclaimer or "").strip()
    if not disc_txt:
        img_w, img_h = image.size
        margin = int(min(img_w, img_h) * 0.06)
        return img_h - margin * 2, img_h - margin

    img_w, img_h = image.size
    margin = int(min(img_w, img_h) * 0.06)
    scale = min(img_w, img_h) / ref_width
    font_sizes = {"disclaimer": max(10, int(14 * scale))}
    disc_base_size = font_sizes["disclaimer"]
    disc_font_size = disc_base_size * 2
    try:
        disc_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            disc_font_size,
        )
        disc_font_small = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            disc_base_size,
        )
    except OSError:
        disc_font = ImageFont.load_default()
        disc_font_small = ImageFont.load_default()

    draw = ImageDraw.Draw(image)

    def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> str:
        words = (text or "").split()
        if not words:
            return ""
        lines: List[str] = []
        cur: List[str] = []
        for w in words:
            test = (" ".join(cur + [w])).strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width or not cur:
                cur.append(w)
            else:
                lines.append(" ".join(cur))
                cur = [w]
        if cur:
            lines.append(" ".join(cur))
        return "\n".join(lines)

    def _render_line_with_spacing(
        line: str,
        font: ImageFont.ImageFont,
        spacing_mult: float,
        fill: tuple,
        shadow: tuple,
    ) -> Image.Image:
        if not line:
            return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        pad = 6
        char_images = []
        total_w = 0
        max_h = 0
        for c in line:
            b = font.getbbox(c) if hasattr(font, "getbbox") else draw.textbbox((0, 0), c, font=font)
            cw = b[2] - b[0]
            ch = b[3] - b[1]
            ox, oy = pad - b[0], pad - b[1]
            tmp = Image.new("RGBA", (cw + pad * 2 + 4, ch + pad * 2 + 4), (0, 0, 0, 0))
            td = ImageDraw.Draw(tmp)
            td.text((ox + 1, oy + 1), c, font=font, fill=shadow)
            td.text((ox, oy), c, font=font, fill=fill)
            advance = int(cw * spacing_mult)
            char_img = tmp.crop((pad, pad, pad + cw, pad + ch))
            char_images.append((char_img, advance))
            total_w += advance
            max_h = max(max_h, char_img.size[1])
        out = Image.new("RGBA", (total_w, max_h), (0, 0, 0, 0))
        x = 0
        for img, adv in char_images:
            out.paste(img, (x, 0), img)
            x += adv
        return out

    def _draw_disclaimer_styled(
        text: str,
        font: ImageFont.ImageFont,
        center_x: int,
        top_y: int,
        max_width: int,
        fill: tuple,
        shadow: tuple = (0, 0, 0, 200),
        line_gap: int = 18,
        height_mult: float = 2.0,
        width_mult: float = 1.3,
        spacing_mult: float = 1.1,
    ) -> None:
        wrapped = _wrap_text(text, font, max_width)
        if not wrapped:
            return
        lines = wrapped.split("\n")
        line_imgs = []
        max_w = 0
        total_h = 0
        for ln in lines:
            limg = _render_line_with_spacing(ln, font, spacing_mult, fill, shadow)
            line_imgs.append(limg)
            max_w = max(max_w, limg.size[0])
            total_h += limg.size[1] + line_gap
        total_h -= line_gap
        if max_w <= 0 or total_h <= 0:
            return
        combined = Image.new("RGBA", (max_w, total_h), (0, 0, 0, 0))
        y = 0
        for limg in line_imgs:
            combined.paste(limg, (0, y), limg)
            y += limg.size[1] + line_gap
        scale_x = width_mult / (height_mult * spacing_mult)
        new_w = max(1, int(combined.size[0] * scale_x))
        new_h = combined.size[1]
        scaled = combined.resize((new_w, new_h), Image.LANCZOS)
        paste_x = center_x - scaled.size[0] // 2
        paste_y = top_y
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        overlay.paste(scaled, (paste_x, paste_y), scaled)
        composited = Image.alpha_composite(image, overlay)
        image.paste(composited, (0, 0))

    disc_x = img_w // 2
    disc_y = img_h - margin - disc_base_size * 3
    bbox = draw.textbbox((0, 0), disc_txt, font=disc_font_small)
    _, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    disc_h = max(th * 2, int(img_h * 0.12))
    disc_rect_top = disc_y - 8
    disc_rect_bottom = min(img_h, disc_rect_top + disc_h)
    bg_style = disclaimer_bg_style or {}
    alpha = bg_style.get("alpha", 160)
    color = bg_style.get("color", [0, 0, 0])
    if isinstance(color, list):
        color = tuple(color[:3])
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle(
        [(0, disc_rect_top), (img_w, disc_rect_bottom)],
        fill=(*color, alpha),
    )
    composited = Image.alpha_composite(image, overlay)
    image.paste(composited, (0, 0))
    draw = ImageDraw.Draw(image)
    disc_max_w = int(img_w * 0.33)
    _draw_disclaimer_styled(
        disc_txt,
        disc_font,
        center_x=disc_x,
        top_y=disc_y,
        max_width=int(disc_max_w * 2),
        fill=(255, 255, 255, 255),
    )
    return disc_y, disc_rect_top


def get_text_zones_for_layout(
    img_width: int,
    img_height: int,
    layout_name: str,
    margin: int,
) -> List[Tuple[int, int, int, int]]:
    """
    Возвращает список зон (x1, y1, x2, y2), занятых текстом (заголовок, описание, дисклеймер).
    Пачка и логотип НЕ должны накладываться на эти зоны.
    Для classic_left: текст слева (~55% ширины), справа оставляем место для пачки.
    Для вертикальной ориентации (height > width): текст по всей ширине, компактнее по вертикали.
    """
    zones = []
    is_vertical = img_height > img_width
    h_zone_top = int(img_height * 0.25)
    desc_bottom = int(img_height * 0.72)
    disc_top = int(img_height * 0.82)

    if is_vertical:
        # Вертикальный баннер: текст занимает почти всю ширину, пачка — в углу
        text_right = img_width - margin
        zones.append((margin, margin, text_right, h_zone_top))
        zones.append((margin, h_zone_top, text_right, desc_bottom))
    else:
        text_right = int(img_width * 0.55)
        if "left" in layout_name:
            zones.append((margin, margin, text_right, h_zone_top))
            zones.append((margin, h_zone_top, text_right, desc_bottom))
        elif "right" in layout_name:
            text_left = int(img_width * 0.45)
            zones.append((text_left, margin, img_width - margin, h_zone_top))
            zones.append((text_left, h_zone_top, img_width - margin, desc_bottom))
        else:
            zones.append((margin, margin, img_width - margin, h_zone_top))
            zones.append((margin, h_zone_top, img_width - margin, desc_bottom))
    zones.append((margin, disc_top, img_width - margin, img_height - margin))
    return zones


def find_safe_product_position(
    img_width: int,
    img_height: int,
    text_zones: List[Tuple[int, int, int, int]],
    product_width: int,
    product_height: int,
    product_zones: Optional[List[Tuple[int, int, int, int]]] = None,
    preferred_region: Optional[str] = None,
) -> Optional[Tuple[int, int]]:
    """
    Находит позицию для пачки/логотипа, не пересекающуюся с текстом и другими продуктами.
    preferred_region: "top" — логотип, "bottom" — пачка (выше дисклеймера).
    """
    if product_zones is None:
        product_zones = []
    margin = 24
    # Продукт должен гарантированно помещаться внутри
    max_w = img_width - 2 * margin
    max_h = img_height - 2 * margin
    if product_width > max_w or product_height > max_h or product_width <= 0 or product_height <= 0:
        return None
    disc_top = int(img_height * 0.82)
    pack_bottom_y = disc_top - product_height - margin - 10
    pack_bottom_y = max(margin, min(pack_bottom_y, img_height - product_height - margin))
    top_candidates = [
        (img_width - product_width - margin, margin),
        (margin, margin),
        (int(img_width * 0.5 - product_width * 0.5), margin),
        (img_width - product_width - int(img_width * 0.02), int(img_height * 0.08)),
        (int(img_width * 0.02), int(img_height * 0.08)),
    ]
    bottom_candidates = [
        (img_width - product_width - margin, pack_bottom_y),
        (margin, pack_bottom_y),
        (int(img_width * 0.5 - product_width * 0.5), pack_bottom_y),
        (img_width - product_width - margin, img_height - product_height - margin),
        (margin, img_height - product_height - margin),
    ]
    neutral = [
        (int(img_width * 0.02), int(img_height * 0.35)),
        (img_width - product_width - int(img_width * 0.02), int(img_height * 0.35)),
    ]
    if preferred_region == "top":
        candidates = top_candidates + neutral + bottom_candidates
    elif preferred_region == "bottom":
        candidates = bottom_candidates + neutral + top_candidates
    else:
        candidates = top_candidates + bottom_candidates + neutral
    for px, py in candidates:
        px = max(margin, min(px, img_width - product_width - margin))
        py = max(margin, min(py, img_height - product_height - margin))
        rect = (px, py, px + product_width, py + product_height)
        overlaps = False
        for tz in text_zones:
            if _rects_overlap(rect, tz):
                overlaps = True
                break
        if overlaps:
            continue
        for pz in product_zones:
            if _rects_overlap(rect, pz):
                overlaps = True
                break
        if not overlaps:
            return (px, py)
    return None


def _draw_venue_badge(
    image: Image.Image,
    text: str,
    text_zones: List[Tuple[int, int, int, int]],
) -> Optional[Tuple[int, int, int, int]]:
    """
    Накладывает крафтовый бейдж (магазин, лаундж, лофт и т.д.) на свободную зону.
    Возвращает (x1, y1, x2, y2) бейджа или None.
    """
    try:
        cfg = _load_config()
        badges = cfg.get("venue_badges", ["ЛАУНДЖ", "КАЛЬЯННАЯ"])
        badge_text = text or random.choice(badges)
        img_w, img_h = image.size
        scale = min(img_w, img_h) / 1024
        font_size = max(18, int(28 * scale))
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()
        from PIL import ImageDraw
        bbox = ImageDraw.Draw(image).textbbox((0, 0), badge_text, font=font)
        pw = bbox[2] - bbox[0] + 24
        ph = bbox[3] - bbox[1] + 16
        pos = find_safe_product_position(img_w, img_h, text_zones, pw, ph, None, preferred_region="top")
        if not pos:
            return None
        badge = Image.new("RGBA", (pw, ph), (40, 40, 45, 200))
        draw = ImageDraw.Draw(badge)
        draw.rounded_rectangle([(0, 0), (pw - 1, ph - 1)], radius=8, outline=(200, 200, 200, 255), width=1)
        draw.text((12, 8), badge_text, font=font, fill=(255, 255, 255, 255))
        image.paste(badge, pos, badge)
        return (pos[0], pos[1], pos[0] + pw, pos[1] + ph)
    except Exception:
        return None


def _rects_overlap(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> bool:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return not (ax2 <= bx1 or ax1 >= bx2 or ay2 <= by1 or ay1 >= by2)


def _draw_venue_name_standalone(
    image: Image.Image,
    venue_name: str,
    text_zones: List[Tuple[int, int, int, int]],
) -> Optional[Tuple[int, int, int, int]]:
    """
    Рисует название магазина крафтовым шрифтом в свободной зоне (без бейджа).
    Для сценариев с пачками/логотипами, где нужна только вывеска магазина.
    Возвращает bbox (x1,y1,x2,y2) или None.
    """
    if not venue_name:
        return None
    try:
        img_w, img_h = image.size
        scale = min(img_w, img_h) / 1024
        font_size = max(36, int(90 * scale))
        font = get_cyrillic_craft_font(venue_name, font_size)
        draw = ImageDraw.Draw(image)
        tb = draw.textbbox((0, 0), venue_name, font=font)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
        pos = find_safe_product_position(
            img_w, img_h, text_zones, tw, th, None, preferred_region="top"
        )
        if not pos:
            pos = (max(24, img_w - tw - 24), 24)
        x, y = pos
        draw.text((x + 1, y + 1), venue_name, font=font, fill=(0, 0, 0, 200))
        draw.text((x, y), venue_name, font=font, fill=(255, 255, 255, 255))
        return (x, y, x + tw, y + th)
    except Exception:
        return None


def _draw_venue_name_under_badge(
    image: Image.Image,
    venue_name: str,
    badge_bbox: Tuple[int, int, int, int],
) -> None:
    """
    Рисует название заведения под крафтовым бейджем крафтовым шрифтом.
    """
    if not venue_name:
        return
    try:
        img_w, img_h = image.size
        x1, y1, x2, y2 = badge_bbox
        badge_w = x2 - x1
        badge_h = y2 - y1
        scale = min(img_w, img_h) / 1024
        # Название заметно крупнее бейджа (в 3–4 раза)
        font_size = max(36, int(90 * scale))
        font = get_cyrillic_craft_font(venue_name, font_size)
        draw = ImageDraw.Draw(image)
        tb = draw.textbbox((0, 0), venue_name, font=font)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
        margin_y = max(4, int(6 * scale))
        # Центруем по бейджу, потом ограничиваем внутри кадра
        text_x = int(x1 + badge_w / 2 - tw / 2)
        # Если строка слишком широкая — сдвигаем и подрезаем по полям
        margin_x = 10
        if text_x < margin_x:
            text_x = margin_x
        if text_x + tw > img_w - margin_x:
            text_x = max(margin_x, img_w - margin_x - tw)
        text_y = min(img_h - th - 10, y2 + margin_y)
        # Лёгкая тень для читаемости
        draw.text((text_x + 1, text_y + 1), venue_name, font=font, fill=(0, 0, 0, 200))
        draw.text((text_x, text_y), venue_name, font=font, fill=(255, 255, 255, 255))
    except Exception:
        return


def get_tobacco_brands_and_packs(cigarette_images_dir: Path) -> Dict[str, List[Path]]:
    """Возвращает {brand_name: [path1, path2, ...]} для папок с пачками (исключая logo)."""
    result = {}
    if not cigarette_images_dir.is_dir():
        return result
    for sub in cigarette_images_dir.iterdir():
        if not sub.is_dir() or sub.name.lower() == "logo":
            continue
        files = list(sub.glob("*.png")) + list(sub.glob("*.jpg")) + list(sub.glob("*.jpeg"))
        if files:
            result[sub.name] = files
    return result


def get_logo_for_brand(cigarette_images_dir: Path, brand_name: str) -> Optional[Path]:
    """Возвращает случайный путь к логотипу бренда, если есть."""
    logo_dir = cigarette_images_dir / "logo"
    if not logo_dir.is_dir():
        return None
    # Логотипы: BrandName_Number_hash.png
    pattern = f"{brand_name}_*"
    files = list(logo_dir.glob(pattern))
    if not files:
        return None
    return random.choice(files)


def _clamp_paste_position(
    pos: Tuple[int, int],
    product_w: int,
    product_h: int,
    img_w: int,
    img_h: int,
    margin: int = 10,
) -> Tuple[int, int]:
    """Гарантирует, что вставка не выходит за границы изображения."""
    x, y = pos
    x = max(margin, min(x, img_w - product_w - margin))
    y = max(margin, min(y, img_h - product_h - margin))
    return (x, y)


def _safe_paste(
    dest: Image.Image,
    src: Image.Image,
    pos: Tuple[int, int],
    img_w: int,
    img_h: int,
) -> None:
    """
    Вставляет src в dest в позицию pos, обрезая при необходимости.
    Гарантирует, что никакая часть не выходит за границы dest (img_w x img_h).
    """
    x, y = pos
    pw, ph = src.size
    # Сколько пикселей остаётся до границ
    max_w = max(0, img_w - x)
    max_h = max(0, img_h - y)
    if pw <= max_w and ph <= max_h:
        dest.paste(src, pos, src)
        return
    # Обрезаем src до допустимого размера
    crop_w = min(pw, max_w)
    crop_h = min(ph, max_h)
    if crop_w <= 0 or crop_h <= 0:
        return
    cropped = src.crop((0, 0, crop_w, crop_h))
    dest.paste(cropped, pos, cropped)


def apply_pack_and_logo(
    image: Image.Image,
    pack_path: Optional[Path],
    logo_path: Optional[Path],
    text_zones: List[Tuple[int, int, int, int]],
    max_pack_height_ratio: float = 0.35,
    max_logo_height_ratio: float = 0.15,
) -> Image.Image:
    """
    Накладывает пачку (внизу, выше дисклеймера) и логотип (вверху) на свободные зоны.
    Сначала логотип — в верхней части, затем пачка — в нижней.
    Для вертикальной ориентации — уменьшенные размеры и жёсткое ограничение по ширине.
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    img_w, img_h = image.size
    is_vertical = img_h > img_w
    margin = 24
    # Максимальные размеры продукта — жёстко внутри границ
    max_product_w = max(60, img_w - 2 * margin)
    max_product_h = max(80, img_h - 2 * margin)
    product_zones: List[Tuple[int, int, int, int]] = []

    if is_vertical:
        max_pack_height_ratio = 0.18
        max_logo_height_ratio = 0.08
        max_product_w = min(max_product_w, int(img_w * 0.4))

    # Логотип — в верхней части (преимущественно)
    if logo_path and logo_path.exists():
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            lw, lh = logo_img.size
            max_lh = min(int(img_h * max_logo_height_ratio), max_product_h)
            max_lw = min(max_product_w, int(img_w * 0.30))
            scale = min(max_lh / lh, max_lw / lw, 1.0)
            nw = max(1, min(int(lw * scale), max_product_w))
            nh = max(1, min(int(lh * scale), max_product_h))
            if is_vertical:
                nw = min(nw, img_w - 2 * margin)
                nh = min(nh, img_h - 2 * margin)
            logo_img = logo_img.resize((nw, nh), Image.LANCZOS)
            lw, lh = logo_img.size
            pos = find_safe_product_position(
                img_w, img_h, text_zones, lw, lh, product_zones, preferred_region="top"
            )
            if pos:
                pos = _clamp_paste_position(pos, lw, lh, img_w, img_h, margin)
                _safe_paste(image, logo_img, pos, img_w, img_h)
                product_zones.append((pos[0], pos[1], pos[0] + lw, pos[1] + lh))
        except Exception:
            pass

    # Пачка — в нижней части, выше дисклеймера
    if pack_path and pack_path.exists():
        try:
            pack_img = Image.open(pack_path).convert("RGBA")
            pw, ph = pack_img.size
            max_h = min(int(img_h * max_pack_height_ratio), max_product_h)
            max_w = min(max_product_w, int(img_w * 0.40) if is_vertical else int(img_w * 0.5))
            scale = min(max_h / ph, max_w / pw, 1.0)
            nw = max(1, min(int(pw * scale), max_product_w))
            nh = max(1, min(int(ph * scale), max_product_h))
            # Вертикальный формат: жёсткая гарантия в границах баннера
            if is_vertical:
                nw = min(nw, img_w - 2 * margin)
                nh = min(nh, img_h - 2 * margin)
            pack_img = pack_img.resize((nw, nh), Image.LANCZOS)
            pw, ph = pack_img.size
            pos = find_safe_product_position(
                img_w, img_h, text_zones, pw, ph, product_zones, preferred_region="bottom"
            )
            if pos:
                pos = _clamp_paste_position(pos, pw, ph, img_w, img_h, margin)
                _safe_paste(image, pack_img, pos, img_w, img_h)
        except Exception:
            pass

    return image


def build_tobacco_text_bundle(
    headline: Optional[str] = None,
    description: Optional[str] = None,
    disclaimer: Optional[str] = None,
    purpose: str = "advertising",
    product_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Собирает текст для баннера.
    product_type: "cigarettes" — сигареты/сигары (пачка+логотип),
                  "venues" — магазин/лаундж/кафе/клуб (бейдж),
                  "hookah" — кальян/кальянная, "vape" — вейпы, "smoking_mixes" — курительные смеси,
                  None — случайный выбор.
    purpose: "advertising" или "propaganda" (здоровый образ жизни без табака).
    """
    cfg = _load_config()
    if product_type is None:
        product_type = random.choice(["cigarettes", "venues", "hookah", "vape"])

    if purpose == "propaganda":
        hl = cfg.get("headlines_propaganda", cfg.get("headlines", []))
        desc = cfg.get("descriptions_propaganda", cfg.get("descriptions", []))
    elif product_type == "cigarettes":
        hl = cfg.get("headlines_cigarettes", cfg.get("headlines_advertising", cfg.get("headlines", [])))
        desc = cfg.get("descriptions_cigarettes", cfg.get("descriptions_advertising", cfg.get("descriptions", [])))
    elif product_type == "hookah":
        hl = cfg.get("headlines_hookah", cfg.get("headlines_venues", []))
        desc = cfg.get("descriptions_hookah", cfg.get("descriptions_venues", []))
    elif product_type == "vape":
        hl = cfg.get("headlines_vape", cfg.get("headlines_venues", []))
        desc = cfg.get("descriptions_vape", cfg.get("descriptions_venues", []))
    elif product_type == "smoking_mixes":
        hl = cfg.get("headlines_smoking_mixes", cfg.get("headlines_venues", []))
        desc = cfg.get("descriptions_smoking_mixes", cfg.get("descriptions_venues", []))
    else:
        hl = cfg.get("headlines_venues", cfg.get("headlines_advertising", []))
        desc = cfg.get("descriptions_venues", cfg.get("descriptions_advertising", []))

    disc = cfg.get("disclaimers_advertising" if purpose == "advertising" else "disclaimers_propaganda", cfg.get("disclaimers", []))
    return {
        "headline": headline or (random.choice(hl) if hl else "ТАБАК"),
        "description": description or (random.choice(desc) if desc else ""),
        "disclaimer": disclaimer or (random.choice(disc) if disc else "18+. Курение вредит здоровью."),
        "product_type": product_type,
    }


class TobaccoBannerOverlay:
    """Наложение текста на баннеры категории «табак»."""

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
        self.layout = layout or LAYOUTS[0] if LAYOUTS else {}
        self.style = _style_to_tuples(style or (styles[0] if styles else {}))
        self.disclaimer_bg_style = disclaimer_bg_style or (disc_styles[0] if disc_styles else {})

    def apply(
        self,
        image: Image.Image,
        headline: str,
        description: str,
        disclaimer: str,
        pack_path: Optional[Path] = None,
        logo_path: Optional[Path] = None,
        cigarette_images_dir: Optional[Path] = None,
        product_type: Optional[str] = None,
        venue_badge_text: Optional[str] = None,
        venue_name: Optional[str] = None,
        venue_address: Optional[str] = None,
        venue_hours: Optional[str] = None,
        venue_phone: Optional[str] = None,
    ) -> Image.Image:
        """
        Накладывает текст, затем:
        - product_type="cigarettes": пачку (внизу) и логотип (вверху) на свободные зоны
        - product_type="venues": крафтовый бейдж (магазин, лаундж, лофт и т.д.), без пачки/логотипа
        """
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        img_w, img_h = image.size
        margin = int(min(img_w, img_h) * 0.06)
        layout_name = self.layout.get("name", "classic_left")
        text_zones = get_text_zones_for_layout(img_w, img_h, layout_name, margin)

        draw = ImageDraw.Draw(image)
        scale = min(img_w, img_h) / self.REF_WIDTH
        font_sizes = {
            "headline": max(28, int(50 * scale)),
            # Описание делаем крупнее (примерно в 2 раза)
            "text": max(18, int(48 * scale)),
            "disclaimer": max(10, int(14 * scale)),
        }
        is_vertical = img_h > img_w
        # Максимальная ширина заголовка — не выходить за границы баннера
        headline_max_w = int(img_w * 0.9) if is_vertical else int(img_w * 0.5)
        safe_left, max_w = margin, headline_max_w
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
        except OSError:
            hl_font = ImageFont.load_default()

        # Для описаний используем надёжный системный шрифт с поддержкой кириллицы,
        # чтобы текст НИКОГДА не пропадал из-за ограничений craft-шрифтов.
        try:
            txt_font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                font_sizes["text"],
            )
        except OSError:
            txt_font = ImageFont.load_default()

        # Мелкий шрифт для адреса; размер условного «большого» дисклеймера — для смещения addr_y
        disc_base_size = font_sizes["disclaimer"]
        disc_font_size = disc_base_size * 2
        try:
            disc_font_small = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                disc_base_size,
            )
        except OSError:
            disc_font_small = ImageFont.load_default()

        def _draw_with_shadow(d, pos, text, font, color, shadow=(0, 0, 0)):
            x, y = pos
            d.text((x + 1, y + 1), text, font=font, fill=shadow)
            d.text((x, y), text, font=font, fill=color)

        def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> str:
            """
            Простая переноска строк по словам под max_width.
            """
            words = (text or "").split()
            if not words:
                return ""
            lines: List[str] = []
            cur: List[str] = []
            for w in words:
                test = (" ".join(cur + [w])).strip()
                bbox = draw.textbbox((0, 0), test, font=font)
                if bbox[2] - bbox[0] <= max_width or not cur:
                    cur.append(w)
                else:
                    lines.append(" ".join(cur))
                    cur = [w]
            if cur:
                lines.append(" ".join(cur))
            return "\n".join(lines)

        def _draw_multiline_centered(
            text: str,
            font: ImageFont.ImageFont,
            center_x: int,
            top_y: int,
            max_width: int,
            fill: tuple,
            shadow: tuple = (0, 0, 0, 200),
            line_gap: int = 4,
        ) -> Tuple[int, int]:
            wrapped = _wrap_text(text, font, max_width)
            if not wrapped:
                return (0, 0)
            lines = wrapped.split("\n")
            widths = []
            heights = []
            for ln in lines:
                b = draw.textbbox((0, 0), ln, font=font)
                widths.append(b[2] - b[0])
                heights.append(b[3] - b[1])
            lh = max(1, max(heights))
            y = top_y
            for i, ln in enumerate(lines):
                tw = widths[i]
                x = int(center_x - tw / 2)
                _draw_with_shadow(draw, (x, y), ln, font, fill, shadow=shadow)
                y += lh + line_gap
            return (max(widths), y - top_y)

        hl_y = margin
        # Заголовок с переносом — чтобы не выходил за границы (особенно для вертикального формата)
        wrapped_headline = _wrap_text(headline, hl_font, headline_max_w)
        for i, line in enumerate(wrapped_headline.split("\n")):
            line_y = hl_y + i * (font_sizes["headline"] + 4)
            _draw_with_shadow(draw, (safe_left, line_y), line, hl_font, hl_color)
        # Описание: левая колонка, с переносами. Для вертикального — шире (85% ширины)
        desc_y = int(img_h * 0.35)
        desc_max_w = int(img_w * 0.85) if is_vertical else int(img_w * 0.33)
        if description:
            wrapped_desc = _wrap_text(description, txt_font, desc_max_w)
            for i, line in enumerate(wrapped_desc.split("\n")):
                line_y = desc_y + i * (font_sizes["text"] + 4)
                _draw_with_shadow(draw, (safe_left, line_y), line, txt_font, txt_color)

        disc_x = img_w // 2
        has_disclaimer_text = bool(disclaimer and str(disclaimer).strip())
        disc_rect_top = img_h - margin
        disc_y = img_h - margin * 2
        if has_disclaimer_text:
            disc_y, disc_rect_top = paint_styled_footer_disclaimer(
                image,
                disclaimer,
                self.disclaimer_bg_style,
                self.REF_WIDTH,
            )
            draw = ImageDraw.Draw(image)

        # Адрес и телефон (если есть) — под дисклеймером обычным шрифтом
        if venue_address or venue_phone:
            addr_font = disc_font_small
            if has_disclaimer_text:
                addr_y = disc_y + int(disc_font_size * 2.2)  # под увеличенным дисклеймером
            else:
                addr_y = max(margin, img_h - margin - 48)
            lines = []
            if venue_address:
                lines.append(venue_address)
            if venue_phone:
                lines.append(f"Тел.: {venue_phone}")
            addr_text = "\n".join(lines)
            _draw_multiline_centered(
                addr_text,
                addr_font,
                center_x=disc_x,
                top_y=addr_y,
                max_width=int(img_w * 0.7),
                fill=(255, 255, 255, 255),
            )

        # Бейдж "Часы работы" над дисклеймером
        if venue_hours:
            template = random.choice(HOURS_PHRASES)
            hours_text = template.replace("[время]", venue_hours or "").replace("[time]", venue_hours or "")
            badge_font_size = max(18, int(26 * scale))
            badge_img = create_oval_promotional_badge(hours_text, font_size=badge_font_size)
            bw, bh = badge_img.size
            bx = max(0, int(disc_x - bw / 2))
            by = max(0, int(disc_rect_top - bh - 10))
            image.paste(badge_img, (bx, by), badge_img)

        venue_types = ("venues", "hookah", "vape", "smoking_mixes")
        if product_type in venue_types and (venue_badge_text or venue_name):
            bbox = _draw_venue_badge(image, venue_badge_text, text_zones)
            if bbox and venue_name:
                _draw_venue_name_under_badge(image, venue_name, bbox)
        elif product_type == "discreditation":
            # Крафт (бейдж / название) рисуется в discreditation_overlay, не здесь
            pass
        elif product_type == "propaganda":
            pass
        else:
            zones_for_pack = list(text_zones)
            if venue_name:
                venue_bbox = _draw_venue_name_standalone(image, venue_name, text_zones)
                if venue_bbox:
                    zones_for_pack.append(venue_bbox)
            pack_to_use = pack_path
            logo_to_use = logo_path
            if cigarette_images_dir and (not pack_to_use or not logo_to_use):
                brands = get_tobacco_brands_and_packs(Path(cigarette_images_dir))
                if brands:
                    brand = random.choice(list(brands.keys()))
                    packs = brands[brand]
                    if not pack_to_use and packs:
                        pack_to_use = random.choice(packs)
                    if not logo_to_use:
                        logo_to_use = get_logo_for_brand(Path(cigarette_images_dir), brand)
            image = apply_pack_and_logo(image, pack_to_use, logo_to_use, zones_for_pack)
        return image


if __name__ == "__main__":
    print("Tobacco overlay module. Use tobacco_composition_with_products.py for generation.")
