#!/usr/bin/env python3
"""
Композиция баннеров категории «табак» с наложением пачек сигарет/сигар и логотипов.

Использует:
- /mldata/glm-image-pipeline/cigarette_images — папки с изображениями пачек по маркам
- cigarette_images/logo — логотипы к маркам (накладываются при наличии)
- Пачка и логотип накладываются ТОЛЬКО на зоны, свободные от текста (заголовок, описание, дисклеймер)
"""

import argparse
import random
import sys
import time
from pathlib import Path

from PIL import Image, ImageStat, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.tobacco_overlay import (
    TobaccoBannerOverlay,
    build_tobacco_text_bundle,
    get_tobacco_brands_and_packs,
    get_logo_for_brand,
    get_random_tobacco_venue_name,
    get_random_tobacco_venue,
)
from scripts.tobacco_overlay import _load_config

CIGARETTE_IMAGES_DIR = PROJECT_ROOT / "cigarette_images"

BANNER_FORMATS = {"square": (1024, 1024), "horizontal": (1200, 700), "vertical": (800, 1200)}


def get_average_color(img: Image.Image) -> tuple:
    if img.mode != "RGB":
        img = img.convert("RGB")
    stat = ImageStat.Stat(img)
    return tuple(map(int, stat.median[:3]))


def pastel_from_color(rgb: tuple) -> tuple:
    r, g, b = rgb
    return (
        min(255, int(r + (255 - r) * 0.85)),
        min(255, int(g + (255 - g) * 0.85)),
        min(255, int(b + (255 - b) * 0.85)),
    )


def create_background_from_image(
    pack_path: Path,
    width: int,
    height: int,
) -> Image.Image:
    """Создаёт пастельный фон по среднему цвету пачки."""
    pack_img = Image.open(pack_path).convert("RGB")
    avg = get_average_color(pack_img)
    bg_color = pastel_from_color(avg)
    return Image.new("RGBA", (width, height), (*bg_color, 255))


def create_solid_background(width: int, height: int) -> Image.Image:
    """Нейтральный тёмный или светлый фон."""
    colors = [(240, 238, 235), (45, 45, 50), (60, 55, 50)]
    bg = random.choice(colors)
    return Image.new("RGBA", (width, height), (*bg, 255))


def main():
    parser = argparse.ArgumentParser(
        description="Композиция табак: фон + текст + пачка и логотип из cigarette_images (только на свободные зоны)"
    )
    parser.add_argument("--cigarette-images-dir", type=str, default=str(CIGARETTE_IMAGES_DIR),
                        help="Директория с папками марок и logo")
    parser.add_argument("--brand", type=str, help="Конкретная марка (иначе случайная)")
    parser.add_argument("--no-pack", action="store_true", help="Не накладывать пачку")
    parser.add_argument("--no-logo", action="store_true", help="Не накладывать логотип")
    parser.add_argument("--output", type=str, default="output/tobacco_composition")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--format", type=str, choices=list(BANNER_FORMATS.keys()), default="horizontal")
    parser.add_argument("--purpose", type=str, choices=["advertising", "propaganda"], default="advertising")
    parser.add_argument("--headline", type=str)
    parser.add_argument("--description", type=str)
    parser.add_argument("--disclaimer", type=str)
    parser.add_argument("--product-type", type=str,
                        choices=["cigarettes", "venues", "hookah", "vape", "smoking_mixes", "propaganda"],
                        default=None,
                        help="cigarettes=пачка+логотип, venues/hookah/vape/smoking_mixes=бейдж, propaganda=ЗОЖ")
    args = parser.parse_args()

    cig_dir = Path(args.cigarette_images_dir)
    brands = {}
    if cig_dir.is_dir():
        brands = get_tobacco_brands_and_packs(cig_dir)
    needs_packs = args.product_type == "cigarettes" or (args.product_type is None)
    if needs_packs and not brands:
        print(f"Предупреждение: директория {cig_dir} не найдена. Используйте --product-type venues|hookah|vape для бейджей.")
        if args.product_type is None:
            args.product_type = "venues"

    w, h = BANNER_FORMATS[args.format]
    out_path = Path(args.output)
    out_path.mkdir(parents=True, exist_ok=True)

    cfg = _load_config()
    styles = cfg.get("styles", [])
    disc_styles = cfg.get("disclaimer_bg_styles", [])
    style = styles[0] if styles else {}
    disc_style = disc_styles[0] if disc_styles else {}

    pt = args.product_type
    print(f"Генерация {args.count} баннеров (product_type={pt or 'авто'})")
    for i in range(args.count):
        bundle = build_tobacco_text_bundle(
            headline=args.headline,
            description=args.description,
            disclaimer=args.disclaimer,
            purpose=args.purpose,
            product_type=pt,
        )
        product_type = bundle["product_type"]

        pack_path = None
        logo_path = None
        brand = "venue"
        if product_type == "cigarettes" and brands:
            brand = args.brand if args.brand and args.brand in brands else random.choice(list(brands.keys()))
            packs = brands[brand]
            pack_path = None if args.no_pack else random.choice(packs)
            if not args.no_logo and pack_path:
                logo_path = get_logo_for_brand(cig_dir, brand)

        if pack_path:
            bg = create_background_from_image(pack_path, w, h)
        else:
            bg = create_solid_background(w, h)

        overlay = TobaccoBannerOverlay(style=style, disclaimer_bg_style=disc_style)
        cfg = _load_config()
        badge_text = None
        venue_name = None
        venue_address = None
        venue_hours = None
        if product_type == "hookah":
            badge_text = random.choice(["КАЛЬЯННАЯ", "КАЛЬЯН"])
            v = get_random_tobacco_venue("hookah")
            if v:
                venue_name = v.get("name")
                venue_address = v.get("address")
                venue_hours = v.get("hours")
        elif product_type == "vape":
            badge_text = "ВЕЙП-МАГАЗИН"
            v = get_random_tobacco_venue("vape")
            if v:
                venue_name = v.get("name")
                venue_address = v.get("address")
                venue_hours = v.get("hours")
        elif product_type in ("venues", "smoking_mixes"):
            badge_text = random.choice(cfg.get("venue_badges", ["ЛАУНДЖ", "КАЛЬЯННАЯ"]))
            v = get_random_tobacco_venue(None)
            if v:
                venue_name = v.get("name")
                venue_address = v.get("address")
                venue_hours = v.get("hours")
        final = overlay.apply(
            bg,
            headline=bundle["headline"],
            description=bundle["description"],
            disclaimer=bundle["disclaimer"],
            pack_path=pack_path,
            logo_path=logo_path,
            cigarette_images_dir=None,
            product_type=product_type,
            venue_badge_text=badge_text,
            venue_name=venue_name,
            venue_address=venue_address,
            venue_hours=venue_hours,
        )

        ts = int(time.time() * 1000)
        label = brand if product_type == "cigarettes" else product_type
        fname = f"tobacco_{str(label).replace(' ', '_')}_{i:03d}_{ts}.png"
        final.save(out_path / fname, quality=95)
        tag = f"марка: {brand}, лого: {'да' if logo_path else 'нет'}" if product_type == "cigarettes" else product_type
        print(f"[{i+1}/{args.count}] {fname} ({tag})")

    print(f"\nГотово: {out_path}")


if __name__ == "__main__":
    main()
