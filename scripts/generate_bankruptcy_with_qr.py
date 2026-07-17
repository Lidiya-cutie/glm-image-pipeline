#!/usr/bin/env python3
"""
Интегратор для генерации баннеров банкротства с QR-кодами.

Объединяет:
1. Генерацию баннеров банкротства (BankruptcyBannerPipeline)
2. Генерацию QR-кодов из доменов (DomainProcessor)
3. Наложение QR на баннеры с избежанием текста

Особенности:
- QR накладываются только на часть баннеров (настраиваемый процент)
- QR избегают наложения на текст (умное позиционирование)
- Разнообразие типов QR: простые, артистичные, кастомные цветные
- Массовая генерация: 100, 500, 1000, 2000+ баннеров

УСТАНОВКА ЗАВИСИМОСТЕЙ:
    pip install qrcode[pil]>=7.4.2 Pillow>=10.0.0

    Или из custom-qr-generator:
    cd /mldata/custom-qr-generator
    pip install -r requirements.txt

Примеры:
    # Генерация 2000 баннеров с QR (50% с QR)
    python scripts/generate_bankruptcy_with_qr.py --mass-generate 2000 \\
        --qr-percentage 50 \\
        --output output/bankruptcy_with_qr/

    # Быстрая генерация 100 тестовых
    python scripts/generate_bankruptcy_with_qr.py --mass-generate 100 \\
        --qr-percentage 30 \\
        --quantize 4bit \\
        --steps 25
"""

import argparse
import sys
from pathlib import Path
import json
import random
from typing import Dict, List, Optional, Any, Tuple
import time
from datetime import date
import torch
from PIL import Image, ImageDraw, ImageFont
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Импорты для баннеров банкротства
from scripts.generate_bankruptcy_banners import BankruptcyBannerPipeline
from scripts.bankruptcy_overlay import (
    BANKRUPTCY_SCENARIOS,
    BANKRUPTCY_HEADLINES,
    BANKRUPTCY_DESCRIPTIONS,
    BANKRUPTCY_STYLES,
    get_appropriate_disclaimer,
    generate_phone,
    get_random_disclaimer_bg_style,
    STRUCTURED_CONTENT,
    BULLET_LISTS,
    get_random_structured_content,
    get_random_bullet_list,
)

# Импорты для QR-кодов
sys.path.insert(0, str(Path("/mldata/custom-qr-generator")))

# Проверка базовой зависимости qrcode
try:
    import qrcode
except ImportError:
    print("=" * 70)
    print("❌ ОШИБКА: Модуль 'qrcode' не установлен!")
    print("=" * 70)
    print("\nУстановите зависимости:")
    print("  pip install qrcode[pil]>=7.4.2 Pillow>=10.0.0")
    print("\nИли установите все зависимости из custom-qr-generator:")
    print("  cd /mldata/custom-qr-generator")
    print("  pip install -r requirements.txt")
    print("=" * 70)
    sys.exit(1)

try:
    from qr_generator.domain_processor import DomainProcessor, DomainEntry
    from qr_generator.core import QRGenerator
    from qr_generator.artistic import ArtisticQRGenerator, BlendMode
    from qr_generator.styles import QRStyle, ModuleStyle, ColorMode, ErrorCorrection, PRESET_STYLES
except ImportError as e:
    print("=" * 70)
    print("❌ ОШИБКА ИМПОРТА QR ГЕНЕРАТОРА")
    print("=" * 70)
    print(f"\nДетали: {e}")
    print("\nПроверьте:")
    print("  1. Путь /mldata/custom-qr-generator существует")
    print("  2. Установлены зависимости: pip install qrcode[pil] Pillow")
    print("  3. Структура модулей корректна")
    print("\nДля установки зависимостей:")
    print("  cd /mldata/custom-qr-generator")
    print("  pip install -r requirements.txt")
    print("=" * 70)
    sys.exit(1)


class QRPlacementStrategy:
    """Стратегия размещения QR-кода на баннере с избежанием текста."""
    
    # Зоны где обычно находится текст (в процентах от размера изображения)
    TEXT_ZONES = [
        # Левая верхняя (заголовки)
        {"x": (0, 0.5), "y": (0, 0.3)},
        # Левая средняя (описания, телефоны)
        {"x": (0, 0.5), "y": (0.35, 0.65)},
        # Нижняя (дисклеймер)
        {"x": (0, 1.0), "y": (0.75, 1.0)},
        # Правая верхняя (для структурированных)
        {"x": (0.55, 1.0), "y": (0, 0.4)},
    ]
    
    @staticmethod
    def find_safe_position(
        img_width: int,
        img_height: int,
        qr_size: int,
        margin: int = 20,
    ) -> Optional[Tuple[int, int]]:
        """
        Находит безопасную позицию для QR-кода.
        
        Returns:
            (x, y) позиция или None если не найдено
        """
        # Список безопасных зон (углы и края)
        safe_zones = [
            # Правый верхний угол
            {"x": (0.7, 0.95), "y": (0.02, 0.25)},
            # Правый нижний угол
            {"x": (0.7, 0.95), "y": (0.65, 0.93)},
            # Левый верхний угол (если нет заголовка)
            {"x": (0.02, 0.25), "y": (0.02, 0.25)},
            # Центр правой части
            {"x": (0.75, 0.95), "y": (0.4, 0.6)},
        ]
        
        for zone in safe_zones:
            x_min = int(img_width * zone["x"][0])
            x_max = int(img_width * zone["x"][1]) - qr_size
            y_min = int(img_height * zone["y"][0])
            y_max = int(img_height * zone["y"][1]) - qr_size
            
            if x_max > x_min and y_max > y_min:
                # Проверяем что не пересекается с текстовыми зонами
                x = random.randint(x_min, x_max)
                y = random.randint(y_min, y_max)
                
                # Проверка пересечения с текстовыми зонами
                qr_right = x + qr_size
                qr_bottom = y + qr_size
                
                overlaps = False
                for text_zone in QRPlacementStrategy.TEXT_ZONES:
                    tx_min = int(img_width * text_zone["x"][0])
                    tx_max = int(img_width * text_zone["x"][1])
                    ty_min = int(img_height * text_zone["y"][0])
                    ty_max = int(img_height * text_zone["y"][1])
                    
                    # Проверка пересечения прямоугольников
                    if not (qr_right < tx_min or x > tx_max or qr_bottom < ty_min or y > ty_max):
                        overlaps = True
                        break
                
                if not overlaps:
                    return (x, y)
        
        # Если не нашли идеальное место, возвращаем правый верхний угол с отступом
        return (img_width - qr_size - margin, margin)


class BankruptcyQRPipeline:
    """Пайплайн для генерации баннеров банкротства с QR-кодами."""
    
    def __init__(
        self,
        domains_csv: str = "/mldata/traditional_healers_domains.csv",
        favicons_dir: str = "/mldata/LLD_favicons_full_png",
        device: str = "cuda",
        dtype: torch.dtype = torch.float16,
        quantize: Optional[str] = None,
        validate: bool = True,
    ):
        self.banner_pipeline = BankruptcyBannerPipeline(
            device=device,
            dtype=dtype,
            quantize=quantize,
            validate=validate,
        )
        
        # Инициализация QR процессора
        self.domain_processor = DomainProcessor(
            domains_csv=domains_csv,
            favicons_dir=favicons_dir,
        )
        
        self.qr_generator = QRGenerator()
        self.artistic_qr = ArtisticQRGenerator()
        
        # Загружаем домены
        if not self.domain_processor.domains:
            print("⚠️  Домены не загружены, используем заглушку")
            self.domain_processor.load_domains()
    
    def generate_qr_variety(
        self,
        domain: DomainEntry,
        qr_type: str = "random",
    ) -> Image.Image:
        """
        Генерация QR-кода с разнообразием стилей.
        
        Args:
            domain: Домен для QR
            qr_type: Тип QR ("simple", "artistic_white", "artistic_transparent", "custom_color", "random")
        
        Returns:
            PIL Image с QR-кодом
        """
        url = domain.url or f"https://{domain.domain}"
        
        if qr_type == "random":
            qr_type = random.choice([
                "simple",
                "artistic_white",
                "artistic_transparent",
                "custom_color",
            ])
        
        if qr_type == "simple":
            # Простой QR на белом фоне
            style = PRESET_STYLES.get("rounded", QRStyle())
            favicon = self.domain_processor.get_favicon(domain.domain, strategy="random")
            return self.qr_generator.generate(
                data=url,
                style=style,
                logo_path=favicon,
            )
        
        elif qr_type == "artistic_white":
            # Артистичный QR на белом фоне с градиентом
            style = QRStyle(
                module_style=ModuleStyle.ROUNDED,
                color_mode=ColorMode.GRADIENT,
                gradient_center=(50, 50, 150),
                gradient_edge=(150, 50, 50),
                bg_color=(255, 255, 255, 255),
                error_correction=ErrorCorrection.H,
            )
            favicon = self.domain_processor.get_favicon(domain.domain, strategy="random")
            return self.qr_generator.generate(
                data=url,
                style=style,
                logo_path=favicon,
            )
        
        elif qr_type == "artistic_transparent":
            # Артистичный QR на прозрачном фоне
            favicon = self.domain_processor.get_favicon(domain.domain, strategy="random")
            qr_img = self.artistic_qr.generate_transparent(
                data=url,
                size=300,
                fg_color=(0, 0, 0, 220),
                module_style=ModuleStyle.ROUNDED,
            )
            
            # Добавляем логотип если есть
            if favicon:
                logo = Image.open(favicon).convert("RGBA")
                logo_size = int(300 * 0.2)
                logo.thumbnail((logo_size, logo_size), Image.LANCZOS)
                
                # Вставляем логотип в центр
                qr_w, qr_h = qr_img.size
                logo_x = (qr_w - logo.width) // 2
                logo_y = (qr_h - logo.height) // 2
                
                # Белая подложка для логотипа
                bg_size = logo.width + 10, logo.height + 10
                logo_bg = Image.new("RGBA", bg_size, (255, 255, 255, 240))
                logo_bg.paste(logo, (5, 5), logo)
                
                qr_img.paste(logo_bg, (logo_x - 5, logo_y - 5), logo_bg)
            
            return qr_img
        
        elif qr_type == "custom_color":
            # Кастомный цветной QR
            colors = [
                ((34, 139, 34), (255, 255, 255)),  # Зелёный на белом
                ((70, 130, 180), (255, 255, 255)),  # Синий на белом
                ((139, 69, 19), (255, 255, 255)),  # Коричневый на белом
                ((0, 0, 0), (240, 240, 240)),  # Чёрный на сером
            ]
            fg_color, bg_color = random.choice(colors)
            
            style = QRStyle(
                module_style=random.choice([ModuleStyle.ROUNDED, ModuleStyle.CIRCLE]),
                fg_color=fg_color,
                bg_color=(*bg_color, 255),
                error_correction=ErrorCorrection.H,
            )
            favicon = self.domain_processor.get_favicon(domain.domain, strategy="random")
            return self.qr_generator.generate(
                data=url,
                style=style,
                logo_path=favicon,
            )
        
        else:
            # Fallback на простой
            return self.generate_qr_variety(domain, "simple")
    
    def overlay_qr_on_banner(
        self,
        banner: Image.Image,
        qr: Image.Image,
        position: Optional[Tuple[int, int]] = None,
        qr_size: Optional[int] = None,
    ) -> Image.Image:
        """
        Наложение QR-кода на баннер.
        
        Args:
            banner: Изображение баннера
            qr: QR-код
            position: Позиция (x, y), если None - автоматический поиск
            qr_size: Размер QR (если None - авто)
        """
        banner = banner.convert("RGBA")
        qr = qr.convert("RGBA")
        
        img_width, img_height = banner.size
        
        # Определяем размер QR
        if qr_size is None:
            qr_size = min(int(img_width * 0.15), int(img_height * 0.15))
            qr_size = max(150, min(qr_size, 300))  # Ограничения: 150-300px
        
        qr = qr.resize((qr_size, qr_size), Image.LANCZOS)
        
        # Находим безопасную позицию
        if position is None:
            position = QRPlacementStrategy.find_safe_position(
                img_width, img_height, qr_size
            )
        
        if position is None:
            # Fallback: правый верхний угол
            position = (img_width - qr_size - 20, 20)
        
        x, y = position
        
        # Накладываем QR
        result = banner.copy()
        result.paste(qr, (x, y), qr)
        
        return result
    
    def generate_banner_with_qr(
        self,
        add_qr: bool = True,
        qr_type: str = "random",
        banner_type: str = "random",  # "simple", "structured", "bullet", "random"
        **banner_kwargs,
    ) -> Tuple[Image.Image, Dict[str, Any]]:
        """
        Генерация баннера с опциональным QR-кодом.
        
        Returns:
            (image, metadata)
        """
        # Выбираем тип баннера
        if banner_type == "random":
            banner_type = random.choice(["simple", "structured", "bullet"])
        
        # Генерируем баннер
        if banner_type == "structured":
            content = random.choice(STRUCTURED_CONTENT)
            banner = self.banner_pipeline.generate_structured_banner(
                **banner_kwargs
            )
        elif banner_type == "bullet":
            bullet_list = random.choice(BULLET_LISTS)
            banner = self.banner_pipeline.generate_bullet_banner(
                bullet_list=bullet_list,
                position=bullet_list.get("position", "right"),
                **banner_kwargs
            )
        else:  # simple
            banner = self.banner_pipeline.generate_banner(**banner_kwargs)
        
        metadata = {
            "banner_type": banner_type,
            "has_qr": False,
            "qr_type": None,
            "domain": None,
        }
        
        # Добавляем QR если нужно
        if add_qr:
            domain = random.choice(self.domain_processor.domains)
            qr = self.generate_qr_variety(domain, qr_type)
            banner = self.overlay_qr_on_banner(banner, qr)
            
            metadata.update({
                "has_qr": True,
                "qr_type": qr_type,
                "domain": domain.domain,
                "url": domain.url,
            })
        
        return banner, metadata
    
    def generate_mass_with_qr(
        self,
        output_dir: Path,
        total_count: int = 2000,
        qr_percentage: float = 50.0,  # Процент баннеров с QR
        save_stats: bool = True,
        **kwargs,
    ) -> List[Dict]:
        """
        Массовая генерация баннеров с QR-кодами.
        
        Args:
            output_dir: Папка для сохранения
            total_count: Общее количество баннеров
            qr_percentage: Процент баннеров с QR (0-100)
            save_stats: Сохранять статистику
            **kwargs: Параметры для генерации баннеров
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        errors = []
        timing_stats = []
        start_time = time.time()
        
        qr_types = ["simple", "artistic_white", "artistic_transparent", "custom_color"]
        
        print(f"\n{'='*70}")
        print(f"  МАССОВАЯ ГЕНЕРАЦИЯ БАННЕРОВ БАНКРОТСТВА С QR-КОДАМИ")
        print(f"  Дата: {date.today().isoformat()}")
        print(f"  Всего: {total_count} баннеров")
        print(f"  QR на {qr_percentage}% баннеров")
        print(f"  Папка: {output_dir}")
        print(f"{'='*70}\n")
        
        for i in range(total_count):
            banner_start = time.time()
            
            # Решаем добавлять ли QR
            add_qr = random.random() * 100 < qr_percentage
            
            # Случайные параметры
            scenario = random.choice(BANKRUPTCY_SCENARIOS)
            style = random.choice(BANKRUPTCY_STYLES)
            disc_bg = get_random_disclaimer_bg_style()
            seed = random.randint(1, 999999999)
            
            # Тип баннера и QR
            banner_type = random.choice(["simple", "structured", "bullet"])
            qr_type = random.choice(qr_types) if add_qr else None
            
            progress = (i + 1) / total_count * 100
            elapsed = time.time() - start_time
            avg_time = elapsed / (i + 1) if i > 0 else 30
            eta = avg_time * (total_count - i - 1)
            
            print(f"\n[{i+1}/{total_count}] ({progress:.1f}%) ETA: {eta/60:.1f} мин")
            print(f"  Тип: {banner_type} | QR: {'Да' if add_qr else 'Нет'} ({qr_type if add_qr else '-'})")
            print(f"  Сценарий: {scenario['name']}")
            
            try:
                gen_start = time.time()
                
                banner, metadata = self.generate_banner_with_qr(
                    add_qr=add_qr,
                    qr_type=qr_type,
                    banner_type=banner_type,
                    scenario=scenario,
                    style=style,
                    disclaimer_bg_style=disc_bg,
                    seed=seed,
                    **kwargs,
                )
                
                gen_time = time.time() - gen_start
                
                # Сохранение
                filename = f"bankruptcy_qr_{i:05d}_{scenario['name']}_{banner_type}_{seed}.png"
                filepath = output_dir / filename
                
                save_start = time.time()
                banner.save(filepath, quality=95)
                save_time = time.time() - save_start
                
                banner_total = time.time() - banner_start
                
                result_entry = {
                    "id": i,
                    "filename": str(filepath),
                    "scenario": scenario['name'],
                    "style": style['name'],
                    "banner_type": banner_type,
                    "has_qr": metadata["has_qr"],
                    "qr_type": metadata.get("qr_type"),
                    "domain": metadata.get("domain"),
                    "seed": seed,
                    "generation_time_sec": round(gen_time, 2),
                    "total_time_sec": round(banner_total, 2),
                }
                results.append(result_entry)
                
                timing_stats.append({
                    "id": i,
                    "gen_time": gen_time,
                    "total_time": banner_total,
                    "has_qr": add_qr,
                })
                
                print(f"  ✅ Сохранено: {filename} ({gen_time:.1f}s)")
                
            except Exception as e:
                errors.append({"id": i, "error": str(e), "scenario": scenario['name']})
                print(f"  ❌ Ошибка: {e}")
        
        # Итоговая статистика
        total_time = time.time() - start_time
        
        qr_count = sum(1 for r in results if r.get("has_qr"))
        
        print(f"\n{'='*70}")
        print(f"  ГЕНЕРАЦИЯ ЗАВЕРШЕНА")
        print(f"{'='*70}")
        print(f"  📊 Успешно:            {len(results)}/{total_count}")
        print(f"  📱 С QR-кодами:        {qr_count} ({qr_count/len(results)*100:.1f}%)")
        print(f"  ❌ Ошибок:             {len(errors)}")
        print(f"  ⏱️  Общее время:        {total_time/60:.1f} минут")
        if timing_stats:
            avg_time = sum(t['total_time'] for t in timing_stats) / len(timing_stats)
            print(f"  ⚡ Среднее время:      {avg_time:.1f} сек/баннер")
            print(f"  🚀 Скорость:           {3600/avg_time:.0f} баннеров/час")
        print(f"{'='*70}\n")
        
        # Сохранение статистики
        if save_stats:
            stats_path = output_dir / "generation_stats.json"
            with open(stats_path, "w", encoding="utf-8") as f:
                json.dump({
                    "summary": {
                        "total": total_count,
                        "generated": len(results),
                        "with_qr": qr_count,
                        "errors": len(errors),
                        "time_minutes": round(total_time / 60, 2),
                        "qr_percentage": qr_percentage,
                    },
                    "results": results,
                    "errors": errors,
                }, f, indent=2, ensure_ascii=False)
            print(f"📊 Статистика: {stats_path}")
        
        return results


def main():
    parser = argparse.ArgumentParser(
        description="Генератор баннеров банкротства с QR-кодами"
    )
    
    # Массовая генерация
    parser.add_argument("--mass-generate", type=int, metavar="COUNT",
                        help="Массовая генерация N баннеров (например: --mass-generate 2000)")
    parser.add_argument("--qr-percentage", type=float, default=50.0,
                        help="Процент баннеров с QR (0-100, по умолчанию 50)")
    
    # QR настройки
    parser.add_argument("--qr-type", type=str,
                        choices=["simple", "artistic_white", "artistic_transparent", "custom_color", "random"],
                        default="random",
                        help="Тип QR-кода")
    
    # Домены
    parser.add_argument("--domains-csv", type=str,
                        default="/mldata/traditional_healers_domains.csv",
                        help="Путь к CSV с доменами")
    parser.add_argument("--favicons-dir", type=str,
                        default="/mldata/LLD_favicons_full_png",
                        help="Директория с фавиконами")
    
    # Генерация баннеров
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--cfg-scale", type=float, default=7.5)
    parser.add_argument("--seed", type=int)
    
    # Модель
    parser.add_argument("--quantize", type=str, choices=["4bit", "8bit"])
    parser.add_argument("--device", type=str, default="cuda")
    parser.add_argument("--dtype", type=str, default="fp16",
                        choices=["fp16", "bf16", "fp32"])
    
    # Валидация
    parser.add_argument("--no-validate", action="store_true",
                        help="Отключить проверку законодательства")
    
    # Вывод
    parser.add_argument("--output", type=str, default="output/bankruptcy_with_qr")
    
    args = parser.parse_args()
    
    # Типы данных
    dtype_map = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}
    dtype = dtype_map[args.dtype]
    
    # Создаём пайплайн
    pipeline = BankruptcyQRPipeline(
        domains_csv=args.domains_csv,
        favicons_dir=args.favicons_dir,
        device=args.device,
        dtype=dtype,
        quantize=args.quantize,
        validate=not args.no_validate,
    )
    
    output_dir = Path(args.output)
    
    # Массовая генерация
    if args.mass_generate:
        print(f"\n🚀 ЗАПУСК МАССОВОЙ ГЕНЕРАЦИИ: {args.mass_generate} баннеров")
        print(f"   QR на {args.qr_percentage}% баннеров")
        
        results = pipeline.generate_mass_with_qr(
            output_dir=output_dir,
            total_count=args.mass_generate,
            qr_percentage=args.qr_percentage,
            width=args.width,
            height=args.height,
            num_steps=args.steps,
            guidance_scale=args.cfg_scale,
        )
        
        print(f"\n✅ Создано {len(results)} баннеров в {output_dir}")
        return
    
    # Один баннер для теста
    print("\n🚀 Генерация тестового баннера...")
    banner, metadata = pipeline.generate_banner_with_qr(
        add_qr=True,
        qr_type=args.qr_type,
        width=args.width,
        height=args.height,
        num_steps=args.steps,
        guidance_scale=args.cfg_scale,
        seed=args.seed,
    )
    
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / f"test_bankruptcy_qr_{args.seed or 'random'}.png"
    banner.save(filepath, quality=95)
    print(f"✅ Сохранено: {filepath}")
    print(f"   QR: {metadata.get('domain', 'Нет')}")


if __name__ == "__main__":
    main()
