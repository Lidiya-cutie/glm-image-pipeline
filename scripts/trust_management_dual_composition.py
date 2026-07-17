#!/usr/bin/env python3
"""
Скрипт создания композитных баннеров доверительного управления из двух изображений с QR-кодами.
Поддерживает форматы: квадрат 1024x1024, горизонтальный 1200x700, вертикальный 800x1200.
15+ формулировок текста в соответствии со ст. 28 ФЗ-38.
"""

import argparse
import sys
import random
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageStat
from typing import List, Tuple, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.trust_management_overlay import (
    TrustManagementBannerOverlay,
    get_random_content,
    get_random_company,
    TRUST_MANAGEMENT_STYLES,
    TRUST_MANAGEMENT_HEADLINES,
    TRUST_MANAGEMENT_DESCRIPTIONS,
    TRUST_MANAGEMENT_DISCLAIMERS,
    DISCLAIMER_BG_STYLES,
    generate_phone,
)
from scripts.text_overlay import TextRenderer
from scripts.folk_dual_composition import (
    DualCompositionEngine,
    find_safe_qr_position,
)

# QR pipeline (optional)
try:
    from scripts.generate_folk_medicine_with_qr_2 import FolkMedicineQRPipeline
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

# Форматы баннеров
BANNER_FORMATS = {
    "square": (1024, 1024),
    "horizontal": (1200, 700),
    "vertical": (800, 1200),
}

# URL по умолчанию для QR (доверительное управление)
DEFAULT_QR_URL = "https://www.example.ru/trust-management"


def get_company_qr_url(company: Optional[Dict[str, str]] = None) -> str:
    """Возвращает URL для QR-кода из данных компании."""
    if company and company.get("website"):
        url = company["website"]
        # Убеждаемся, что URL начинается с http/https
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url
    return DEFAULT_QR_URL


def get_layout_by_name(name: str) -> Dict:
    from scripts.text_overlay import LAYOUTS
    for layout in LAYOUTS:
        if layout["name"] == name:
            return layout
    return LAYOUTS[0]


def apply_trust_management_text(
    image: Image.Image,
    headline: str,
    description: str,
    phone: str,
    disclaimer: str,
    legal_entity: str,
    source_info: str,
    layout_name: str,
    style: Dict,
    background_zones: List[Tuple[int, int, int, int]],
    num_backgrounds: int = 2,
    is_horizontal: bool = True,
) -> Image.Image:
    """Накладывает текст доверительного управления с учётом зон фонов."""
    if not isinstance(background_zones, list):
        background_zones = []
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    w, h = image.size
    REF_WIDTH = 1024
    scale = min(w, h) / REF_WIDTH

    renderer = TextRenderer(
        style,
        headline_size=int(58 * scale),
        text_size=int(26 * scale),
        phone_size=int(38 * scale),
        disclaimer_size=int(12 * scale),
    )
    draw = ImageDraw.Draw(image)
    margin = int(w * 0.06)
    text_width = int(w * 0.45 if num_backgrounds == 2 else w * 0.6)

    # Определяем позицию текста
    if len(background_zones) > 0:
        if num_backgrounds == 1:
            bg_x1, bg_y1, bg_x2, bg_y2 = background_zones[0]
            bg_center_x = (bg_x1 + bg_x2) / 2
            if bg_center_x < w / 2:
                base_x = int(w * 0.65)
                align = "right"
            else:
                base_x = int(w * 0.35)
                align = "left"
        else:
            base_x = w // 2
            align = "center"
    else:
        if "right" in layout_name:
            base_x = w - margin
            align = "right"
        elif "left" in layout_name:
            base_x = margin
            align = "left"
        else:
            base_x = w // 2
            align = "center"

    # Заголовок
    headline_y = int(h * 0.15)
    renderer.draw_text_with_shadow(
        draw, (base_x, headline_y), headline,
        renderer.headline_font, style["headline_color"],
        align=align, max_width=text_width,
    )

    # Описание + юрлицо + источник
    full_desc = f"{legal_entity}\n{description}\n{source_info}"
    desc_y = headline_y + int(58 * scale * 1.5) + int(h * 0.03)
    renderer.draw_text_with_shadow(
        draw, (base_x, desc_y), full_desc,
        renderer.text_font, style["text_color"],
        align=align, max_width=text_width,
    )

    # Телефон
    phone_y = int(h * 0.55)
    renderer.draw_text_with_shadow(
        draw, (base_x, phone_y), phone,
        renderer.phone_font, style["headline_color"],
        align=align,
    )

    # Дисклеймер
    disc_style = random.choice(DISCLAIMER_BG_STYLES)
    disc_y = h - 90
    adj_y = max(0, h - int((h - disc_y + 10) * disc_style.get("height_multiplier", 1.0)))
    bg_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    disc_draw = ImageDraw.Draw(bg_layer)
    if disc_style.get("type", "solid") == "solid":
        disc_draw.rectangle(
            [0, adj_y, w, h],
            fill=(*disc_style.get("color", (0, 0, 0)), disc_style.get("alpha", 150)),
        )
    image = Image.alpha_composite(image, bg_layer)
    draw = ImageDraw.Draw(image)
    renderer.draw_text_with_shadow(
        draw, (w // 2, h - 65), disclaimer,
        renderer.disclaimer_font, (255, 255, 255),
        align="center", max_width=int(w * 0.9),
    )
    return image


def generate_qr_image(url: str = None, company: Optional[Dict[str, str]] = None) -> Optional[Image.Image]:
    """Генерирует QR-код (если доступен пайплайн)."""
    if not QR_AVAILABLE:
        return None
    try:
        pipeline = FolkMedicineQRPipeline(device="cpu")
        qr_type = random.choice(["simple", "artistic_white", "custom_color"])
        # Используем сайт компании, если доступен
        qr_url = url or get_company_qr_url(company) or DEFAULT_QR_URL
        return pipeline.generate_qr_variety(qr_url, qr_type=qr_type)
    except Exception:
        return None


def process_batch(
    input_dir: str,
    output_dir: str,
    count: int = 10,
    format_name: str = "horizontal",
    qr_chance: float = 60,
    qr_url: str = None,
):
    in_path = Path(input_dir)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    w, h = BANNER_FORMATS.get(format_name, (1200, 700))

    images = list(in_path.glob("*.png")) + list(in_path.glob("*.jpg"))
    if len(images) < 2:
        print("Ошибка: В папке должно быть минимум 2 изображения")
        return

    for i in range(count):
        pair = random.sample(images, 2)
        engine = DualCompositionEngine(w, h)
        is_horizontal = w > h
        composed_img, layout_type, background_zones, num_backgrounds = engine.compose(
            pair[0], pair[1], shape=random.choice(["circle", "square"]), auto_bg=True
        )
        if not isinstance(background_zones, list):
            background_zones = []

        # Используем реальные компании
        company = get_random_company()
        content = get_random_content(use_real_companies=True)
        style = random.choice(TRUST_MANAGEMENT_STYLES)
        headline = content["headline"]
        description = content["description"]
        disclaimer = random.choice(TRUST_MANAGEMENT_DISCLAIMERS)
        legal_entity = content["legal_entity"]
        source_info = content["source_info"]
        phone = content.get("phone") or generate_phone()
        website = content.get("website", "")

        try:
            final_banner = apply_trust_management_text(
                composed_img.copy(),
                headline=headline,
                description=description,
                phone=phone,
                disclaimer=disclaimer,
                legal_entity=legal_entity,
                source_info=source_info,
                layout_name=layout_type,
                style=style,
                background_zones=background_zones,
                num_backgrounds=num_backgrounds,
                is_horizontal=is_horizontal,
            )

            # QR (используем сайт компании)
            if random.random() * 100 < qr_chance:
                qr_url_to_use = qr_url or website or (company["website"] if company else None)
                qr_img = generate_qr_image(qr_url_to_use, company=company)
                if qr_img is not None:
                    qr_size = 100
                    qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS).convert("RGBA")
                    text_zones = []
                    qr_pos = find_safe_qr_position(w, h, background_zones, text_zones, qr_size)
                    final_banner.paste(qr_img, qr_pos, qr_img)

            ts = int(time.time() * 1000)
            fn = f"trust_dual_{format_name}_{i:03d}_{ts}.png"
            final_banner.save(out_path / fn, quality=95)
            print(f"[{i+1}/{count}] Создан: {fn}")
        except Exception as e:
            print(f"Ошибка при создании баннера {i}: {e}")
            import traceback
            traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="Trust Management Dual Composition + QR")
    parser.add_argument("--input-dir", type=str, required=True, help="Папка с фоновыми изображениями")
    parser.add_argument("--output", type=str, default="output/trust_management_dual")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--format", type=str, choices=list(BANNER_FORMATS), default="horizontal")
    parser.add_argument("--qr-chance", type=float, default=60, help="Вероятность добавления QR (0-100)")
    parser.add_argument("--qr-url", type=str, default=None, help="URL для QR-кода")
    args = parser.parse_args()

    process_batch(
        input_dir=args.input_dir,
        output_dir=args.output,
        count=args.count,
        format_name=args.format,
        qr_chance=args.qr_chance,
        qr_url=args.qr_url,
    )


if __name__ == "__main__":
    main()
