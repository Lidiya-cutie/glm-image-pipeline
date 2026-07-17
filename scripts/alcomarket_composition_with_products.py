#!/usr/bin/env python3
"""
Композиция баннеров категории «алкомаркет».

Создание баннеров из готовых фоновых изображений с наложением текста.
- product_type=products: реклама алкогольной продукции (бутылки, банки)
- product_type=venues: магазины, бары, лаунджи — крафтовый бейдж

Примеры:
    python scripts/alcomarket_composition_with_products.py --image bg.png --output output/alcomarket/
    python scripts/alcomarket_composition_with_products.py --count 5 --product-type venues
"""

import argparse
import random
import sys
import time
from pathlib import Path

from PIL import Image, ImageStat, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.alcomarket_overlay import (
    AlcomarketBannerOverlay,
    build_alcomarket_text_bundle,
)
from scripts.alcomarket_overlay import _load_config

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
    img_path: Path,
    width: int,
    height: int,
) -> Image.Image:
    """Создаёт пастельный фон по среднему цвету изображения."""
    img = Image.open(img_path).convert("RGB")
    avg = get_average_color(img)
    bg_color = pastel_from_color(avg)
    return Image.new("RGBA", (width, height), (*bg_color, 255))


def create_solid_background(width: int, height: int) -> Image.Image:
    """Нейтральный тёмный или светлый фон."""
    colors = [(240, 238, 235), (45, 45, 50), (60, 55, 50), (30, 35, 45)]
    bg = random.choice(colors)
    return Image.new("RGBA", (width, height), (*bg, 255))


def main():
    parser = argparse.ArgumentParser(
        description="Композиция алкомаркет: фон + текст + бейдж (для venues)"
    )
    parser.add_argument("--image", type=str, help="Путь к фоновому изображению")
    parser.add_argument("--output", type=str, default="output/alcomarket_composition")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--format", type=str, choices=list(BANNER_FORMATS.keys()), default="horizontal")
    parser.add_argument(
        "--product-type",
        type=str,
        choices=["products", "venues"],
        default=None,
        help="products=продукт, venues=магазин/бар. По умолчанию — случайный",
    )
    parser.add_argument("--headline", type=str)
    parser.add_argument("--description", type=str)
    parser.add_argument("--disclaimer", type=str)
    args = parser.parse_args()

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
        bundle = build_alcomarket_text_bundle(
            headline=args.headline,
            description=args.description,
            disclaimer=args.disclaimer,
            product_type=pt,
        )
        product_type = bundle["product_type"]

        if args.image and Path(args.image).exists():
            bg_img = Image.open(args.image).convert("RGBA")
            bg_img = bg_img.resize((w, h), Image.LANCZOS)
        else:
            bg = create_solid_background(w, h)
            bg_img = bg

        venue_badge_text = None
        if product_type == "venues":
            venue_badges = cfg.get("venue_badges", ["ЛАУНДЖ", "АЛКОМАРКЕТ"])
            venue_badge_text = random.choice(venue_badges)

        overlay = AlcomarketBannerOverlay(style=style, disclaimer_bg_style=disc_style)
        final = overlay.apply(
            bg_img,
            headline=bundle["headline"],
            description=bundle["description"],
            disclaimer=bundle["disclaimer"],
            product_type=product_type,
            venue_badge_text=venue_badge_text,
        )

        ts = int(time.time() * 1000)
        fname = f"alcomarket_{product_type}_{i:03d}_{ts}.png"
        path = out_path / fname
        final.save(path)
        print(f"  ✅ {path}")

    print(f"\n✅ Готово: {out_path}")


if __name__ == "__main__":
    main()
