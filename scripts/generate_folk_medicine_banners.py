#!/usr/bin/env python3
"""
Full Folk Medicine Ad Banner Generator (Народная медицина)

Полный пайплайн генерации рекламных баннеров услуг народной медицины:
1. Генерация фонового изображения (SDXL)
2. Наложение текста с учётом законодательства РФ

ТРЕБОВАНИЯ ЗАКОНОДАТЕЛЬСТВА:
✅ ОБЯЗАТЕЛЬНО:
   - Дисклеймер "ИМЕЮТСЯ ПРОТИВОПОКАЗАНИЯ"
   - Дисклеймер "НЕОБХОДИМА КОНСУЛЬТАЦИЯ СПЕЦИАЛИСТА"
   - Явный контекст народной медицины (не мед. услуги!)

✅ ДОПУСТИМАЯ ТЕРМИНОЛОГИЯ:
   - Нетрадиционная медицина, народный целитель, знахарь
   - Экстрасенс, ясновидящий, гадалка, шаман, колдун
   - Лечение травами, биоэнергетика, заговоры
   - Тибетские, ведические, шаманские методы

❌ НЕ ДОЛЖНО БЫТЬ:
   - Признаков медицинских услуг (врач, клиника, диагноз)
   - Медицинского массажа (народная медицина = шаманский массаж с чакрами)

Примеры:
    # Один баннер
    python scripts/generate_folk_medicine_banners.py --scenario herbs_jars

    # Все сценарии
    python scripts/generate_folk_medicine_banners.py --all-scenarios --output output/folk_medicine/

    # С квантизацией
    python scripts/generate_folk_medicine_banners.py --all-scenarios --quantize 4bit

    # Только сценарии с людьми
    python scripts/generate_folk_medicine_banners.py --with-people --output output/folk_medicine/

    # Проверить текст
    python scripts/generate_folk_medicine_banners.py --validate "Шаманский массаж с раскрытием чакр"
"""

import argparse
import sys
from pathlib import Path
import json
import random
from typing import Dict, List, Optional, Any
import torch
from PIL import Image

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.folk_medicine_overlay import (
    FolkMedicineBannerOverlay,
    FolkMedicineValidator,
    FOLK_MEDICINE_HEADLINES,
    FOLK_MEDICINE_DESCRIPTIONS,
    FOLK_MEDICINE_DISCLAIMERS,
    FOLK_MEDICINE_SCENARIOS,
    FOLK_MEDICINE_SCENARIOS_NO_PEOPLE,
    FOLK_MEDICINE_SCENARIOS_WITH_PEOPLE,
    FOLK_MEDICINE_STYLES,
    DISCLAIMER_BG_STYLES,
    get_random_content,
    generate_phone,
    get_layout_for_scenario,
    get_random_disclaimer_bg_style,
    get_disclaimer_bg_style_by_name,
    # Категории заголовков
    HEALER_HEADLINES,
    PSYCHIC_HEADLINES,
    FORTUNE_TELLER_HEADLINES,
    SHAMAN_HEADLINES,
    SPIRIT_HEADLINES,
    HERBAL_HEADLINES,
    ENERGY_HEADLINES,
    PRAYER_HEADLINES,
)
from scripts.text_overlay import LAYOUTS, get_layout_by_name

# Форматы баннеров
BANNER_FORMATS = {
    "square": (1024, 1024),
    "horizontal": (1200, 700),
    "vertical": (800, 1200),
}

# Негативные промпты для генерации
NEG_PROMPT = "text, words, letters, watermark, logo, cartoon, anime, 3d render, modern medical equipment, hospital, clinic, stethoscope, pills, pharmacy, low quality, blurry, deformed, ugly"
NEG_PROMPT_PERSON = "text, words, letters, watermark, logo, cartoon, anime, 3d render, modern medical equipment, hospital, clinic, stethoscope, pills, pharmacy, low quality, blurry, deformed, ugly, extra limbs, bad anatomy"


class FolkMedicineBannerPipeline:
    """
    Полный пайплайн: генерация фона + наложение текста.
    С валидацией на соответствие законодательству.
    """
    
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
        """Загрузка модели генерации."""
        if self._pipeline is not None:
            return
        
        from pipeline.inference.simple_pipeline import SimpleImagePipeline
        
        print("Загрузка модели...")
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
        seed: int = None,
    ) -> Image.Image:
        """Генерация фонового изображения."""
        self.load()
        
        is_person = scenario.get("has_person") or scenario.get("person_position")
        neg_prompt = NEG_PROMPT_PERSON if is_person else NEG_PROMPT
        
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
    
    def generate_banner(
        self,
        scenario: Dict[str, Any] = None,
        headline: str = None,
        description: str = None,
        phone: str = None,
        disclaimer: str = None,
        layout: Dict = None,
        style: Dict = None,
        disclaimer_bg_style: Dict = None,
        width: int = 1024,
        height: int = 1024,
        num_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: int = None,
    ) -> Image.Image:
        """
        Генерация полного баннера: фон + текст.
        
        Валидирует тексты на соответствие закону.
        """
        scenario = scenario or random.choice(FOLK_MEDICINE_SCENARIOS)
        
        # Подбираем лейаут под сценарий, если не указан
        if layout is None:
            layout = get_layout_for_scenario(scenario)
        
        style = style or random.choice(FOLK_MEDICINE_STYLES)
        
        # Генерируем фон
        print(f"  Генерация фона: {scenario['name']}...")
        background = self.generate_background(
            scenario=scenario,
            width=width,
            height=height,
            num_steps=num_steps,
            guidance_scale=guidance_scale,
            seed=seed,
        )
        
        # Накладываем текст
        disc_bg_name = disclaimer_bg_style['name'] if disclaimer_bg_style else "random"
        print(f"  Наложение текста (стиль: {style['name']}, фон дисклеймера: {disc_bg_name})...")
        overlay = FolkMedicineBannerOverlay(
            layout=layout,
            style=style,
            disclaimer_bg_style=disclaimer_bg_style,
            validate=self.validate,
        )
        
        result = overlay.apply(
            background,
            headline=headline,
            description=description,
            phone=phone,
            disclaimer=disclaimer,
        )
        
        return result
    
    def generate_batch(
        self,
        scenarios: List[Dict],
        output_dir: Path,
        format_name: str = "square",
        variations: int = 1,
        layout: Dict = None,
        style: Dict = None,
        disclaimer_bg_style: Dict = None,
        backgrounds_only: bool = False,
        **kwargs,
    ) -> List[Dict]:
        """Генерация нескольких баннеров."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        if format_name == "custom":
            # Для custom формата используем width и height из kwargs
            w = kwargs.get('width', 1024)
            h = kwargs.get('height', 1024)
        else:
            w, h = BANNER_FORMATS.get(format_name, (1024, 1024))
        results = []
        count = 0
        
        for scenario in scenarios:
            for var in range(variations):
                count += 1
                print(f"\n[{count}] Сценарий: {scenario['name']} (вариация {var+1})")
                
                try:
                    if backgrounds_only:
                        # Генерация только фона без текста
                        print(f"  Генерация фона: {scenario['name']} ({w}x{h})...")
                        image = self.generate_background(
                            scenario=scenario,
                            width=w,
                            height=h,
                            **{k: v for k, v in kwargs.items() if k in ['num_steps', 'guidance_scale', 'seed']}
                        )
                        seed_str = f"_{kwargs.get('seed', random.randint(100000, 999999))}" if kwargs.get('seed') else f"_{random.randint(100000, 999999)}"
                        filename = f"folk_bg_{scenario['name']}_{format_name}_{var:03d}{seed_str}.png"
                        
                        filepath = output_dir / filename
                        image.save(filepath, quality=95)
                        
                        result_item = {
                            "filename": str(filepath),
                            "scenario": scenario['name'],
                            "format": format_name,
                            "has_person": scenario.get('has_person', False),
                        }
                        results.append(result_item)
                    else:
                        # Полный баннер с текстом
                        use_layout = layout if layout else get_layout_for_scenario(scenario)
                        use_style = style if style else random.choice(FOLK_MEDICINE_STYLES)
                        use_disc_bg = disclaimer_bg_style if disclaimer_bg_style else get_random_disclaimer_bg_style()
                        
                        image = self.generate_banner(
                            scenario=scenario,
                            layout=use_layout,
                            style=use_style,
                            disclaimer_bg_style=use_disc_bg,
                            width=w,
                            height=h,
                            **kwargs,
                        )
                        filename = f"folk_{scenario['name']}_{format_name}_{use_style['name']}_{use_disc_bg['name']}_{var:02d}.png"
                        
                        filepath = output_dir / filename
                        image.save(filepath, quality=95)
                        
                        result_item = {
                            "filename": str(filepath),
                            "scenario": scenario['name'],
                            "format": format_name,
                            "has_person": scenario.get('has_person', False),
                            "style": use_style['name'],
                            "disclaimer_bg_style": use_disc_bg['name'],
                        }
                        results.append(result_item)
                    
                    print(f"  ✅ Сохранено: {filepath}")
                    
                except ValueError as e:
                    print(f"  ❌ Ошибка: {e}")
                except Exception as e:
                    print(f"  ❌ Ошибка: {e}")
                    import traceback
                    traceback.print_exc()
        
        return results


def main():
    parser = argparse.ArgumentParser(
        description="Генератор баннеров о народной медицине"
    )
    
    # Сценарии
    parser.add_argument("--scenario", type=str, help="Имя сценария")
    parser.add_argument("--all-scenarios", action="store_true",
                        help="Использовать все сценарии")
    parser.add_argument("--with-people", action="store_true",
                        help="Только сценарии с людьми")
    parser.add_argument("--without-people", action="store_true",
                        help="Только сценарии без людей")
    parser.add_argument("--variations", type=int, default=1,
                        help="Вариаций на сценарий")
    
    # Текст
    parser.add_argument("--headline", type=str, help="Заголовок")
    parser.add_argument("--description", type=str, help="Описание")
    parser.add_argument("--phone", type=str, help="Телефон")
    parser.add_argument("--disclaimer", type=str, help="Дисклеймер")
    
    # Категория заголовков
    parser.add_argument("--category", type=str,
                        choices=["healer", "psychic", "fortune", "shaman", 
                                 "spirit", "herbal", "energy", "prayer"],
                        help="Категория заголовков")
    
    # Стиль
    parser.add_argument("--style", type=str,
                        choices=[s['name'] for s in FOLK_MEDICINE_STYLES],
                        help="Стиль оформления текста")
    parser.add_argument("--layout", type=str,
                        choices=[l['name'] for l in LAYOUTS],
                        help="Лейаут")
    parser.add_argument("--disclaimer-bg-style", type=str,
                        choices=[s['name'] for s in DISCLAIMER_BG_STYLES],
                        help="Стиль фона дисклеймера (по умолчанию - случайный)")
    
    # Генерация
    parser.add_argument("--format", type=str, choices=list(BANNER_FORMATS.keys()), default="square", help="Формат баннера")
    parser.add_argument("--width", type=int, help="Ширина (переопределяет --format)")
    parser.add_argument("--height", type=int, help="Высота (переопределяет --format)")
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--cfg-scale", type=float, default=7.5)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--backgrounds-only", action="store_true", help="Генерировать ТОЛЬКО фоны без текста (чистые фоны)")
    
    # Модель
    parser.add_argument("--quantize", type=str, choices=["4bit", "8bit"])
    parser.add_argument("--device", type=str, default="cuda")
    parser.add_argument("--dtype", type=str, default="fp16",
                        choices=["fp16", "bf16", "fp32"])
    
    # Валидация
    parser.add_argument("--no-validate", action="store_true",
                        help="Отключить проверку законодательства")
    parser.add_argument("--validate", type=str,
                        help="Проверить текст")
    
    # Вывод
    parser.add_argument("--output", type=str, default="output/folk_medicine")
    parser.add_argument("--save-metadata", action="store_true")
    
    # Утилиты
    parser.add_argument("--list-scenarios", action="store_true")
    parser.add_argument("--list-styles", action="store_true")
    parser.add_argument("--list-headlines", action="store_true")
    parser.add_argument("--list-categories", action="store_true")
    parser.add_argument("--list-disclaimer-styles", action="store_true",
                        help="Показать стили фона дисклеймера")
    parser.add_argument("--show-requirements", action="store_true",
                        help="Показать требования законодательства")
    
    args = parser.parse_args()
    
    # Утилиты
    if args.validate:
        issues = FolkMedicineValidator.check_medical_indicators(args.validate)
        has_context = FolkMedicineValidator.check_folk_medicine_context(args.validate)
        
        print(f"\nПроверка: \"{args.validate}\"")
        print("-" * 50)
        
        if issues:
            print("❌ ПРОБЛЕМЫ (признаки мед. услуг):")
            for issue in issues:
                print(f"   {issue}")
        else:
            print("✅ Признаков медицинских услуг не найдено")
        
        if has_context:
            print("✅ Содержит контекст народной медицины")
        else:
            print("⚠️  Не содержит явного контекста народной медицины")
        return
    
    if args.list_scenarios:
        print("\n=== Сценарии фонов ===")
        print("\n[Без людей]:")
        for s in FOLK_MEDICINE_SCENARIOS_NO_PEOPLE:
            print(f"  • {s['name']}")
        print("\n[С людьми]:")
        for s in FOLK_MEDICINE_SCENARIOS_WITH_PEOPLE:
            pos = s.get('person_position', 'center')
            print(f"  • {s['name']} (человек {pos})")
        return
    
    if args.list_styles:
        print("\n=== Стили оформления ===")
        for s in FOLK_MEDICINE_STYLES:
            r, g, b = s['headline_color']
            print(f"  • {s['name']}: RGB({r}, {g}, {b})")
        return
    
    if args.list_headlines:
        print("\n=== Все заголовки ===")
        for h in FOLK_MEDICINE_HEADLINES:
            print(f"  • {h}")
        return
    
    if args.list_categories:
        print("\n=== Категории заголовков ===")
        categories = {
            "healer": ("Целители и знахари", HEALER_HEADLINES),
            "psychic": ("Экстрасенсы и ясновидящие", PSYCHIC_HEADLINES),
            "fortune": ("Гадалки и прорицатели", FORTUNE_TELLER_HEADLINES),
            "shaman": ("Шаманы и духовные практики", SHAMAN_HEADLINES),
            "spirit": ("Спиритизм и магия", SPIRIT_HEADLINES),
            "herbal": ("Траволечение и натуропатия", HERBAL_HEADLINES),
            "energy": ("Энергетические практики", ENERGY_HEADLINES),
            "prayer": ("Молитвы и заговоры", PRAYER_HEADLINES),
        }
        for key, (name, headlines) in categories.items():
            print(f"\n[{key}] {name}:")
            for h in headlines:
                print(f"  • {h}")
        return
    
    if args.list_disclaimer_styles:
        print("\n=== Стили фона дисклеймера ===")
        print("\n[Сплошные (solid)]:")
        for s in DISCLAIMER_BG_STYLES:
            if s['type'] == 'solid':
                alpha = s.get('alpha', 150)
                mult = s.get('height_multiplier', 1.0)
                opacity = "непрозрачный" if alpha >= 220 else "полупрозрачный" if alpha >= 100 else "разряженный"
                height = "вытянутый" if mult >= 1.5 else "сжатый" if mult < 0.8 else "стандартный"
                print(f"  • {s['name']}: {s['description']}")
                print(f"      alpha={alpha} ({opacity}), высота x{mult} ({height})")
        
        print("\n[Градиентные (gradient)]:")
        for s in DISCLAIMER_BG_STYLES:
            if s['type'] == 'gradient':
                mult = s.get('height_multiplier', 1.0)
                print(f"  • {s['name']}: {s['description']}")
                print(f"      alpha: {s.get('alpha_top', 0)} → {s.get('alpha_bottom', 200)}, высота x{mult}")
        return
    
    if args.show_requirements:
        print("""
╔══════════════════════════════════════════════════════════════════╗
║          ТРЕБОВАНИЯ К РЕКЛАМЕ НАРОДНОЙ МЕДИЦИНЫ                  ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  ✅ ОБЯЗАТЕЛЬНО:                                                 ║
║     • Дисклеймер "ИМЕЮТСЯ ПРОТИВОПОКАЗАНИЯ"                      ║
║     • Дисклеймер "НЕОБХОДИМА КОНСУЛЬТАЦИЯ СПЕЦИАЛИСТА"           ║
║     • Явный контекст народной медицины                           ║
║                                                                  ║
║  ✅ ДОПУСТИМАЯ ТЕРМИНОЛОГИЯ:                                     ║
║     • Нетрадиционная медицина                                    ║
║     • Народный целитель, знахарь, гадалка                        ║
║     • Экстрасенс, ясновидящий, колдун, маг, шаман                ║
║     • Лечение травами, энерготерапия, биоэнергетика              ║
║     • Заговоры, молитвы, ритуалы                                 ║
║     • Природные, древние, ведические, тибетские методы           ║
║     • Работа с чакрами, аурой, кармой                            ║
║     • Рейки, аюрведа, натуропатия                                ║
║                                                                  ║
║  ❌ НЕДОПУСТИМО:                                                 ║
║     • Признаки медицинских услуг (врач, клиника)                 ║
║     • Медицинский массаж (но: шаманский массаж — OK!)            ║
║     • Медицинская диагностика, анализы, рецепты                  ║
║                                                                  ║
║  📋 РАЗГРАНИЧЕНИЕ МАССАЖА:                                       ║
║     ❌ "Лечебный массаж поясничной области" — мед. услуга        ║
║     ✅ "Шаманский массаж с раскрытием чакр" — народная медицина  ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
        """)
        return
    
    # Выбор сценариев
    if args.all_scenarios:
        scenarios = FOLK_MEDICINE_SCENARIOS
    elif args.with_people:
        scenarios = FOLK_MEDICINE_SCENARIOS_WITH_PEOPLE
    elif args.without_people:
        scenarios = FOLK_MEDICINE_SCENARIOS_NO_PEOPLE
    elif args.scenario:
        scenarios = [s for s in FOLK_MEDICINE_SCENARIOS if s['name'] == args.scenario]
        if not scenarios:
            print(f"Сценарий '{args.scenario}' не найден!")
            print("Доступные:", [s['name'] for s in FOLK_MEDICINE_SCENARIOS])
            return
    else:
        scenarios = [FOLK_MEDICINE_SCENARIOS[0]]
    
    # Выбор заголовка по категории
    headline = args.headline
    if not headline and args.category:
        category_map = {
            "healer": HEALER_HEADLINES,
            "psychic": PSYCHIC_HEADLINES,
            "fortune": FORTUNE_TELLER_HEADLINES,
            "shaman": SHAMAN_HEADLINES,
            "spirit": SPIRIT_HEADLINES,
            "herbal": HERBAL_HEADLINES,
            "energy": ENERGY_HEADLINES,
            "prayer": PRAYER_HEADLINES,
        }
        headline = random.choice(category_map[args.category])
    
    # Типы данных
    dtype_map = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}
    dtype = dtype_map[args.dtype]
    
    # Создаём пайплайн
    pipeline = FolkMedicineBannerPipeline(
        device=args.device,
        dtype=dtype,
        quantize=args.quantize,
        validate=not args.no_validate,
    )
    
    # Стиль/лейаут
    style = None
    if args.style:
        for s in FOLK_MEDICINE_STYLES:
            if s['name'] == args.style:
                style = s
                break
    
    # Стиль фона дисклеймера
    disclaimer_bg_style = None
    if args.disclaimer_bg_style:
        disclaimer_bg_style = get_disclaimer_bg_style_by_name(args.disclaimer_bg_style)
    
    layout = get_layout_by_name(args.layout) if args.layout else None
    
    # Определяем размеры
    if args.width and args.height:
        w, h = args.width, args.height
        format_name = "custom"
    else:
        w, h = BANNER_FORMATS[args.format]
        format_name = args.format
    
    # Генерация
    output_dir = Path(args.output)
    
    if args.backgrounds_only:
        print(f"\n=== Режим генерации чистых фонов ===")
        print(f"  Формат: {format_name} ({w}x{h})")
        print(f"  Сценариев: {len(scenarios)}")
        print(f"  Вариаций на сценарий: {args.variations}")
    
    results = pipeline.generate_batch(
        scenarios=scenarios,
        output_dir=output_dir,
        format_name=format_name,
        variations=args.variations,
        disclaimer_bg_style=disclaimer_bg_style,
        headline=headline,
        description=args.description,
        phone=args.phone,
        disclaimer=args.disclaimer,
        layout=layout,
        style=style,
        width=w,
        height=h,
        num_steps=args.steps,
        guidance_scale=args.cfg_scale,
        seed=args.seed,
        backgrounds_only=args.backgrounds_only,
    )
    
    # Метаданные
    if args.save_metadata:
        metadata_path = output_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nМетаданные: {metadata_path}")
    
    print(f"\n✅ Создано {len(results)} баннеров в {output_dir}")


if __name__ == "__main__":
    main()
