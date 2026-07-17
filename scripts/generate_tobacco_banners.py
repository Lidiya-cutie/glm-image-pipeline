#!/usr/bin/env python3
"""
Генератор баннеров категории «табак» (SDXL + overlay).

Полный пайплайн:
1. Генерация фонового изображения (SDXL)
2. Наложение текста (заголовок, описание, дисклеймер)
3. Наложение пачки и логотипа (при product_type=cigarettes) или крафтового бейджа (при venues)

Примеры:
    python scripts/generate_tobacco_banners.py --scenario tobacco_noir_pack_ashtray_smoke
    python scripts/generate_tobacco_banners.py --all-scenarios --output output/tobacco_all_4
    python scripts/generate_tobacco_banners.py --all-scenarios --product-type cigarettes --format horizontal
    python scripts/generate_tobacco_banners.py --backgrounds-only --format square
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

from scripts.tobacco_overlay import (
    TobaccoBannerOverlay,
    build_tobacco_text_bundle,
    get_tobacco_brands_and_packs,
    get_logo_for_brand,
    get_random_tobacco_venue_name,
    get_random_tobacco_venue,
)
from scripts.tobacco_overlay import _load_config

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
CONFIG_PATH = PROJECT_ROOT / "configs" / "tobacco_config.json"

# Сценарии tobacco_woman_*: всегда пачки из cigarette_images, без venue-бейджей и крафтовых названий
TOBACCO_WOMAN_SCENARIOS = frozenset([
    "tobacco_woman_cherry_luxury",
    "tobacco_woman_profile_flower",
    "tobacco_woman_smiling_cigarette",
    "tobacco_woman_legs_bracelet",
    "tobacco_woman_duo_glamour",
    "tobacco_woman_youth_dynamic",
    "tobacco_woman_beach_blur",
])

# Сценарии ментола: без пачек из cigarette_images, только логотипы
MENTHOL_LOGO_ONLY_SCENARIOS = frozenset([
    "tobacco_menthol_fresh_ice",
    "menthol_condensation_mint_leaves",
    "menthol_mint_leaves_open_pack",
    "menthol_ice_smoke_stylized",
])

# Сценарии БЕЗ наложения наименования магазина и инфо в дисклеймере
# (cafe_hookah — с бейджем и названием кальянной, menthol/tobacco_woman — без)
SCENARIOS_WITHOUT_VENUE_INFO = (
    TOBACCO_WOMAN_SCENARIOS | MENTHOL_LOGO_ONLY_SCENARIOS
)


def load_scenarios() -> List[Dict[str, Any]]:
    """Загружает сценарии из tobacco_config.json."""
    if not CONFIG_PATH.exists():
        return []
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("scenarios", [])


class TobaccoBannerPipeline:
    """
    Пайплайн генерации баннеров: SDXL фон + текст + пачка/логотип (или бейдж).
    """

    def __init__(
        self,
        device: str = "cuda",
        dtype: torch.dtype = torch.float16,
        quantize: Optional[str] = None,
        cigarette_images_dir: Optional[Path] = None,
    ):
        self.device = device
        self.dtype = dtype
        self.quantize = quantize
        self.cigarette_images_dir = Path(cigarette_images_dir) if cigarette_images_dir else PROJECT_ROOT / "cigarette_images"
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
        purpose: Optional[str] = None,
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
        """
        Генерация полного баннера: фон + текст + пачка/логотип или бейдж.
        """
        cfg = _load_config()
        styles = cfg.get("styles", [])
        disc_styles = cfg.get("disclaimer_bg_styles", [])
        style = style or (random.choice(styles) if styles else {})
        disc_style = random.choice(disc_styles) if disc_styles else {}

        sc_purpose = scenario.get("purpose", "advertising")
        if purpose is None:
            purpose = sc_purpose
        if product_type is None and sc_purpose == "propaganda":
            product_type = "propaganda"

        # tobacco_woman_*: только пачки из cigarette_images, без venue-бейджей и крафтовых названий
        is_woman_scenario = scenario.get("name") in TOBACCO_WOMAN_SCENARIOS
        if is_woman_scenario:
            product_type = "cigarettes"
        # Ментол-сценарии: только логотип, без пачек
        if scenario.get("name") in MENTHOL_LOGO_ONLY_SCENARIOS:
            product_type = "cigarettes"

        # Генерируем фон
        background = self.generate_background(
            scenario=scenario,
            width=width,
            height=height,
            num_steps=num_steps,
            guidance_scale=guidance_scale,
            seed=seed,
        )

        # Текстовый бандл
        bundle = build_tobacco_text_bundle(
            headline=headline,
            description=description,
            disclaimer=disclaimer,
            purpose=purpose,
            product_type=product_type,
        )

        # tobacco_woman_*: дамские заголовки и слоганы
        if is_woman_scenario:
            women_hl = cfg.get("headlines_women_cigarettes", [])
            if women_hl:
                bundle["headline"] = random.choice(women_hl)
            women_desc = cfg.get("descriptions_women_cigarettes", [])
            if women_desc:
                bundle["description"] = random.choice(women_desc)

        # Пачка и логотип для cigarettes
        pack_path = None
        logo_path = None
        brand = None
        is_menthol_logo_only = scenario.get("name") in MENTHOL_LOGO_ONLY_SCENARIOS
        if bundle["product_type"] == "cigarettes" and self.cigarette_images_dir.is_dir():
            brands = get_tobacco_brands_and_packs(self.cigarette_images_dir)
            if brands:
                brand_list = list(brands.keys())
                random.shuffle(brand_list)
                if is_menthol_logo_only:
                    # Только логотип, без пачки
                    for b in brand_list:
                        logo_path = get_logo_for_brand(self.cigarette_images_dir, b)
                        if logo_path:
                            break
                    pack_path = None
                else:
                    brand = random.choice(brand_list)
                    packs = brands[brand]
                    pack_path = random.choice(packs) if packs else None
                    logo_path = get_logo_for_brand(self.cigarette_images_dir, brand) if pack_path else None

        # Бейдж для venues, hookah, vape, smoking_mixes + данные заведения
        venue_badge_text = None
        venue_name = None
        venue_address = None
        venue_hours = None
        venue_phone = None
        pt = bundle["product_type"]
        scenario_name = scenario.get("name", "")
        add_venue_info = scenario_name not in SCENARIOS_WITHOUT_VENUE_INFO

        if pt == "hookah" and add_venue_info:
            venue_badge_text = random.choice(["КАЛЬЯННАЯ", "КАЛЬЯН"])
            v = get_random_tobacco_venue("hookah")
            if v:
                venue_name = v.get("name")
                venue_address = v.get("address")
                venue_hours = v.get("hours")
                venue_phone = v.get("phone") or None
        elif pt == "vape" and add_venue_info:
            venue_badge_text = "ВЕЙП-МАГАЗИН"
            v = get_random_tobacco_venue("vape")
            if v:
                venue_name = v.get("name")
                venue_address = v.get("address")
                venue_hours = v.get("hours")
                venue_phone = v.get("phone") or None
        elif pt in ("venues", "smoking_mixes") and add_venue_info:
            venue_badges = cfg.get("venue_badges", ["ЛАУНДЖ", "КАЛЬЯННАЯ", "ТАБАЧНЫЙ МАГАЗИН"])
            venue_badge_text = random.choice(venue_badges)
            v = get_random_tobacco_venue(None)
            if v:
                venue_name = v.get("name")
                venue_address = v.get("address")
                venue_hours = v.get("hours")
                venue_phone = v.get("phone") or None
        elif add_venue_info:
            v = get_random_tobacco_venue(None)
            if v:
                venue_name = v.get("name")
                venue_address = v.get("address")
                venue_hours = v.get("hours")
                venue_phone = v.get("phone") or None

        # Overlay
        overlay = TobaccoBannerOverlay(layout=layout, style=style, disclaimer_bg_style=disc_style)
        result = overlay.apply(
            background,
            headline=bundle["headline"],
            description=bundle["description"],
            disclaimer=bundle["disclaimer"],
            pack_path=pack_path,
            logo_path=logo_path,
            cigarette_images_dir=None,
            product_type=bundle["product_type"],
            venue_badge_text=venue_badge_text,
            venue_name=venue_name,
            venue_address=venue_address,
            venue_hours=venue_hours,
            venue_phone=venue_phone,
        )

        return result


def main():
    parser = argparse.ArgumentParser(
        description="Генератор баннеров категории табак (SDXL + текст + пачка/логотип)"
    )

    # Сценарии
    parser.add_argument("--scenario", type=str, help="Имя сценария")
    parser.add_argument("--all-scenarios", action="store_true", help="Все сценарии")
    parser.add_argument("--with-people", action="store_true", help="Только сценарии с людьми")
    parser.add_argument("--without-people", action="store_true", help="Только сценарии без людей")
    parser.add_argument("--propaganda-only", action="store_true", help="Только сценарии пропаганды ЗОЖ")
    parser.add_argument("--count", type=int, default=1, help="Баннеров на сценарий (при --all-scenarios)")
    parser.add_argument("--scenarios", type=str, help="Список сценариев через запятую")
    parser.add_argument(
        "--exclude-scenarios",
        type=str,
        help="Исключить сценарии (через запятую). Работает с --all-scenarios.",
    )

    # Product type & purpose
    parser.add_argument(
        "--product-type",
        type=str,
        choices=["cigarettes", "venues", "hookah", "vape", "smoking_mixes", "propaganda"],
        default=None,
        help="cigarettes=пачка+логотип, venues/hookah/vape/smoking_mixes=бейдж, propaganda=ЗОЖ без табака",
    )
    parser.add_argument(
        "--purpose",
        type=str,
        choices=["advertising", "propaganda"],
        default=None,
        help="advertising=реклама, propaganda=пропаганда ЗОЖ без табака",
    )
    parser.add_argument(
        "--cigarette-images-dir",
        type=str,
        default=str(PROJECT_ROOT / "cigarette_images"),
        help="Директория с пачками и логотипами",
    )

    # Текст
    parser.add_argument("--headline", type=str)
    parser.add_argument("--description", type=str)
    parser.add_argument("--disclaimer", type=str)

    # Стиль
    parser.add_argument("--layout", type=str, help="Лейаут (classic_left и др.)")

    # Генерация
    parser.add_argument("--format", type=str, choices=list(BANNER_FORMATS.keys()), default="horizontal")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--cfg-scale", type=float, default=7.5)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--backgrounds-only", action="store_true", help="Только фоны без текста")

    # Модель
    parser.add_argument("--quantize", type=str, choices=["4bit", "8bit"])
    parser.add_argument("--device", type=str, default="cuda")
    parser.add_argument("--dtype", type=str, default="fp16", choices=["fp16", "bf16", "fp32"])

    # Вывод
    parser.add_argument("--output", type=str, default="output/tobacco")

    # Утилиты
    parser.add_argument("--list-scenarios", action="store_true")

    args = parser.parse_args()

    scenarios = load_scenarios()
    if not scenarios:
        print("Ошибка: сценарии не найдены в tobacco_config.json")
        sys.exit(1)

    # Утилиты
    if args.list_scenarios:
        print("\n=== Сценарии табак ===")
        for s in scenarios:
            person = "с человеком" if s.get("has_person") else "без людей"
            print(f"  • {s['name']} ({person})")
        return

    # Выбор сценариев
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
            print("Доступные:", [s["name"] for s in scenarios])
            sys.exit(1)
    else:
        selected = [random.choice(scenarios)]

    if args.propaganda_only:
        selected = [s for s in selected if s.get("purpose") == "propaganda"]

    if args.exclude_scenarios:
        exclude = {n.strip() for n in args.exclude_scenarios.split(",") if n.strip()}
        selected = [s for s in selected if s["name"] not in exclude]
        if exclude:
            print(f"Исключено {len(exclude)} сценариев: {', '.join(sorted(exclude))}")

    # Размеры
    if args.width and args.height:
        w, h = args.width, args.height
    else:
        w, h = BANNER_FORMATS[args.format]

    # Pipeline
    dtype_map = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}
    pipeline = TobaccoBannerPipeline(
        device=args.device,
        dtype=dtype_map[args.dtype],
        quantize=args.quantize,
        cigarette_images_dir=Path(args.cigarette_images_dir),
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
                    fname = f"tobacco_bg_{base_name}_{i:03d}_{ts}.png"
                else:
                    print(f"[{count}] Баннер: {scenario['name']}...")
                    img = pipeline.generate_banner(
                        scenario=scenario,
                        product_type=args.product_type,
                        purpose=args.purpose,
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
                    fname = f"tobacco_{base_name}_{i:03d}_{ts}.png"

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
