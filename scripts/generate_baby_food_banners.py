#!/usr/bin/env python3
"""
Full Baby Food Ad Banner Generator (Детское питание 0–3 года)

Полный пайплайн генерации рекламных баннеров детского питания с учётом
гайдлайна «Детское питание (0–3 года)» и ФЗ «О рекламе» РФ.

ОБЯЗАТЕЛЬНО: возрастная маркировка, дисклеймер (молоко матери + консультация специалиста).
ЗАПРЕЩЕНО: утверждения о замене ГВ, преимущества ИВ перед грудным вскармливанием.

ФОРМАТЫ: square 1024x1024, horizontal 1200x700, vertical 800x1200.
СЦЕНАРИИ: 10 без людей (объект в углу + градиент), 3 с людьми (мама + ребёнок).

Примеры:
    python scripts/generate_baby_food_banners.py --scenario jar_puree_lower_right_gradient
    python scripts/generate_baby_food_banners.py --all-scenarios --output output/baby_food/
    python scripts/generate_baby_food_banners.py --without-people --format horizontal --count 5
    python scripts/generate_baby_food_banners.py --backgrounds-only --format square
    python scripts/generate_baby_food_banners.py --list-scenarios
    python scripts/generate_baby_food_banners.py --show-requirements
"""

import argparse
import sys
from pathlib import Path
import random
from typing import Dict, List, Optional, Any
import torch
from PIL import Image

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.baby_food_overlay import (
    BabyFoodBannerOverlay,
    BabyFoodValidator,
    BABY_FOOD_HEADLINES,
    BABY_FOOD_DESCRIPTIONS,
    BABY_FOOD_DISCLAIMERS,
    BABY_FOOD_STYLES,
    BABY_FOOD_SCENARIOS,
    AGE_MARKING_TEMPLATES,
    DISCLAIMER_BG_STYLES,
    get_random_content,
    get_layout_for_scenario,
    get_random_disclaimer_bg_style,
    get_disclaimer_bg_style_by_name,
    find_safe_qr_position_for_baby_food,
)
from scripts.text_overlay import LAYOUTS, get_layout_by_name

# QR pipeline (опционально, как в ломбардах / доверительном управлении)
try:
    from scripts.generate_folk_medicine_with_qr_2 import FolkMedicineQRPipeline
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

BANNER_FORMATS = {
    "square": (1024, 1024),
    "horizontal": (1200, 700),
    "vertical": (800, 1200),
}

NEG_PROMPT = "text, words, letters, watermark, logo, cartoon, anime, 3d render, cluttered, bright red, bright pink, neon colors, low quality, blurry, deformed, sad baby, crying"
NEG_PROMPT_PERSON = "text, words, letters, watermark, logo, cartoon, anime, 3d render, deformed, ugly, bad anatomy, extra limbs, blurry, low quality, red clothes, pink background, sad baby"


class BabyFoodBannerPipeline:
    """Пайплайн: генерация фона + наложение текста (гайдлайн детское питание 0–3 года)."""

    def __init__(
        self,
        device: str = "cuda",
        dtype: torch.dtype = torch.float16,
        quantize: str = None,
        validate: bool = True,
    ):
        self.device = device
        self.dtype = dtype
        self.quantize = quantize
        self.validate = validate
        self._pipeline = None

    def load(self):
        if self._pipeline is not None:
            return
        from pipeline.inference.simple_pipeline import SimpleImagePipeline
        print("Загрузка модели...")
        self._pipeline = SimpleImagePipeline(device=self.device, dtype=self.dtype, quantize=self.quantize)
        self._pipeline.load()

    def generate_background(
        self,
        scenario: Dict[str, Any],
        width: int = 1024,
        height: int = 1024,
        num_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: int = None,
    ) -> Image.Image:
        self.load()
        is_person = scenario.get("has_person") or "person_position" in scenario
        neg_prompt = NEG_PROMPT_PERSON if is_person else NEG_PROMPT
        if seed is None:
            seed = random.randint(1, 2**31 - 1)
        images = self._pipeline.generate(
            prompt=scenario["prompt"],
            negative_prompt=neg_prompt,
            width=width,
            height=height,
            num_inference_steps=num_steps,
            guidance_scale=guidance_scale,
            seed=seed,
            num_images=1,
        )
        return images[0]

    def _add_qr_code(
        self,
        image: Image.Image,
        width: int,
        height: int,
        qr_url: Optional[str] = None,
        layout_bounds: Dict[str, Any] = None,
    ) -> Image.Image:
        """Добавляет QR-код так, чтобы он не перекрывал дисклеймер, описание, заголовок или логотипы."""
        if not QR_AVAILABLE:
            return image
        if not layout_bounds:
            print(f"  ⚠️  QR пропущен: нет данных о layout bounds")
            return image

        try:
            url = qr_url or "https://www.example.ru/baby-food"
            if not url.startswith(("http://", "https://")):
                url = "https://" + url

            pipeline = FolkMedicineQRPipeline(device="cpu")
            qr_type = random.choice(["simple", "artistic_white", "custom_color"])
            qr_img = pipeline.generate_qr_variety(url, qr_type=qr_type)
            if not qr_img:
                return image

            qr_size = min(120, int(min(width, height) * 0.12))
            qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS).convert("RGBA")

            qr_pos = find_safe_qr_position_for_baby_food(width, height, qr_size, layout_bounds)
            if qr_pos is None:
                print(f"  ⚠️  QR пропущен: нет свободной зоны между описанием и дисклеймером")
                return image

            qr_x, qr_y = qr_pos
            if qr_x >= 0 and qr_y >= 0 and qr_x + qr_size <= width and qr_y + qr_size <= height:
                image.paste(qr_img, qr_pos, qr_img)
                print(f"  ✅ QR добавлен в позиции ({qr_x}, {qr_y}): {url[:40]}...")
            else:
                print(f"  ⚠️  QR не помещается в позиции ({qr_x}, {qr_y}), пропущен")
        except Exception as e:
            print(f"  ⚠️  Ошибка добавления QR: {e}")
            import traceback
            traceback.print_exc()
        return image

    def generate_banner(
        self,
        scenario: Dict[str, Any] = None,
        headline: str = None,
        description: str = None,
        disclaimer: str = None,
        age_marking: str = None,
        layout: Dict = None,
        style: Dict = None,
        disclaimer_bg_style: Dict = None,
        width: int = 1024,
        height: int = 1024,
        num_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: int = None,
        add_qr: bool = False,
        qr_chance: float = 50.0,
        qr_url: Optional[str] = None,
    ) -> Image.Image:
        scenario = scenario or random.choice(BABY_FOOD_SCENARIOS)
        layout = layout or get_layout_for_scenario(scenario)
        style = style or random.choice(BABY_FOOD_STYLES)
        content = get_random_content()
        headline = headline or content["headline"]
        description = description or content["description"]
        disclaimer = disclaimer or content["disclaimer"]
        age_marking = age_marking or content["age_marking"]

        print(f"  Генерация фона: {scenario['name']} ({width}x{height})...")
        background = self.generate_background(
            scenario=scenario,
            width=width,
            height=height,
            num_steps=num_steps,
            guidance_scale=guidance_scale,
            seed=seed,
        )

        overlay = BabyFoodBannerOverlay(
            layout=layout,
            style=style,
            disclaimer_bg_style=disclaimer_bg_style or get_random_disclaimer_bg_style(),
            validate=self.validate,
        )
        result, layout_bounds = overlay.apply(
            background,
            headline=headline,
            description=description,
            disclaimer=disclaimer,
            age_marking=age_marking,
        )

        if add_qr and random.random() * 100 < qr_chance:
            result = self._add_qr_code(
                result,
                width=width,
                height=height,
                qr_url=qr_url,
                layout_bounds=layout_bounds,
            )

        return result

    def generate_batch(
        self,
        scenarios: List[Dict],
        output_dir: Path,
        format_name: str = "square",
        variations: int = 1,
        backgrounds_only: bool = False,
        **kwargs,
    ) -> List[Dict]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        w, h = BANNER_FORMATS.get(format_name, (1024, 1024))
        if kwargs.get("width") and kwargs.get("height"):
            w, h = kwargs["width"], kwargs["height"]
            format_name = "custom"
        results = []
        for scenario in scenarios:
            for var in range(variations):
                try:
                    if backgrounds_only:
                        print(f"  Генерация фона: {scenario['name']} ({w}x{h})...")
                        image = self.generate_background(
                            scenario=scenario,
                            width=w,
                            height=h,
                            **{k: v for k, v in kwargs.items() if k in ("num_steps", "guidance_scale", "seed")}
                        )
                        seed_str = kwargs.get("seed") or random.randint(100000, 999999)
                        filename = f"baby_food_bg_{scenario['name']}_{format_name}_{var:03d}_{seed_str}.png"
                    else:
                        image = self.generate_banner(
                            scenario=scenario,
                            width=w,
                            height=h,
                            **{k: v for k, v in kwargs.items() if k in ("num_steps", "guidance_scale", "seed", "add_qr", "qr_chance", "qr_url")}
                        )
                        filename = f"baby_food_{scenario['name']}_{format_name}_{var:02d}.png"
                    filepath = output_dir / filename
                    image.save(filepath, quality=95)
                    results.append({
                        "filename": str(filepath),
                        "scenario": scenario["name"],
                        "format": format_name,
                        "has_person": scenario.get("has_person", False),
                    })
                    print(f"  ✅ Сохранено: {filepath}")
                except Exception as e:
                    print(f"  ❌ Ошибка: {e}")
                    import traceback
                    traceback.print_exc()
        return results


def main():
    parser = argparse.ArgumentParser(description="Генератор баннеров детского питания (0–3 года)")
    parser.add_argument("--scenario", type=str, help="Имя одного сценария")
    parser.add_argument("--scenarios", type=str, help="Несколько сценариев через запятую")
    parser.add_argument("--all-scenarios", action="store_true", help="Все сценарии")
    parser.add_argument("--with-people", action="store_true", help="Только сценарии с людьми (мама+ребёнок)")
    parser.add_argument("--without-people", action="store_true", help="Только сценарии без людей")
    parser.add_argument("--format", type=str, choices=list(BANNER_FORMATS), default="square")
    parser.add_argument("--count", type=int, default=1, help="Количество вариаций на сценарий")
    parser.add_argument("--output", type=str, default="output/baby_food")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--quantize", type=str, choices=["4bit", "8bit"])
    parser.add_argument("--list-scenarios", action="store_true")
    parser.add_argument("--show-requirements", action="store_true")
    parser.add_argument("--backgrounds-only", action="store_true", help="Генерировать только фоны без текста")
    parser.add_argument("--validate", type=str, help="Проверить текст (например: «Лучше маминого молока»)")
    parser.add_argument("--add-qr", action="store_true", help="Добавлять QR-коды (по умолчанию включено при полных баннерах)")
    parser.add_argument("--no-qr", action="store_true", help="Не добавлять QR-коды даже при полных баннерах")
    parser.add_argument("--qr-chance", type=float, default=50.0, help="Вероятность добавления QR-кода (0-100)")
    parser.add_argument("--qr-url", type=str, help="URL для QR-кода (по умолчанию служебный baby-food URL)")
    args = parser.parse_args()

    if args.list_scenarios:
        no_people = [s for s in BABY_FOOD_SCENARIOS if not s.get("has_person")]
        with_people = [s for s in BABY_FOOD_SCENARIOS if s.get("has_person")]
        print("\n=== Сценарии БЕЗ людей (объект в углу + градиент, детальные композиции) ===")
        for s in no_people:
            print(f"  • {s['name']}")
        print("\n=== Сценарии С людьми (мама + ребёнок, детальные по референсам) ===")
        for s in with_people:
            print(f"  • {s['name']} ({s.get('person_position', '-')})")
        print(f"\nВсего: {len(no_people)} без людей, {len(with_people)} с людьми.")
        return

    if args.show_requirements:
        print("""
╔══════════════════════════════════════════════════════════════════╗
║     ГАЙДЛАЙН: Реклама детского питания (0–3 года)                 ║
╠══════════════════════════════════════════════════════════════════╣
║  ✅ ОБЯЗАТЕЛЬНО:                                                 ║
║     • Возрастная маркировка (0+, с 6 месяцев, для детей с 1 года) ║
║     • Дисклеймер: «Молоко матери — идеальное питание...»         ║
║     • Призыв: «Перед вводом продукта проконсультируйтесь со специалистом» ║
║  ❌ ЗАПРЕЩЕНО:                                                   ║
║     • Утверждения о замене грудного молока                        ║
║     • Преимущества искусственного вскармливания перед ГВ         ║
╚══════════════════════════════════════════════════════════════════╝
        """)
        return

    if args.validate:
        v = BabyFoodValidator.check_forbidden(args.validate)
        if v:
            print("Нарушения:", v)
        else:
            print("Запрещённых формулировок не найдено.")
        return

    # Выбор сценариев (включая детальные: gerber_style, chudo_chado, nutrilon, agusha, md, bledina, nan, tema)
    if args.all_scenarios:
        scenarios = BABY_FOOD_SCENARIOS
    elif args.with_people:
        scenarios = [s for s in BABY_FOOD_SCENARIOS if s.get("has_person")]
    elif args.without_people:
        scenarios = [s for s in BABY_FOOD_SCENARIOS if not s.get("has_person")]
    elif args.scenarios:
        names = [n.strip() for n in args.scenarios.split(",") if n.strip()]
        name_set = set(names)
        scenarios = [s for s in BABY_FOOD_SCENARIOS if s["name"] in name_set]
        missing = name_set - {s["name"] for s in scenarios}
        if missing:
            print(f"Сценарии не найдены: {missing}")
            return
    elif args.scenario:
        scenarios = [s for s in BABY_FOOD_SCENARIOS if s["name"] == args.scenario]
        if not scenarios:
            print(f"Сценарий '{args.scenario}' не найден!")
            return
    else:
        scenarios = [BABY_FOOD_SCENARIOS[0]]

    w, h = BANNER_FORMATS[args.format]
    if args.width:
        w = args.width
    if args.height:
        h = args.height
    format_name = "custom" if (args.width and args.height) else args.format

    pipeline = BabyFoodBannerPipeline(
        device="cuda",
        quantize=args.quantize,
        validate=True,
    )
    results = pipeline.generate_batch(
        scenarios=scenarios,
        output_dir=Path(args.output),
        format_name=format_name,
        variations=args.count,
        backgrounds_only=args.backgrounds_only,
        width=w,
        height=h,
        num_steps=args.steps,
        guidance_scale=7.5,
        seed=args.seed,
        add_qr=(not args.backgrounds_only and not args.no_qr) or args.add_qr,
        qr_chance=args.qr_chance,
        qr_url=args.qr_url,
    )
    print(f"\n✅ Создано {len(results)} баннеров в {args.output}")


if __name__ == "__main__":
    main()
