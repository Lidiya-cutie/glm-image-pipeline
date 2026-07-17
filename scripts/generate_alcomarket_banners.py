#!/usr/bin/env python3
"""
Генератор баннеров категории «алкомаркет» (SDXL + overlay).

Полный пайплайн:
1. Генерация фонового изображения (SDXL)
2. Наложение текста (заголовок, описание, дисклеймер)
3. product_type=venues: крафтовый бейдж (магазин, бар, лаундж)

Примеры:
    python scripts/generate_alcomarket_banners.py --scenario beer_bottle_center_neutral
    python scripts/generate_alcomarket_banners.py --all-scenarios --output output/alcomarket_all
    python scripts/generate_alcomarket_banners.py --all-scenarios --product-type venues
    python scripts/generate_alcomarket_banners.py --backgrounds-only --format square
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.alcomarket_overlay import (
    AlcomarketBannerOverlay,
    build_alcomarket_text_bundle,
)
from scripts.alcomarket_overlay import _load_config

try:
    from scripts.text_overlay import LAYOUTS, get_layout_by_name
except ImportError:
    LAYOUTS = [{"name": "classic_left"}]

    def get_layout_by_name(name: str):
        return LAYOUTS[0]

BANNER_FORMATS = {
    "square": (1024, 1024),
    "horizontal": (1200, 700),
    "vertical": (800, 1200),
}

NEG_PROMPT = "text, words, letters, watermark, logo, cartoon, anime, 3d render, low quality, blurry, deformed, ugly"
CONFIG_PATH = PROJECT_ROOT / "configs" / "alcomarket_config.json"


def load_scenarios() -> List[Dict[str, Any]]:
    """Загружает сценарии из alcomarket_config.json."""
    if not CONFIG_PATH.exists():
        return []
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("scenarios", [])


class AlcomarketBannerPipeline:
    """Пайплайн генерации баннеров алкомаркета: SDXL фон + текст + бейдж (для venues)."""

    def __init__(
        self,
        device: str = "cuda",
        dtype: torch.dtype = torch.float16,
        quantize: Optional[str] = None,
    ):
        self.device = device
        self.dtype = dtype
        self.quantize = quantize
        self._pipeline = None

    def load(self):
        """Загрузка SDXL-модели."""
        if self._pipeline is not None:
            return

        from pipeline.inference.simple_pipeline import SimpleImagePipeline

        print("Загрузка SDXL-модели...")
        self._pipeline = SimpleImagePipeline(
            device=self.device,
            dtype=self.dtype,
            quantize=self.quantize,
        )
        self._pipeline.load()

    def generate_background(
        self,
        scenario: Dict[str, Any],
        width: int = 1024,
        height: int = 1024,
        num_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: Optional[int] = None,
    ) -> Image.Image:
        """Генерация фонового изображения через SDXL."""
        self.load()

        images = self._pipeline.generate(
            prompt=scenario["prompt"],
            negative_prompt=NEG_PROMPT,
            width=width,
            height=height,
            num_inference_steps=num_steps,
            guidance_scale=guidance_scale,
            seed=seed,
            num_images=1,
        )

        return images[0]

    def generate_banner(
        self,
        scenario: Dict[str, Any],
        product_type: Optional[str] = None,
        headline: Optional[str] = None,
        description: Optional[str] = None,
        disclaimer: Optional[str] = None,
        layout: Optional[Dict] = None,
        style: Optional[Dict] = None,
        width: int = 1024,
        height: int = 1024,
        num_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: Optional[int] = None,
    ) -> Image.Image:
        """Генерация полного баннера: фон + текст + бейдж (для venues)."""
        cfg = _load_config()
        styles = cfg.get("styles", [])
        disc_styles = cfg.get("disclaimer_bg_styles", [])
        style = style or (random.choice(styles) if styles else {})
        disc_style = random.choice(disc_styles) if disc_styles else {}

        background = self.generate_background(
            scenario=scenario,
            width=width,
            height=height,
            num_steps=num_steps,
            guidance_scale=guidance_scale,
            seed=seed,
        )

        bundle = build_alcomarket_text_bundle(
            headline=headline,
            description=description,
            disclaimer=disclaimer,
            product_type=product_type,
        )

        venue_badge_text = None
        if bundle["product_type"] == "venues":
            venue_badges = cfg.get(
                "venue_badges", ["ЛАУНДЖ", "АЛКОМАРКЕТ", "ВИННЫЙ БУТИК"]
            )
            venue_badge_text = random.choice(venue_badges)

        overlay = AlcomarketBannerOverlay(
            layout=layout, style=style, disclaimer_bg_style=disc_style
        )
        result = overlay.apply(
            background,
            headline=bundle["headline"],
            description=bundle["description"],
            disclaimer=bundle["disclaimer"],
            product_type=bundle["product_type"],
            venue_badge_text=venue_badge_text,
        )

        return result


def main():
    parser = argparse.ArgumentParser(
        description="Генератор баннеров алкомаркета (SDXL + текст + бейдж)"
    )

    parser.add_argument("--scenario", type=str, help="Имя сценария")
    parser.add_argument("--all-scenarios", action="store_true", help="Все сценарии")
    parser.add_argument("--with-people", action="store_true", help="Только сценарии с людьми")
    parser.add_argument("--without-people", action="store_true", help="Только сценарии без людей")
    parser.add_argument("--count", type=int, default=1, help="Баннеров на сценарий (при --all-scenarios)")
    parser.add_argument("--scenarios", type=str, help="Список сценариев через запятую")

    parser.add_argument(
        "--product-type",
        type=str,
        choices=["products", "venues"],
        default=None,
        help="products=продукт, venues=магазин/бар (бейдж). По умолчанию — случайный",
    )

    parser.add_argument("--headline", type=str)
    parser.add_argument("--description", type=str)
    parser.add_argument("--disclaimer", type=str)

    parser.add_argument("--layout", type=str)
    parser.add_argument("--format", type=str, choices=list(BANNER_FORMATS.keys()), default="horizontal")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--cfg-scale", type=float, default=7.5)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--backgrounds-only", action="store_true", help="Только фоны без текста")

    parser.add_argument("--quantize", type=str, choices=["4bit", "8bit"])
    parser.add_argument("--device", type=str, default="cuda")
    parser.add_argument("--dtype", type=str, default="fp16", choices=["fp16", "bf16", "fp32"])

    parser.add_argument("--output", type=str, default="output/alcomarket")
    parser.add_argument("--list-scenarios", action="store_true")

    args = parser.parse_args()

    scenarios = load_scenarios()
    if not scenarios:
        print("Ошибка: сценарии не найдены в alcomarket_config.json")
        sys.exit(1)

    if args.list_scenarios:
        print("\n=== Сценарии алкомаркет ===")
        for s in scenarios:
            person = "с человеком" if s.get("has_person") else "без людей"
            print(f"  • {s['name']} ({person})")
        return

    if args.all_scenarios:
        selected = scenarios
    elif args.with_people:
        selected = [s for s in scenarios if s.get("has_person")]
    elif args.without_people:
        selected = [s for s in scenarios if not s.get("has_person")]
    elif args.scenarios:
        names = [n.strip() for n in args.scenarios.split(",")]
        selected = [s for s in scenarios if s["name"] in names]
        if len(selected) != len(names):
            found = {s["name"] for s in selected}
            print(f"Не найдены: {set(names) - found}")
    elif args.scenario:
        selected = [s for s in scenarios if s["name"] == args.scenario]
        if not selected:
            print(f"Сценарий '{args.scenario}' не найден")
            print("Доступные:", [s["name"] for s in scenarios][:20], "...")
            sys.exit(1)
    else:
        selected = [random.choice(scenarios)]

    if args.width and args.height:
        w, h = args.width, args.height
    else:
        w, h = BANNER_FORMATS[args.format]

    dtype_map = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}
    pipeline = AlcomarketBannerPipeline(
        device=args.device,
        dtype=dtype_map[args.dtype],
        quantize=args.quantize,
    )

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    layout = get_layout_by_name(args.layout) if args.layout else None
    count = 0

    for scenario in selected:
        for i in range(args.count):
            count += 1
            seed = args.seed if args.seed is not None else random.randint(100000, 999999)
            ts = int(time.time() * 1000)
            base_name = scenario["name"].replace(" ", "_")

            try:
                if args.backgrounds_only:
                    print(f"[{count}] Фон: {scenario['name']}...")
                    img = pipeline.generate_background(
                        scenario=scenario,
                        width=w,
                        height=h,
                        num_steps=args.steps,
                        guidance_scale=args.cfg_scale,
                        seed=seed,
                    )
                    fname = f"alcomarket_bg_{base_name}_{i:03d}_{ts}.png"
                else:
                    print(f"[{count}] Баннер: {scenario['name']}...")
                    img = pipeline.generate_banner(
                        scenario=scenario,
                        product_type=args.product_type,
                        headline=args.headline,
                        description=args.description,
                        disclaimer=args.disclaimer,
                        layout=layout,
                        width=w,
                        height=h,
                        num_steps=args.steps,
                        guidance_scale=args.cfg_scale,
                        seed=seed,
                    )
                    fname = f"alcomarket_{base_name}_{i:03d}_{ts}.png"

                path = output_dir / fname
                img.save(path, quality=95)
                print(f"  ✅ {path}")

            except Exception as e:
                print(f"  ❌ Ошибка: {e}")
                import traceback

                traceback.print_exc()

    print(f"\n✅ Готово: {output_dir}")


if __name__ == "__main__":
    main()
