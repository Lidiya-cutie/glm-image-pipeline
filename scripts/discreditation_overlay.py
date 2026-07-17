#!/usr/bin/env python3
"""
Оверлей для категории «дискредитация» (модерация / учебные макеты).

Архитектура как у табака:
- заголовок, описание, дисклеймер (типографика TobaccoBannerOverlay);
- опционально бейдж (venue_badges), крафтовое имя заведения, часы, адрес/телефон;
- без пачек и логотипов сигарет.

Крафтовое имя: get_cyrillic_craft_font(); при кириллице — только шрифты с нормальными глифами, иначе
DejaVu Sans Bold. Фактический путь: tobacco_overlay.LAST_CRAFT_FONT_PATH_USED или
DISCREDITATION_DEBUG_CRAFT_FONT=1 в окружении (stderr). Текст бейджа — DejaVu Bold.

Пулы текстов: плоский массив (как табак) или categories/items (как народная медицина).
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.tobacco_overlay import (
    TobaccoBannerOverlay,
    _style_to_tuples,
    get_cyrillic_craft_font,
    paint_styled_footer_disclaimer,
)

CONFIG_PATH = PROJECT_ROOT / "configs" / "discreditation_config.json"

_config_cache: Optional[Dict[str, Any]] = None

try:
    from scripts.text_overlay import LAYOUTS, get_layout_by_name
except ImportError:
    LAYOUTS = [{"name": "classic_left"}]

    def get_layout_by_name(name: str) -> Dict[str, Any]:
        for L in LAYOUTS:
            if L.get("name") == name:
                return L
        return LAYOUTS[0]


def _load_config() -> Dict[str, Any]:
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    if not CONFIG_PATH.is_file():
        _config_cache = {}
        return _config_cache
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        _config_cache = json.load(f)
    return _config_cache


def reload_config() -> None:
    global _config_cache
    _config_cache = None
    _load_config()


def load_scenarios() -> List[Dict[str, Any]]:
    cfg = _load_config()
    return list(cfg.get("scenarios") or [])


# Дополнение к prompt при SDXL: детализация материалов, света, ракурса (поле prompt в сценарии не меняется).
DEFAULT_PROMPT_DETAIL_SUFFIX = (
    "Additional rendering specification (keep the same subject as the main prompt; add material and lighting fidelity only). "
    "(1) Background and textiles: visible fabric weave; cordura or ripstop grain where military cloth appears; "
    "dense embroidery thread texture; optional white topstitch along rectangular patch edges; slight fold tension. "
    "(2) Patches and appliqués when present: morale-patch proportions, gently rounded corners, thread-embroidered letters "
    "with crisp readable Cyrillic if the scene includes fabric text; slightly irregular brush- or chalk-like edges on painted marks. "
    "(3) Ribbons and wide stripes: preserve hue separation already stated in the main prompt; soft highlights and occluding shadows on folds. "
    "(4) Lighting: soft key from above or upper-left, mild falloff, micro-shadows that reveal stitch height and surface relief. "
    "(5) Camera: macro or mild top-down angle for insignia studies; documentary or cinematic framing for environmental shots; "
    "shallow depth of field when a single object must dominate. "
    "(6) Output quality: photorealistic, 8k, high micro-detail, natural noise, no watermark; no extra overlaid lettering "
    "unless the main prompt explicitly asks for mock broadcast or poster typography."
)


def compose_sdxl_prompt(
    scenario: Dict[str, Any],
    *,
    use_detail_suffix: bool = True,
) -> str:
    """
    Собирает строку для SDXL: исходный scenario['prompt'] + опционально prompt_detail_suffix из конфига.
    Пустой или отсутствующий suffix в конфиге — используется DEFAULT_PROMPT_DETAIL_SUFFIX;
    suffix \"\" в конфиге отключает добавку (если use_detail_suffix).
    """
    base = str(scenario.get("prompt") or "").strip()
    if not base or not use_detail_suffix:
        return base
    cfg = _load_config()
    raw = cfg.get("prompt_detail_suffix")
    if raw is None:
        suffix = DEFAULT_PROMPT_DETAIL_SUFFIX
    else:
        suffix = str(raw).strip()
        if not suffix:
            return base
    return f"{base} {suffix}".strip()


def _flatten_text_pool(cfg: Dict[str, Any], key: str) -> List[str]:
    """
    Табак: "headlines": [ ... ]
    Народная медицина: "headlines": { "categories": { "cat": { "items": [...] } } }
    """
    raw = cfg.get(key)
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]
    if isinstance(raw, dict):
        items: List[str] = []
        cats = raw.get("categories") or {}
        for c in cats.values():
            if isinstance(c, dict):
                for it in c.get("items") or []:
                    s = str(it).strip()
                    if s:
                        items.append(s)
        return items
    return []


def build_discreditation_text_bundle(
    headline: Optional[str] = None,
    description: Optional[str] = None,
    disclaimer: Optional[str] = None,
    scenario: Optional[Dict[str, Any]] = None,
    *,
    no_disclaimer: bool = False,
) -> Dict[str, str]:
    """
    Тексты только из глобальных пулов конфига (как tobacco_config) или из аргументов CLI.
    Сценарий не содержит headline/description/disclaimer.
    no_disclaimer=True — не брать дисклеймер из пула (пустая строка, без полосы в оверлее).
    """
    cfg = _load_config()
    hl_pool = _flatten_text_pool(cfg, "headlines")
    desc_pool = _flatten_text_pool(cfg, "descriptions")
    disc_pool = _flatten_text_pool(cfg, "disclaimers")

    h = "" if headline is None else str(headline)
    if not (h and str(h).strip()) and hl_pool:
        h = random.choice(hl_pool)
    h = str(h or "")

    d = "" if description is None else str(description)
    if not (d and str(d).strip()) and desc_pool:
        d = random.choice(desc_pool)
    d = str(d or "")

    if no_disclaimer:
        disc = ""
    else:
        disc = "" if disclaimer is None else str(disclaimer)
        if not (disc and str(disc).strip()) and disc_pool:
            disc = random.choice(disc_pool)
        disc = str(disc or "")

    return {
        "headline": h,
        "description": d,
        "disclaimer": disc,
    }


def _nonempty(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = str(s).strip()
    return s if s else None


def resolve_discreditation_venue_fields(
    scenario: Dict[str, Any],
    cfg: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Пресеты заведений — в venue_presets[] (как выборка магазинов из JSON для табака).
    Сценарий может задать venue_preset_index (число) или venue_preset_name (строка).
    Иначе при непустом venue_presets — случайный пресет.
    Бейдж без пресета: случайный из venue_badges (если список не пуст).
    """
    sc = scenario
    presets = [p for p in (cfg.get("venue_presets") or []) if isinstance(p, dict)]
    preset: Optional[Dict[str, Any]] = None

    idx = sc.get("venue_preset_index")
    if idx is not None and isinstance(idx, int) and 0 <= idx < len(presets):
        preset = presets[idx]

    pname = sc.get("venue_preset_name")
    if preset is None and pname is not None and str(pname).strip():
        for p in presets:
            if str(p.get("name", "")).strip() == str(pname).strip():
                preset = p
                break

    if preset is None and presets:
        preset = random.choice(presets)

    badge = _nonempty((preset or {}).get("venue_badge_text"))
    name = _nonempty((preset or {}).get("venue_name"))
    address = _nonempty((preset or {}).get("venue_address"))
    hours = _nonempty((preset or {}).get("venue_hours"))
    phone = _nonempty((preset or {}).get("venue_phone"))

    badges_only = [_nonempty(x) for x in (cfg.get("venue_badges") or [])]
    badges_only = [x for x in badges_only if x]
    if badge is None and badges_only:
        badge = random.choice(badges_only)

    return badge, name, address, hours, phone


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    b = draw.textbbox((0, 0), text, font=font)
    return max(0, b[2] - b[0])


def _split_long_word(
    word: str,
    font: ImageFont.ImageFont,
    max_w: int,
    draw: ImageDraw.ImageDraw,
) -> List[str]:
    """Разбивает одно слово, если оно шире max_w (узкий вертикальный баннер)."""
    if not word or _text_width(draw, word, font) <= max_w:
        return [word] if word else []
    parts: List[str] = []
    chunk = ""
    for ch in word:
        test = chunk + ch
        if _text_width(draw, test, font) <= max_w:
            chunk = test
        else:
            if chunk:
                parts.append(chunk)
            chunk = ch
    if chunk:
        parts.append(chunk)
    return parts if parts else [word[:1]]


def _wrap_venue_lines(
    text: str,
    font: ImageFont.ImageFont,
    max_w: int,
    draw: ImageDraw.ImageDraw,
) -> List[str]:
    words = (text or "").split()
    if not words:
        return []
    lines: List[str] = []
    cur: List[str] = []
    for w in words:
        pieces = _split_long_word(w, font, max_w, draw)
        for i, piece in enumerate(pieces):
            if i < len(pieces) - 1:
                if cur:
                    lines.append(" ".join(cur))
                    cur = []
                lines.append(piece)
                continue
            test = (" ".join(cur + [piece])).strip()
            if not test:
                continue
            if not cur or _text_width(draw, test, font) <= max_w:
                cur.append(piece)
            else:
                lines.append(" ".join(cur))
                cur = [piece]
    if cur:
        lines.append(" ".join(cur))
    return lines


def _name_block_height(
    lines: List[str],
    font: ImageFont.ImageFont,
    line_gap: int,
    draw: ImageDraw.ImageDraw,
) -> int:
    if not lines:
        return 0
    h = 0
    for j, ln in enumerate(lines):
        b = draw.textbbox((0, 0), ln, font=font)
        h += b[3] - b[1]
        if j < len(lines) - 1:
            h += line_gap
    return h


def _build_badge_patch(
    label: str,
    font_size: int,
) -> Tuple[Image.Image, int, int]:
    try:
        bfont = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size
        )
    except OSError:
        bfont = ImageFont.load_default()
    tmp = Image.new("RGBA", (200, 48), (0, 0, 0, 0))
    draw0 = ImageDraw.Draw(tmp)
    bb = draw0.textbbox((0, 0), label, font=bfont)
    badge_pw = bb[2] - bb[0] + 24
    badge_ph = bb[3] - bb[1] + 16
    badge_patch = Image.new("RGBA", (badge_pw, badge_ph), (40, 40, 45, 200))
    bd = ImageDraw.Draw(badge_patch)
    bd.rounded_rectangle(
        [(0, 0), (badge_pw - 1, badge_ph - 1)],
        radius=8,
        outline=(200, 200, 200, 255),
        width=1,
    )
    bd.text((12, 8), label, font=bfont, fill=(255, 255, 255, 255))
    return badge_patch, badge_pw, badge_ph


def _draw_discreditation_footer_craft(
    image: Image.Image,
    venue_badge_text: Optional[str],
    venue_name: Optional[str],
) -> None:
    """
    Бейдж и крафтовое название в нижней полосе (зона дисклеймера), по центру.
    Для вертикального формата: перенос строк и уменьшение шрифта, без выхода за края.
    """
    if not venue_badge_text and not venue_name:
        return
    try:
        img_w, img_h = image.size
        margin = int(min(img_w, img_h) * 0.06)
        max_w = max(24, img_w - 2 * margin)
        max_stack_h = max(1, img_h - 2 * margin)
        scale = min(img_w, img_h) / 1024
        cx = img_w // 2
        gap = max(6, int(10 * scale))
        draw = ImageDraw.Draw(image)
        is_vertical = img_h > img_w

        badge_patch: Optional[Image.Image] = None
        badge_pw = badge_ph = 0
        if venue_badge_text:
            bf = max(10, int(26 * scale)) if is_vertical else max(18, int(28 * scale))
            while bf >= 10:
                badge_patch, badge_pw, badge_ph = _build_badge_patch(venue_badge_text, bf)
                if badge_pw <= max_w:
                    break
                bf -= 2
            if badge_patch is not None and badge_pw > max_w:
                badge_patch = None
                badge_pw = badge_ph = 0

        name_font: Optional[ImageFont.ImageFont] = None
        name_lines: List[str] = []
        line_gap = max(2, int(5 * scale))
        if venue_name:
            cap = min(scale, img_w / 1024)
            high = max(22, int(72 * cap)) if is_vertical else max(36, int(90 * scale))
            low = 14
            best_lines: List[str] = []
            for fs in range(int(high), low - 1, -2):
                f = get_cyrillic_craft_font(venue_name, fs)
                lines = _wrap_venue_lines(venue_name, f, max_w, draw)
                nh = _name_block_height(lines, f, line_gap, draw)
                extra = (badge_ph + gap) if badge_patch else 0
                if nh + extra <= max_stack_h:
                    name_font = f
                    name_lines = lines
                    break
                best_lines = lines
                name_font = f
            if name_lines == [] and name_font is not None:
                name_lines = best_lines or _wrap_venue_lines(venue_name, name_font, max_w, draw)

        g = gap if (badge_patch is not None and name_lines and name_font is not None) else 0
        name_h = _name_block_height(name_lines, name_font, line_gap, draw) if name_font else 0
        total_h = (badge_ph if badge_patch else 0) + g + name_h
        if total_h <= 0:
            return
        stack_top = max(margin, img_h - margin - total_h)

        if badge_patch is not None:
            bx = int(cx - badge_pw / 2)
            bx = max(margin, min(bx, img_w - margin - badge_pw))
            image.paste(badge_patch, (bx, stack_top), badge_patch)
        if name_font is not None and name_lines:
            ny = stack_top + badge_ph + g
            for ln in name_lines:
                if ny >= img_h - margin:
                    break
                tw = _text_width(draw, ln, name_font)
                th_line = draw.textbbox((0, 0), ln, font=name_font)[3] - draw.textbbox(
                    (0, 0), ln, font=name_font
                )[1]
                tx = int(cx - tw / 2)
                tx = max(margin, min(tx, img_w - margin - tw))
                draw.text((tx + 1, ny + 1), ln, font=name_font, fill=(0, 0, 0, 200))
                draw.text((tx, ny), ln, font=name_font, fill=(255, 255, 255, 255))
                ny += th_line + line_gap
    except Exception:
        return


def apply_discreditation_overlay(
    image: Image.Image,
    bundle: Dict[str, str],
    scenario: Optional[Dict[str, Any]] = None,
    layout: Optional[Dict[str, Any]] = None,
    style: Optional[Dict[str, Any]] = None,
    disclaimer_bg_style: Optional[Dict[str, Any]] = None,
) -> Image.Image:
    cfg = _load_config()
    sc = scenario or {}
    styles = cfg.get("styles") or []
    disc_styles = cfg.get("disclaimer_bg_styles") or []
    st = _style_to_tuples(style or (styles[0] if styles else {}))
    dst = disclaimer_bg_style or (disc_styles[0] if disc_styles else {})
    lay = layout or (LAYOUTS[0] if LAYOUTS else {})

    vb, vn, vaddr, vhours, vphone = resolve_discreditation_venue_fields(sc, cfg)

    overlay = TobaccoBannerOverlay(layout=lay, style=st, disclaimer_bg_style=dst)
    out = overlay.apply(
        image,
        headline=bundle["headline"],
        description=bundle["description"],
        disclaimer=bundle["disclaimer"],
        pack_path=None,
        logo_path=None,
        cigarette_images_dir=None,
        product_type="discreditation",
        venue_badge_text=None,
        venue_name=None,
        venue_address=vaddr,
        venue_hours=vhours,
        venue_phone=vphone,
    )
    _draw_discreditation_footer_craft(out, vb, vn)
    # Дисклеймер снова поверх крафта — та же вёрстка, что у табака (полоса + текст).
    disc_draw = (bundle.get("disclaimer") or "").strip()
    if disc_draw:
        paint_styled_footer_disclaimer(
            out, bundle["disclaimer"], dst, TobaccoBannerOverlay.REF_WIDTH
        )
    return out


if __name__ == "__main__":
    print("discreditation_overlay: используйте generate_discreditation_banners.py")
