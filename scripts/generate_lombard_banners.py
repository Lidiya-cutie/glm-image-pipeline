#!/usr/bin/env python3
"""
Full Lombard Ad Banner Generator (Ломбарды)

Полный пайплайн генерации рекламных баннеров услуг ломбардов
с учётом требований ст. 28 ФЗ-38 «О рекламе» и ФЗ-196 «О ломбардах».

ФОРМАТЫ:
- Квадратный: 1024x1024
- Горизонтальный: 1200x700
- Вертикальный: 800x1200

СЦЕНАРИИ:
- 19 фонов БЕЗ людей (7 интерьеров + 12 объект в углу + градиент/абстракция)
- 7 фонов С людьми

Примеры:
    python scripts/generate_lombard_banners.py --scenario office_lombard
    python scripts/generate_lombard_banners.py --all-scenarios --output output/lombard/
    python scripts/generate_lombard_banners.py --with-people
    python scripts/generate_lombard_banners.py --format horizontal --count 10
    python scripts/generate_lombard_banners.py --backgrounds-only --format square
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

from scripts.lombard_overlay import (
    LombardBannerOverlay,
    LombardValidator,
    LOMBARD_HEADLINES,
    LOMBARD_DESCRIPTIONS,
    LOMBARD_DISCLAIMERS,
    LOMBARD_STYLES,
    DISCLAIMER_BG_STYLES,
    get_random_content,
    get_random_company,
    generate_phone,
    get_layout_for_scenario,
    get_random_disclaimer_bg_style,
    get_disclaimer_bg_style_by_name,
    LOMBARD_SCENARIOS,
    LOMBARD_SCENARIOS_NO_PEOPLE,
    LOMBARD_SCENARIOS_WITH_PEOPLE,
)
from scripts.text_overlay import LAYOUTS, get_layout_by_name

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

NEG_PROMPT = "text, words, letters, watermark, logo, cartoon, anime, 3d render, cluttered, bright neon colors, low quality, blurry, deformed"
NEG_PROMPT_PERSON = "text, words, letters, watermark, logo, cartoon, anime, 3d render, cluttered, bright neon colors, low quality, blurry, deformed, extra limbs, bad anatomy"


class LombardBannerPipeline:
    """Полный пайплайн: генерация фона + наложение текста (ст. 28 ФЗ-38 / ФЗ-196)."""

    def __init__(self, device: str = "cuda", dtype: torch.dtype = torch.float16, quantize: str = None, validate: bool = True, add_phone_logos: bool = False, favicons_dir: str = None):
        self.device = device
        self.dtype = dtype
        self.quantize = quantize
        self.validate = validate
        self._pipeline = None
        self._add_phone_logos = add_phone_logos
        self._favicons_dir = favicons_dir

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
        is_person = scenario.get("type") == "person" or scenario.get("has_person") or "person_position" in scenario
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
        legal_entity: str = "",
        source_info: str = "",
        website: str = None,
        layout: Dict = None,
        style: Dict = None,
        disclaimer_bg_style: Dict = None,
        width: int = 1024,
        height: int = 1024,
        num_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: int = None,
        use_real_companies: bool = True,
        add_qr: bool = False,
        qr_chance: float = 50.0,
        add_phone_logos: bool = None,
        favicons_dir: str = None,
    ) -> Image.Image:
        scenario = scenario or random.choice(LOMBARD_SCENARIOS)
        layout = layout or get_layout_for_scenario(scenario)
        style = style or random.choice(LOMBARD_STYLES)
        content = get_random_content(use_real_companies=use_real_companies, website=website, phone=phone)
        headline = headline or content["headline"]
        description = description or content["description"]
        disclaimer = disclaimer or content.get("disclaimer") or random.choice(LOMBARD_DISCLAIMERS)
        phone = phone or content.get("phone") or generate_phone()
        legal_entity = legal_entity or content["legal_entity"]
        source_info = source_info or content["source_info"]
        website = website or content.get("website", "")

        print(f"  Генерация фона: {scenario['name']} ({width}x{height})...")
        background = self.generate_background(scenario=scenario, width=width, height=height, num_steps=num_steps, guidance_scale=guidance_scale, seed=seed)

        overlay = LombardBannerOverlay(
            layout=layout,
            style=style,
            disclaimer_bg_style=disclaimer_bg_style or get_random_disclaimer_bg_style(),
            validate=self.validate,
        )
        
        use_add_phone_logos = add_phone_logos if add_phone_logos is not None else getattr(self, '_add_phone_logos', False)
        use_favicons_dir = favicons_dir if favicons_dir is not None else getattr(self, '_favicons_dir', None)
        
        result_image = overlay.apply(
            background,
            headline=headline,
            description=description,
            phone=phone,
            disclaimer=disclaimer,
            legal_entity=legal_entity,
            source_info=source_info,
            add_phone_logos=use_add_phone_logos,
            favicons_dir=use_favicons_dir,
        )
        
        # Вычисляем позицию дисклеймера для QR (после наложения текста)
        scale = min(width, height) / 1024
        disclaimer_font_size = max(11, int(14 * scale))
        margin = int(min(width, height) * 0.06)
        safe_bottom = height - margin
        disclaimer_y = safe_bottom - disclaimer_font_size * 4
        disclaimer_height = disclaimer_font_size * 4
        
        # Добавляем QR-код, если нужно
        if add_qr and random.random() * 100 < qr_chance:
            qr_url = website or content.get("website", "")
            if qr_url:
                result_image = self._add_qr_code(result_image, qr_url, width, height, disclaimer_y, disclaimer_height)
        
        return result_image
    
    def _add_qr_code(self, image: Image.Image, url: str, width: int, height: int, disclaimer_y: int = None, disclaimer_height: int = None) -> Image.Image:
        """Добавляет QR-код на изображение в нижних углах, выше дисклеймера."""
        if not QR_AVAILABLE:
            return image
        
        try:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            
            pipeline = FolkMedicineQRPipeline(device="cpu")
            qr_type = random.choice(["simple", "artistic_white", "custom_color"])
            qr_img = pipeline.generate_qr_variety(url, qr_type=qr_type)
            
            if qr_img:
                qr_size = min(120, int(min(width, height) * 0.12))
                qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS).convert("RGBA")
                
                from scripts.lombard_overlay import find_safe_qr_position_for_lombard
                
                if disclaimer_y is None:
                    disclaimer_y = int(height * 0.9)
                    disclaimer_height = int(height * 0.1)
                
                qr_pos = find_safe_qr_position_for_lombard(
                    width, height, qr_size, disclaimer_y, disclaimer_height
                )
                
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

    def generate_batch(
        self,
        scenarios: List[Dict],
        output_dir: Path,
        format_name: str = "square",
        variations: int = 1,
        add_qr: bool = False,
        qr_chance: float = 50.0,
        backgrounds_only: bool = False,
        **kwargs,
    ) -> List[Dict]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        if format_name == "custom":
            w = kwargs.get('width', 1024)
            h = kwargs.get('height', 1024)
        else:
            w, h = BANNER_FORMATS.get(format_name, (1024, 1024))
        
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
                            **{k: v for k, v in kwargs.items() if k in ['num_steps', 'guidance_scale', 'seed']}
                        )
                        seed_str = f"_{kwargs.get('seed', random.randint(100000, 999999))}" if kwargs.get('seed') else f"_{random.randint(100000, 999999)}"
                        filename = f"lombard_bg_{scenario['name']}_{format_name}_{var:03d}{seed_str}.png"
                        
                        filepath = output_dir / filename
                        image.save(filepath, quality=95)
                        results.append({
                            "filename": str(filepath),
                            "scenario": scenario['name'],
                            "format": format_name,
                            "has_person": scenario.get('has_person', False),
                        })
                    else:
                        image = self.generate_banner(
                            scenario=scenario,
                            width=w,
                            height=h,
                            add_qr=add_qr,
                            qr_chance=qr_chance,
                            use_real_companies=kwargs.get('use_real_companies', True),
                            num_steps=kwargs.get('num_steps', 50),
                            guidance_scale=kwargs.get('guidance_scale', 7.5),
                            seed=kwargs.get('seed'),
                        )
                        filename = f"lombard_{scenario['name']}_{format_name}_{var:02d}.png"
                        filepath = output_dir / filename
                        image.save(filepath, quality=95)
                        results.append({"filename": str(filepath), "scenario": scenario["name"], "format": format_name})
                    print(f"  ✅ Сохранено: {filepath}")
                except Exception as e:
                    print(f"  ❌ Ошибка: {e}")
                    import traceback
                    traceback.print_exc()
        return results


def main():
    parser = argparse.ArgumentParser(description="Генератор баннеров ломбардов")
    parser.add_argument("--scenario", type=str, help="Имя одного сценария")
    parser.add_argument("--scenarios", type=str, help="Несколько сценариев через запятую (например: rings_emerald_diamond_lower_corner_gradient,necklace_precious_stones_lower_corner_gradient)")
    parser.add_argument("--all-scenarios", action="store_true", help="Все сценарии")
    parser.add_argument("--with-people", action="store_true", help="Только сценарии с людьми")
    parser.add_argument("--without-people", action="store_true", help="Только сценарии без людей")
    parser.add_argument("--format", type=str, choices=list(BANNER_FORMATS), default="square")
    parser.add_argument("--count", type=int, default=1, help="Количество баннеров (при --all-scenarios)")
    parser.add_argument("--output", type=str, default="output/lombard")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--quantize", type=str, choices=["4bit", "8bit"])
    parser.add_argument("--list-scenarios", action="store_true")
    parser.add_argument("--show-requirements", action="store_true")
    parser.add_argument("--no-real-companies", action="store_true", help="Не использовать реальные компании из JSON")
    parser.add_argument("--qr-chance", type=float, default=50.0, help="Вероятность добавления QR-кода (0-100)")
    parser.add_argument("--backgrounds-only", action="store_true", help="Генерировать ТОЛЬКО фоны без текста")
    parser.add_argument("--add-phone-logos", action="store_true", help="Добавлять логотипы после телефона")
    parser.add_argument("--favicons-dir", type=str, default="/mldata/logo_for_qr_extracted", help="Директория с логотипами")
    args = parser.parse_args()

    if args.list_scenarios:
        print("\n=== Сценарии БЕЗ людей ===")
        for s in LOMBARD_SCENARIOS_NO_PEOPLE:
            print(f"  • {s['name']}")
        print("\n=== Сценарии С людьми ===")
        for s in LOMBARD_SCENARIOS_WITH_PEOPLE:
            print(f"  • {s['name']} ({s.get('person_position', '-')})")
        return

    if args.show_requirements:
        print("""
╔══════════════════════════════════════════════════════════════════╗
║          ТРЕБОВАНИЯ К РЕКЛАМЕ ЛОМБАРДОВ                           ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  ✅ ОБЯЗАТЕЛЬНО:                                                 ║
║     • Наименование юрлица с обязательным словом "Ломбард"        ║
║     • Источник информации (сайт, телефон, адрес)                 ║
║     • Режим работы (8:00-23:00, не круглосуточно!)               ║
║                                                                  ║
║  ❌ ЗАПРЕЩЕНО:                                                   ║
║     • Круглосуточная работа (24 часа) - только 8:00-23:00       ║
║     • Привлечение инвестиций/вкладов                             ║
║     • Гарантированная оценка без оговорок                        ║
║     • Отсутствие ПСК при указании процентных ставок              ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
        """)
        return

    # Выбор сценариев
    if args.all_scenarios:
        scenarios = LOMBARD_SCENARIOS
    elif args.with_people:
        scenarios = LOMBARD_SCENARIOS_WITH_PEOPLE
    elif args.without_people:
        scenarios = LOMBARD_SCENARIOS_NO_PEOPLE
    elif args.scenarios:
        names = [n.strip() for n in args.scenarios.split(",") if n.strip()]
        name_set = set(names)
        scenarios = [s for s in LOMBARD_SCENARIOS if s["name"] in name_set]
        missing = name_set - {s["name"] for s in scenarios}
        if missing:
            print(f"Сценарии не найдены: {missing}")
            return
    elif args.scenario:
        scenarios = [s for s in LOMBARD_SCENARIOS if s['name'] == args.scenario]
        if not scenarios:
            print(f"Сценарий '{args.scenario}' не найден!")
            return
    else:
        scenarios = [LOMBARD_SCENARIOS[0]]

    # Определяем размеры
    if args.width and args.height:
        w, h = args.width, args.height
        format_name = "custom"
    else:
        w, h = BANNER_FORMATS[args.format]
        format_name = args.format

    # Создаём пайплайн
    pipeline = LombardBannerPipeline(
        device="cuda",
        quantize=args.quantize,
        validate=True,
        add_phone_logos=args.add_phone_logos,
        favicons_dir=args.favicons_dir,
    )

    if args.backgrounds_only:
        print(f"\n=== Режим генерации чистых фонов ===")
        print(f"  Формат: {format_name} ({w}x{h})")
        print(f"  Сценариев: {len(scenarios)}")

    results = pipeline.generate_batch(
        scenarios=scenarios,
        output_dir=Path(args.output),
        format_name=format_name,
        variations=args.count,
        add_qr=not args.backgrounds_only,
        qr_chance=args.qr_chance,
        backgrounds_only=args.backgrounds_only,
        width=w,
        height=h,
        num_steps=args.steps,
        guidance_scale=7.5,
        seed=args.seed,
        use_real_companies=not args.no_real_companies,
    )

    print(f"\n✅ Создано {len(results)} баннеров в {args.output}")


if __name__ == "__main__":
    main()
