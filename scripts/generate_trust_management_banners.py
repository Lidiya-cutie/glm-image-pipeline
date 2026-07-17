#!/usr/bin/env python3
"""
Full Trust Management Ad Banner Generator (Доверительное управление ценными бумагами/активами)

Полный пайплайн генерации рекламных баннеров услуг доверительного управления
с учётом требований ст. 28 ФЗ-38 «О рекламе».

СТИЛИ: Ориентация на категории адвокаты/банкротство — navy, gold, corporate, professional.
Углубление в финансовую тематику и доверительное управление.

ФОРМАТЫ:
- Квадратный: 1024x1024
- Горизонтальный: 1200x700
- Вертикальный: 800x1200

СЦЕНАРИИ:
- 7 фонов БЕЗ людей
- 7 фонов С людьми

Примеры:
    python scripts/generate_trust_management_banners.py --scenario office_financial
    python scripts/generate_trust_management_banners.py --all-scenarios --output output/trust_management/
    python scripts/generate_trust_management_banners.py --with-people
    python scripts/generate_trust_management_banners.py --format horizontal --count 10
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

from scripts.trust_management_overlay import (
    TrustManagementBannerOverlay,
    TrustManagementValidator,
    TRUST_MANAGEMENT_HEADLINES,
    TRUST_MANAGEMENT_DESCRIPTIONS,
    TRUST_MANAGEMENT_DISCLAIMERS,
    TRUST_MANAGEMENT_STYLES,
    DISCLAIMER_BG_STYLES,
    get_random_content,
    get_random_company,
    generate_phone,
    get_layout_for_scenario,
    get_random_disclaimer_bg_style,
    get_disclaimer_bg_style_by_name,
)
from scripts.text_overlay import LAYOUTS, get_layout_by_name

# QR pipeline (optional)
try:
    from scripts.generate_folk_medicine_with_qr_2 import FolkMedicineQRPipeline
    from scripts.folk_dual_composition import find_safe_qr_position
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False
    find_safe_qr_position = None

# =============================================================================
# Сценарии фонов — 7 БЕЗ людей (финансовая тематика, офисы, портфели)
# =============================================================================
TRUST_MANAGEMENT_SCENARIOS_NO_PEOPLE = [
    {
        "name": "office_financial",
        "prompt": "professional asset management office interior, modern desk with financial charts and portfolio documents, dark navy blue color scheme, soft professional lighting, business atmosphere, no people, clean empty space, 8k quality, corporate finance",
        "has_person": False,
    },
    {
        "name": "trading_desk_abstract",
        "prompt": "abstract financial trading desk background, multiple monitors with stock charts, dark blue and gold accents, professional investment atmosphere, no people, sleek modern design, 8k quality",
        "has_person": False,
    },
    {
        "name": "portfolio_documents",
        "prompt": "professional desk with investment portfolio documents, financial reports, dark wood surface, navy blue and burgundy color scheme, soft ambient lighting, business law finance atmosphere, no people, 8k quality",
        "has_person": False,
    },
    {
        "name": "bank_vault_abstract",
        "prompt": "abstract secure vault or treasury background, dark blue gradient, subtle gold accents, trust and security concept, minimalist corporate design, no people, 8k quality",
        "has_person": False,
    },
    {
        "name": "charts_wall",
        "prompt": "wall with financial charts and graphs, stock market visualization, dark navy blue corporate colors, professional investment atmosphere, clean composition, no people, 8k quality",
        "has_person": False,
    },
    {
        "name": "library_finance",
        "prompt": "elegant finance library background, investment and economics books on wooden shelves, brass lamp, warm professional lighting, dark mahogany and navy blue, classic authoritative style, no people, 8k",
        "has_person": False,
    },
    {
        "name": "gradient_financial",
        "prompt": "smooth professional gradient background, dark navy blue to black, subtle financial pattern, elegant corporate design, clean minimalist style, perfect for text overlay, trust management concept, 8k quality",
        "has_person": False,
    },
]

# =============================================================================
# Сценарии фонов — 7 С людьми (управляющие, инвесторы, консультанты)
# =============================================================================
TRUST_MANAGEMENT_SCENARIOS_WITH_PEOPLE = [
    {
        "name": "portfolio_manager_right",
        "prompt": "professional portfolio manager in dark suit, confident businessman, standing on right side of frame, modern finance office background, charts on screen, soft lighting, corporate style, space for text on left, high quality portrait, 8k",
        "has_person": True,
        "person_position": "right",
    },
    {
        "name": "advisor_portrait_left",
        "prompt": "professional female financial advisor, confident businesswoman in elegant suit, standing on left side of frame, asset management office with books background, professional lighting, space for text on right, corporate photo, 8k",
        "has_person": True,
        "person_position": "left",
    },
    {
        "name": "manager_desk",
        "prompt": "professional asset manager sitting at desk, businessman in suit, office interior, financial charts behind, looking at camera, confident pose, bottom half of frame, space for text at top, corporate portrait, 8k",
        "has_person": True,
        "person_position": "bottom",
    },
    {
        "name": "investor_consultation",
        "prompt": "financial advisor in navy suit discussing with client, professional office, documents on table, soft natural lighting, person on right side, space on left for text, trust and consultation atmosphere, 8k quality",
        "has_person": True,
        "person_position": "right",
    },
    {
        "name": "wealth_manager_left",
        "prompt": "experienced wealth manager, gray-haired professional in dark suit, standing on left side, modern office with city view, confident posture, space for text on right, high-end finance atmosphere, 8k",
        "has_person": True,
        "person_position": "left",
    },
    {
        "name": "analyst_desk",
        "prompt": "financial analyst at desk with multiple monitors, young professional in shirt, focused expression, charts and data on screens, office background, person in center lower half, space at top for text, 8k quality",
        "has_person": True,
        "person_position": "center",
    },
    {
        "name": "executive_portrait_right",
        "prompt": "senior executive of asset management company, distinguished businessman in elegant suit, standing on right side, prestigious office interior, warm lighting, space for text on left, authoritative corporate style, 8k",
        "has_person": True,
        "person_position": "right",
    },
]

TRUST_MANAGEMENT_SCENARIOS = TRUST_MANAGEMENT_SCENARIOS_NO_PEOPLE + TRUST_MANAGEMENT_SCENARIOS_WITH_PEOPLE

# Форматы баннеров
BANNER_FORMATS = {
    "square": (1024, 1024),
    "horizontal": (1200, 700),
    "vertical": (800, 1200),
}

NEG_PROMPT = "text, words, letters, watermark, logo, cartoon, anime, 3d render, cluttered, bright neon colors, low quality, blurry, deformed"
NEG_PROMPT_PERSON = "text, words, letters, watermark, logo, cartoon, anime, 3d render, cluttered, bright neon colors, low quality, blurry, deformed, extra limbs, bad anatomy"


class TrustManagementBannerPipeline:
    """Полный пайплайн: генерация фона + наложение текста (ст. 28 ФЗ-38)."""

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
        scenario = scenario or random.choice(TRUST_MANAGEMENT_SCENARIOS)
        layout = layout or get_layout_for_scenario(scenario)
        style = style or random.choice(TRUST_MANAGEMENT_STYLES)
        content = get_random_content(use_real_companies=use_real_companies, website=website, phone=phone)
        headline = headline or content["headline"]
        description = description or content["description"]
        disclaimer = disclaimer or random.choice(TRUST_MANAGEMENT_DISCLAIMERS)
        phone = phone or content.get("phone") or generate_phone()
        legal_entity = legal_entity or content["legal_entity"]
        source_info = source_info or content["source_info"]
        website = website or content.get("website", "")

        print(f"  Генерация фона: {scenario['name']} ({width}x{height})...")
        background = self.generate_background(scenario=scenario, width=width, height=height, num_steps=num_steps, guidance_scale=guidance_scale, seed=seed)

        overlay = TrustManagementBannerOverlay(
            layout=layout,
            style=style,
            disclaimer_bg_style=disclaimer_bg_style or get_random_disclaimer_bg_style(),
            validate=self.validate,
        )
        
        result_image = overlay.apply(
            background,
            headline=headline,
            description=description,
            phone=phone,
            disclaimer=disclaimer,
            legal_entity=legal_entity,
            source_info=source_info,
            add_phone_logos=getattr(self, '_add_phone_logos', False),
            favicons_dir=getattr(self, '_favicons_dir', None),
        )
        
        # Вычисляем позицию дисклеймера для QR (после наложения текста)
        scale = min(width, height) / 1024
        disclaimer_font_size = max(11, int(14 * scale))
        disclaimer_y = int(height - disclaimer_font_size * 4)
        disclaimer_height = int(disclaimer_font_size * 3)
        
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
            # Убеждаемся, что URL начинается с http/https
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            
            pipeline = FolkMedicineQRPipeline(device="cpu")
            qr_type = random.choice(["simple", "artistic_white", "custom_color"])
            qr_img = pipeline.generate_qr_variety(url, qr_type=qr_type)
            
            if qr_img:
                qr_size = min(120, int(min(width, height) * 0.12))
                qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS).convert("RGBA")
                
                # Используем специальную функцию для trust_management, учитывающую дисклеймер
                from scripts.trust_management_overlay import find_safe_qr_position_for_trust_management
                
                # Вычисляем позицию дисклеймера, если не передана
                if disclaimer_y is None:
                    # Дисклеймер обычно внизу, занимает ~10% высоты
                    disclaimer_y = int(height * 0.9)
                    disclaimer_height = int(height * 0.1)
                
                qr_pos = find_safe_qr_position_for_trust_management(
                    width, height, qr_size, disclaimer_y, disclaimer_height
                )
                
                # Проверяем, что QR не выходит за границы изображения
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
        **kwargs,
    ) -> List[Dict]:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        w, h = BANNER_FORMATS.get(format_name, (1024, 1024))
        results = []
        for scenario in scenarios:
            for var in range(variations):
                try:
                    image = self.generate_banner(
                        scenario=scenario,
                        width=w,
                        height=h,
                        add_qr=add_qr,
                        qr_chance=qr_chance,
                        **kwargs
                    )
                    filename = f"trust_mgmt_{scenario['name']}_{format_name}_{var:02d}.png"
                    filepath = output_dir / filename
                    image.save(filepath, quality=95)
                    results.append({"filename": str(filepath), "scenario": scenario["name"], "format": format_name})
                    print(f"  ✅ Сохранено: {filepath}")
                except Exception as e:
                    print(f"  ❌ Ошибка: {e}")
        return results


def main():
    parser = argparse.ArgumentParser(description="Генератор баннеров доверительного управления")
    parser.add_argument("--scenario", type=str, help="Имя сценария")
    parser.add_argument("--all-scenarios", action="store_true", help="Все сценарии")
    parser.add_argument("--with-people", action="store_true", help="Только сценарии с людьми")
    parser.add_argument("--without-people", action="store_true", help="Только сценарии без людей")
    parser.add_argument("--format", type=str, choices=list(BANNER_FORMATS), default="square")
    parser.add_argument("--count", type=int, default=1, help="Количество баннеров (при --all-scenarios)")
    parser.add_argument("--output", type=str, default="output/trust_management")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--quantize", type=str, choices=["4bit", "8bit"])
    parser.add_argument("--list-scenarios", action="store_true")
    parser.add_argument("--show-requirements", action="store_true")
    parser.add_argument("--no-real-companies", action="store_true", help="Не использовать реальные компании из JSON (использовать шаблоны)")
    parser.add_argument("--qr-chance", type=float, default=50.0, help="Вероятность добавления QR-кода (0-100, по умолчанию 50)")
    parser.add_argument("--backgrounds-only", action="store_true", help="Генерировать ТОЛЬКО фоны без текста (чистые фоны)")
    parser.add_argument("--add-phone-logos", action="store_true", help="Добавлять логотипы после телефона (если телефон в формате +7)")
    parser.add_argument("--favicons-dir", type=str, default="/mldata/logo_for_qr_extracted", help="Директория с логотипами для телефона")
    args = parser.parse_args()

    if args.list_scenarios:
        print("\n=== Сценарии БЕЗ людей ===")
        for s in TRUST_MANAGEMENT_SCENARIOS_NO_PEOPLE:
            print(f"  • {s['name']}")
        print("\n=== Сценарии С людьми ===")
        for s in TRUST_MANAGEMENT_SCENARIOS_WITH_PEOPLE:
            print(f"  • {s['name']} ({s.get('person_position', '-')})")
        return

    if args.show_requirements:
        print("""
╔══════════════════════════════════════════════════════════════════╗
║   ТРЕБОВАНИЯ К РЕКЛАМЕ ДОВЕРИТЕЛЬНОГО УПРАВЛЕНИЯ (ст. 28 ФЗ-38)   ║
╠══════════════════════════════════════════════════════════════════╣
║  ✅ ОБЯЗАТЕЛЬНО:                                                 ║
║     • Наименование юрлица (ООО/АО + название)                    ║
║     • Источник информации (сайт, телефон, адрес)                 ║
║     • Предупреждение о рисках                                    ║
║  ❌ ЗАПРЕЩЕНО:                                                   ║
║     • Гарантии доходности                                        ║
║     • Прогнозы на основе прошлых результатов без оговорки        ║
║     • Неподтверждённые утверждения                               ║
╚══════════════════════════════════════════════════════════════════╝
        """)
        return

    if args.all_scenarios:
        scenarios = TRUST_MANAGEMENT_SCENARIOS
    elif args.with_people:
        scenarios = TRUST_MANAGEMENT_SCENARIOS_WITH_PEOPLE
    elif args.without_people:
        scenarios = TRUST_MANAGEMENT_SCENARIOS_NO_PEOPLE
    elif args.scenario:
        scenarios = [s for s in TRUST_MANAGEMENT_SCENARIOS if s["name"] == args.scenario]
        if not scenarios:
            print(f"Сценарий '{args.scenario}' не найден")
            return
    else:
        scenarios = [TRUST_MANAGEMENT_SCENARIOS[0]]

    w, h = BANNER_FORMATS[args.format]
    if args.width:
        w = args.width
    if args.height:
        h = args.height

    dtype_map = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}
    pipeline = TrustManagementBannerPipeline(
        quantize=args.quantize,
        validate=True,
        add_phone_logos=args.add_phone_logos,
        favicons_dir=args.favicons_dir,
    )

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    count = args.count if args.all_scenarios else len(scenarios)
    
    # Режим генерации только фонов
    if args.backgrounds_only:
        print(f"\n{'='*70}")
        print(f"  ГЕНЕРАЦИЯ ЧИСТЫХ ФОНОВ (БЕЗ ТЕКСТА)")
        print(f"  Всего: {count} фонов")
        print(f"  Формат: {args.format} ({w}x{h})")
        print(f"{'='*70}\n")
        
        for i in range(count):
            scenario = random.choice(scenarios) if args.all_scenarios and count > 1 else scenarios[i % len(scenarios)]
            print(f"[{i+1}/{count}] Сценарий: {scenario['name']}")
            try:
                image = pipeline.generate_background(
                    scenario=scenario,
                    width=w,
                    height=h,
                    num_steps=args.steps,
                    seed=args.seed,
                )
                fn = f"trust_bg_{scenario['name']}_{args.format}_{i:03d}_{args.seed or random.randint(100000, 999999)}.png"
                fp = output_dir / fn
                image.save(fp, quality=95)
                print(f"  ✅ Сохранено: {fp}")
            except Exception as e:
                print(f"  ❌ Ошибка: {e}")
    else:
        # Обычный режим: фоны + текст
        for i in range(count):
            scenario = random.choice(scenarios) if args.all_scenarios and count > 1 else scenarios[i % len(scenarios)]
            print(f"\n[{i+1}/{count}] Сценарий: {scenario['name']}")
            try:
                image = pipeline.generate_banner(
                    scenario=scenario,
                    width=w,
                    height=h,
                    num_steps=args.steps,
                    seed=args.seed,
                    use_real_companies=not args.no_real_companies,
                    add_qr=True,
                    qr_chance=args.qr_chance,
                )
                fn = f"trust_mgmt_{scenario['name']}_{args.format}_{i:03d}.png"
                fp = output_dir / fn
                image.save(fp, quality=95)
                print(f"  ✅ {fp}")
            except Exception as e:
                print(f"  ❌ {e}")

    print(f"\n✅ Готово. Результаты в {output_dir}")


if __name__ == "__main__":
    main()
