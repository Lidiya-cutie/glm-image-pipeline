#!/usr/bin/env python3
"""
Массовая генерация баннеров народной медицины с QR-кодами.

Объединяет:
1. Генерацию баннеров народной медицины (FolkMedicineBannerPipeline)
2. Генерацию QR-кодов с логотипами из /mldata/logo_for_qr.rar
3. Наложение QR на баннеры с избежанием текста

Особенности:
- Массовая генерация: 100, 500, 1000, 2000+ баннеров
- QR накладываются только на часть баннеров (настраиваемый процент)
- QR избегают наложения на текст (умное позиционирование)
- Разнообразие типов QR: простые, артистичные, кастомные цветные
- Логотипы из архива /mldata/logo_for_qr.rar

УСТАНОВКА ЗАВИСИМОСТЕЙ:
    pip install qrcode[pil]>=7.4.2 Pillow>=10.0.0

Примеры:
    # Массовая генерация 2000 баннеров с QR (50% с QR)
    python scripts/generate_folk_medicine_with_qr.py --mass-generate 2000 \\
        --qr-percentage 50 \\
        --output output/folk_medicine_with_qr/

    # Быстрая генерация 100 тестовых
    python scripts/generate_folk_medicine_with_qr.py --mass-generate 100 \\
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
import shutil
import subprocess

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Импорты для баннеров народной медицины
from scripts.generate_folk_medicine_banners import FolkMedicineBannerPipeline
from scripts.folk_medicine_overlay_2 import (
    FOLK_MEDICINE_SCENARIOS,
    FOLK_MEDICINE_HEADLINES,
    FOLK_MEDICINE_DESCRIPTIONS,
    FOLK_MEDICINE_STYLES,
    get_random_content,
    generate_phone,
    get_random_disclaimer_bg_style,
    DISCLAIMER_BG_STYLES,
    get_layout_for_scenario,
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
    print("=" * 70)
    sys.exit(1)

try:
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
    print("=" * 70)
    sys.exit(1)


class LogoManager:
    """Менеджер для работы с логотипами из архива."""
    
    def __init__(self, archive_path: str = "/mldata/logo_for_qr.rar", extract_dir: str = "/mldata/logo_for_qr_extracted"):
        self.archive_path = Path(archive_path)
        self.extract_dir = Path(extract_dir)
        self.logos: List[Path] = []
        
        # Распаковываем архив если нужно
        self._ensure_extracted()
        
        # Загружаем логотипы
        self._load_logos()
    
    def _ensure_extracted(self):
        """Распаковывает архив если папка не существует или пуста."""
        if self.extract_dir.exists() and any(self.extract_dir.iterdir()):
            return
        
        print(f"📦 Распаковка архива {self.archive_path}...")
        self.extract_dir.mkdir(parents=True, exist_ok=True)
        
        # Пробуем разные способы распаковки
        success = False
        
        # Способ 1: unrar через subprocess
        try:
            result = subprocess.run(
                ["unrar", "x", "-o+", str(self.archive_path), str(self.extract_dir)],
                capture_output=True,
                timeout=30
            )
            if result.returncode == 0:
                success = True
                print("  ✅ Распаковано через unrar")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # Способ 2: python-rarfile
        if not success:
            try:
                import rarfile
                rf = rarfile.RarFile(self.archive_path)
                rf.extractall(self.extract_dir)
                success = True
                print("  ✅ Распаковано через python-rarfile")
            except ImportError:
                print("  ⚠️  Установите: pip install rarfile")
            except Exception as e:
                print(f"  ⚠️  Ошибка распаковки: {e}")
        
        # Способ 3: 7z
        if not success:
            try:
                result = subprocess.run(
                    ["7z", "x", str(self.archive_path), f"-o{self.extract_dir}"],
                    capture_output=True,
                    timeout=30
                )
                if result.returncode == 0:
                    success = True
                    print("  ✅ Распаковано через 7z")
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
        
        if not success:
            print("  ⚠️  Не удалось распаковать автоматически.")
            print(f"  Распакуйте вручную: {self.archive_path} -> {self.extract_dir}")
    
    def _load_logos(self):
        """Загружает список логотипов из папки."""
        if not self.extract_dir.exists():
            print(f"⚠️  Папка {self.extract_dir} не существует")
            return
        
        # Ищем изображения
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}
        self.logos = [
            f for f in self.extract_dir.rglob('*')
            if f.suffix.lower() in image_extensions and f.is_file()
        ]
        
        if self.logos:
            print(f"  ✅ Загружено {len(self.logos)} логотипов")
        else:
            print(f"  ⚠️  Логотипы не найдены в {self.extract_dir}")
    
    def get_random_logo(self) -> Optional[Path]:
        """Возвращает случайный логотип."""
        if self.logos:
            return random.choice(self.logos)
        return None
    
    def get_logo_by_index(self, index: int) -> Optional[Path]:
        """Возвращает логотип по индексу."""
        if 0 <= index < len(self.logos):
            return self.logos[index]
        return None


class QRPlacementStrategy:
    """Стратегия размещения QR-кода на баннере с избежанием текста."""
    
    @staticmethod
    def get_text_zones_for_layout(layout_name: str, img_width: int, img_height: int) -> List[Dict]:
        """
        Возвращает текстовые зоны в зависимости от лейаута.
        
        Args:
            layout_name: Имя лейаута ("classic_left", "classic_right", "center_stack", "top_bottom", "diagonal")
            img_width: Ширина изображения
            img_height: Высота изображения
        
        Returns:
            Список текстовых зон {"x": (min, max), "y": (min, max)}
        """
        if layout_name == "classic_right":
            # Текст справа - зоны справа И слева (телефон может быть перемещён налево)
            # Расширяем зоны для более надёжного покрытия
            return [
                {"x": (0.45, 1.0), "y": (0, 0.35)},      # Правая верхняя (заголовки) - расширено
                {"x": (0.45, 1.0), "y": (0.30, 0.80)},   # Правая средняя (описания, телефоны справа) - расширено
                {"x": (0, 0.55), "y": (0.30, 0.80)},     # Левая средняя (телефоны слева при длинном тексте) - расширено
                {"x": (0, 1.0), "y": (0.70, 1.0)},       # Нижняя (дисклеймер) - расширено
            ]
        elif layout_name == "center_stack":
            # Текст по центру - зоны по центру, но телефон может быть в углу
            return [
                {"x": (0.15, 0.85), "y": (0, 0.35)},     # Центр верх (заголовки) - расширено
                {"x": (0.15, 0.85), "y": (0.30, 0.80)},  # Центр средний (описания, телефоны по центру) - расширено
                {"x": (0.65, 1.0), "y": (0, 0.35)},      # Правый верхний (телефон может быть здесь) - расширено
                {"x": (0, 1.0), "y": (0.70, 1.0)},       # Нижняя (дисклеймер) - расширено
            ]
        elif layout_name == "top_bottom":
            # Текст сверху и снизу - зоны по центру
            return [
                {"x": (0.1, 0.9), "y": (0, 0.5)},     # Верхняя часть (заголовки, описания)
                {"x": (0.1, 0.9), "y": (0.55, 0.7)},  # Средняя (телефоны)
                {"x": (0, 1.0), "y": (0.75, 1.0)},    # Нижняя (дисклеймер)
            ]
        elif layout_name == "diagonal":
            # Диагональ - текст слева-сверху и справа-снизу
            return [
                {"x": (0, 0.5), "y": (0, 0.3)},       # Левая верхняя (заголовки)
                {"x": (0.5, 1.0), "y": (0.5, 0.75)}, # Правая нижняя (описания, телефоны)
                {"x": (0, 1.0), "y": (0.75, 1.0)},   # Нижняя (дисклеймер)
            ]
        else:  # classic_left (по умолчанию)
            # Текст слева - зоны слева И справа (телефон может быть перемещён направо)
            return [
                {"x": (0, 0.55), "y": (0, 0.35)},      # Левая верхняя (заголовки) - расширено
                {"x": (0, 0.55), "y": (0.30, 0.80)},   # Левая средняя (описания, телефоны слева) - расширено
                {"x": (0.45, 1.0), "y": (0.30, 0.80)}, # Правая средняя (телефоны справа при длинном тексте) - расширено
                {"x": (0, 1.0), "y": (0.70, 1.0)},     # Нижняя (дисклеймер) - расширено
            ]
    
    @staticmethod
    def find_safe_position(
        img_width: int,
        img_height: int,
        qr_size: int,
        layout_name: str = "classic_left",
        margin: int = 20,
    ) -> Optional[Tuple[int, int]]:
        """
        Находит безопасную позицию для QR-кода с учётом лейаута.
        
        Args:
            img_width: Ширина изображения
            img_height: Высота изображения
            qr_size: Размер QR-кода
            layout_name: Имя лейаута для определения текстовых зон
            margin: Отступ от краёв
        
        Returns:
            (x, y) позиция или None если не найдено
        """
        # Получаем текстовые зоны для данного лейаута
        text_zones = QRPlacementStrategy.get_text_zones_for_layout(layout_name, img_width, img_height)
        
        # Определяем безопасные зоны в зависимости от лейаута
        if layout_name == "classic_right":
            # Текст справа - QR слева, но избегаем области где может быть телефон
            # Телефон может быть справа (0.45-1.0, 0.30-0.80) или слева (0-0.55, 0.30-0.80)
            # Размещаем QR в левых углах, строго избегая средней части слева где может быть телефон
            safe_zones = [
                {"x": (0.02, 0.20), "y": (0.02, 0.25)},  # Левый верхний угол (строго выше возможного телефона 0.30)
                {"x": (0.02, 0.20), "y": (0.82, 0.93)},  # Левый нижний угол (строго ниже возможного телефона 0.80)
                # Избегаем левую среднюю часть (0-0.55, 0.30-0.80) где может быть телефон
            ]
        elif layout_name == "center_stack":
            # Текст по центру - QR в углах, избегая правого верхнего где может быть телефон
            safe_zones = [
                {"x": (0.02, 0.25), "y": (0.02, 0.25)},  # Левый верхний угол
                {"x": (0.75, 0.95), "y": (0.65, 0.93)},  # Правый нижний угол
                {"x": (0.02, 0.25), "y": (0.65, 0.93)},  # Левый нижний угол
                # Избегаем правый верхний где может быть телефон при длинном тексте
            ]
        elif layout_name == "top_bottom":
            # Текст сверху и снизу - QR в углах
            safe_zones = [
                {"x": (0.75, 0.95), "y": (0.02, 0.25)},  # Правый верхний угол
                {"x": (0.02, 0.25), "y": (0.02, 0.25)},  # Левый верхний угол
                {"x": (0.75, 0.95), "y": (0.65, 0.93)},  # Правый нижний угол
            ]
        elif layout_name == "diagonal":
            # Диагональ - QR в свободных углах
            safe_zones = [
                {"x": (0.75, 0.95), "y": (0.02, 0.25)},  # Правый верхний угол
                {"x": (0.02, 0.25), "y": (0.65, 0.93)},  # Левый нижний угол
            ]
        else:  # classic_left
            # Текст слева - QR справа, но избегаем области где может быть телефон
            # Телефон может быть слева (0-0.55, 0.30-0.80) или справа (0.45-1.0, 0.30-0.80)
            # Размещаем QR в правых углах, строго избегая средней части справа где может быть телефон
            safe_zones = [
                {"x": (0.75, 0.95), "y": (0.02, 0.25)},  # Правый верхний угол (строго выше возможного телефона 0.30)
                {"x": (0.75, 0.95), "y": (0.82, 0.93)},  # Правый нижний угол (строго ниже возможного телефона 0.80)
                # Избегаем правую среднюю часть (0.45-1.0, 0.30-0.80) где может быть телефон
            ]
        
            # Пробуем каждую безопасную зону
        for zone in safe_zones:
            x_min = int(img_width * zone["x"][0])
            x_max = int(img_width * zone["x"][1]) - qr_size
            y_min = int(img_height * zone["y"][0])
            y_max = int(img_height * zone["y"][1]) - qr_size
            
            if x_max >= x_min and y_max >= y_min:
                # Пробуем несколько позиций в зоне
                for attempt in range(10):  # Увеличиваем количество попыток
                    if x_max == x_min:
                        x = x_min
                    else:
                        x = random.randint(x_min, x_max)
                    
                    if y_max == y_min:
                        y = y_min
                    else:
                        y = random.randint(y_min, y_max)
                    
                    # Добавляем дополнительный отступ от текстовых зон
                    safety_margin = int(qr_size * 0.15)  # 15% от размера QR как отступ (увеличено)
                    
                    # Проверка пересечения с текстовыми зонами с учётом отступа
                    qr_right = x + qr_size + safety_margin
                    qr_bottom = y + qr_size + safety_margin
                    qr_left = max(0, x - safety_margin)  # Не выходим за границы
                    qr_top = max(0, y - safety_margin)
                    
                    overlaps = False
                    for text_zone in text_zones:
                        tx_min = int(img_width * text_zone["x"][0])
                        tx_max = int(img_width * text_zone["x"][1])
                        ty_min = int(img_height * text_zone["y"][0])
                        ty_max = int(img_height * text_zone["y"][1])
                        
                        # Проверка пересечения прямоугольников с учётом отступа
                        # Пересечение если НЕ (QR полностью слева/справа/сверху/снизу от текста)
                        # Используем строгую проверку: если любая часть QR попадает в текстовую зону
                        if not (qr_right <= tx_min or qr_left >= tx_max or qr_bottom <= ty_min or qr_top >= ty_max):
                            overlaps = True
                            break
                    
                    if not overlaps:
                        # Дополнительная проверка: убеждаемся что QR не слишком близко к текстовым зонам
                        min_distance_ok = True
                        for text_zone in text_zones:
                            tx_min = int(img_width * text_zone["x"][0])
                            tx_max = int(img_width * text_zone["x"][1])
                            ty_min = int(img_height * text_zone["y"][0])
                            ty_max = int(img_height * text_zone["y"][1])
                            
                            # Проверяем минимальное расстояние до текстовой зоны
                            qr_center_x = x + qr_size // 2
                            qr_center_y = y + qr_size // 2
                            
                            # Расстояние до ближайшей точки текстовой зоны
                            nearest_x = max(tx_min, min(qr_center_x, tx_max))
                            nearest_y = max(ty_min, min(qr_center_y, ty_max))
                            
                            distance_x = abs(qr_center_x - nearest_x)
                            distance_y = abs(qr_center_y - nearest_y)
                            
                            # Минимальное расстояние должно быть больше размера QR
                            if distance_x < qr_size * 0.3 or distance_y < qr_size * 0.3:
                                min_distance_ok = False
                                break
                        
                        if min_distance_ok:
                            return (x, y)
        
        # Если не нашли идеальное место, используем fallback в зависимости от лейаута
        if layout_name == "classic_right":
            # Fallback: левый верхний угол, но проверяем что не пересекается
            fallback_x = margin
            fallback_y = margin
            # Убеждаемся что fallback не в текстовой зоне
            for text_zone in text_zones:
                tx_min = int(img_width * text_zone["x"][0])
                tx_max = int(img_width * text_zone["x"][1])
                ty_min = int(img_height * text_zone["y"][0])
                ty_max = int(img_height * text_zone["y"][1])
                if (tx_min <= fallback_x + qr_size <= tx_max and ty_min <= fallback_y + qr_size <= ty_max):
                    # Если fallback пересекается, используем более безопасную позицию
                    fallback_x = margin
                    fallback_y = int(img_height * 0.85)  # Ещё ниже
            return (fallback_x, fallback_y)
        elif layout_name == "center_stack" or layout_name == "top_bottom":
            # Fallback: правый верхний угол
            return (img_width - qr_size - margin, margin)
        else:  # classic_left, diagonal
            # Fallback: правый верхний угол
            return (img_width - qr_size - margin, margin)


class FolkMedicineQRPipeline:
    """Пайплайн для генерации баннеров народной медицины с QR-кодами."""
    
    def __init__(
        self,
        logo_archive: str = "/mldata/logo_for_qr.rar",
        logo_dir: str = "/mldata/logo_for_qr_extracted",
        device: str = "cuda",
        dtype: torch.dtype = torch.float16,
        quantize: Optional[str] = None,
        validate: bool = True,
    ):
        self.banner_pipeline = FolkMedicineBannerPipeline(
            device=device,
            dtype=dtype,
            quantize=quantize,
            validate=validate,
        )
        
        # Менеджер логотипов
        self.logo_manager = LogoManager(logo_archive, logo_dir)
        
        # QR генераторы
        self.qr_generator = QRGenerator()
        self.artistic_qr = ArtisticQRGenerator()
    
    def generate_qr_variety(
        self,
        url: str,
        qr_type: str = "random",
        logo_path: Optional[Path] = None,
    ) -> Image.Image:
        """
        Генерация QR-кода с разнообразием стилей.
        
        Args:
            url: URL для QR-кода
            qr_type: Тип QR ("simple", "artistic_white", "artistic_transparent", "custom_color", "random")
            logo_path: Путь к логотипу (если None - случайный из архива)
        
        Returns:
            PIL Image с QR-кодом
        """
        if qr_type == "random":
            qr_type = random.choice([
                "simple",
                "artistic_white",
                "artistic_transparent",
                "custom_color",
            ])
        
        # Выбираем логотип
        if logo_path is None:
            logo_path = self.logo_manager.get_random_logo()
        
        if qr_type == "simple":
            # Простой QR на белом фоне
            style = PRESET_STYLES.get("rounded", QRStyle())
            return self.qr_generator.generate(
                data=url,
                style=style,
                logo_path=logo_path,
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
            return self.qr_generator.generate(
                data=url,
                style=style,
                logo_path=logo_path,
            )
        
        elif qr_type == "artistic_transparent":
            # Артистичный QR на прозрачном фоне
            qr_img = self.artistic_qr.generate_transparent(
                data=url,
                size=300,
                fg_color=(0, 0, 0, 220),
                module_style=ModuleStyle.ROUNDED,
            )
            
            # Добавляем логотип если есть
            if logo_path and logo_path.exists():
                try:
                    logo = Image.open(logo_path).convert("RGBA")
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
                except Exception as e:
                    print(f"  ⚠️  Ошибка добавления логотипа: {e}")
            
            return qr_img
        
        elif qr_type == "custom_color":
            # Кастомный цветной QR
            colors = [
                ((34, 139, 34), (255, 255, 255)),  # Зелёный на белом
                ((70, 130, 180), (255, 255, 255)),  # Синий на белом
                ((139, 69, 19), (255, 255, 255)),  # Коричневый на белом
                ((0, 0, 0), (240, 240, 240)),  # Чёрный на сером
                ((128, 0, 128), (255, 255, 255)),  # Фиолетовый на белом
                ((255, 140, 0), (255, 255, 255)),  # Оранжевый на белом
            ]
            fg_color, bg_color = random.choice(colors)
            
            style = QRStyle(
                module_style=random.choice([ModuleStyle.ROUNDED, ModuleStyle.CIRCLE]),
                fg_color=fg_color,
                bg_color=(*bg_color, 255),
                error_correction=ErrorCorrection.H,
            )
            return self.qr_generator.generate(
                data=url,
                style=style,
                logo_path=logo_path,
            )
        
        else:
            # Fallback на простой
            return self.generate_qr_variety(url, "simple", logo_path)
    
    def overlay_qr_on_banner(
        self,
        banner: Image.Image,
        qr: Image.Image,
        position: Optional[Tuple[int, int]] = None,
        qr_size: Optional[int] = None,
        layout_name: str = "classic_left",
    ) -> Image.Image:
        """
        Наложение QR-кода на баннер с учётом лейаута.
        
        Args:
            banner: Изображение баннера
            qr: QR-код
            position: Позиция (x, y), если None - автоматический поиск
            qr_size: Размер QR (если None - авто)
            layout_name: Имя лейаута для определения безопасной позиции
        """
        banner = banner.convert("RGBA")
        qr = qr.convert("RGBA")
        
        img_width, img_height = banner.size
        
        # Определяем размер QR
        if qr_size is None:
            qr_size = min(int(img_width * 0.15), int(img_height * 0.15))
            qr_size = max(150, min(qr_size, 300))  # Ограничения: 150-300px
        
        qr = qr.resize((qr_size, qr_size), Image.LANCZOS)
        
        # Находим безопасную позицию с учётом лейаута
        if position is None:
            position = QRPlacementStrategy.find_safe_position(
                img_width, img_height, qr_size, layout_name=layout_name
            )
        
        if position is None:
            # Fallback в зависимости от лейаута
            if layout_name == "classic_right":
                position = (20, 20)  # Левый верхний угол
            else:
                position = (img_width - qr_size - 20, 20)  # Правый верхний угол
        
        x, y = position
        
        # Накладываем QR
        result = banner.copy()
        result.paste(qr, (x, y), qr)
        
        return result
    
    def generate_banner_with_qr(
        self,
        add_qr: bool = True,
        qr_type: str = "random",
        url: str = None,
        **banner_kwargs,
    ) -> Tuple[Image.Image, Dict[str, Any]]:
        """
        Генерация баннера с опциональным QR-кодом.
        
        Returns:
            (image, metadata)
        """
        # Определяем layout для правильного размещения QR
        layout = banner_kwargs.get("layout")
        scenario = banner_kwargs.get("scenario")
        
        if layout:
            layout_name = layout.get("name", "classic_left")
        elif scenario:
            # Определяем layout по scenario
            layout = get_layout_for_scenario(scenario)
            layout_name = layout.get("name", "classic_left")
        else:
            layout_name = "classic_left"  # По умолчанию
        
        # Генерируем баннер
        banner = self.banner_pipeline.generate_banner(**banner_kwargs)
        
        metadata = {
            "has_qr": False,
            "qr_type": None,
            "logo_path": None,
            "url": None,
            "layout_name": layout_name,
        }
        
        # Добавляем QR если нужно
        if add_qr:
            if url is None:
                # Генерируем случайный URL из доменов народной медицины
                domains = [
                    "newnorma.ru", "namasteguru.ru", "vladimirosipov-online.ru",
                    "mariya-gadanie.tilda.ws", "travogor.ru", "happy4woman.ru",
                    "sujokonline.ru", "velarinka.ru", "buraev.ru", "osteopatik.ru",
                    "массаж-пента.рф", "clinic-amrita.ru", "tibetspb.ru",
                    "life-plus.online", "brahmaspb.com", "insam.spb.ru",
                    "ayurvedakamala.ru", "medi-cn.ru", "ayurdara.ru", "medfolk.ru",
                ]
                domain = random.choice(domains)
                url = f"https://{domain}"
            
            logo_path = self.logo_manager.get_random_logo()
            qr = self.generate_qr_variety(url, qr_type, logo_path)
            # Передаём layout_name для правильного размещения QR
            banner = self.overlay_qr_on_banner(banner, qr, layout_name=layout_name)
            
            metadata.update({
                "has_qr": True,
                "qr_type": qr_type,
                "logo_path": str(logo_path) if logo_path else None,
                "url": url,
            })
        
        return banner, metadata
    
    def generate_mass_with_qr(
        self,
        output_dir: Path,
        total_count: int = 2000,
        qr_percentage: float = 50.0,
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
        print(f"  МАССОВАЯ ГЕНЕРАЦИЯ БАННЕРОВ НАРОДНОЙ МЕДИЦИНЫ С QR-КОДАМИ")
        print(f"  Дата: {date.today().isoformat()}")
        print(f"  Всего: {total_count} баннеров")
        print(f"  QR на {qr_percentage}% баннеров")
        print(f"  Логотипов доступно: {len(self.logo_manager.logos)}")
        print(f"  Папка: {output_dir}")
        print(f"{'='*70}\n")
        
        for i in range(total_count):
            banner_start = time.time()
            
            # Решаем добавлять ли QR
            add_qr = random.random() * 100 < qr_percentage
            
            # Случайные параметры
            scenario = random.choice(FOLK_MEDICINE_SCENARIOS)
            style = random.choice(FOLK_MEDICINE_STYLES)
            disc_bg = get_random_disclaimer_bg_style()
            seed = random.randint(1, 999999999)
            
            # Тип QR
            qr_type = random.choice(qr_types) if add_qr else None
            
            progress = (i + 1) / total_count * 100
            elapsed = time.time() - start_time
            avg_time = elapsed / (i + 1) if i > 0 else 30
            eta = avg_time * (total_count - i - 1)
            
            print(f"\n[{i+1}/{total_count}] ({progress:.1f}%) ETA: {eta/60:.1f} мин")
            print(f"  QR: {'Да' if add_qr else 'Нет'} ({qr_type if add_qr else '-'})")
            print(f"  Сценарий: {scenario['name']}")
            
            try:
                gen_start = time.time()
                
                banner, metadata = self.generate_banner_with_qr(
                    add_qr=add_qr,
                    qr_type=qr_type,
                    scenario=scenario,
                    style=style,
                    disclaimer_bg_style=disc_bg,
                    seed=seed,
                    **kwargs,
                )
                
                gen_time = time.time() - gen_start
                
                # Сохранение
                filename = f"folk_medicine_qr_{i:05d}_{scenario['name']}_{seed}.png"
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
                    "has_qr": metadata["has_qr"],
                    "qr_type": metadata.get("qr_type"),
                    "logo_path": metadata.get("logo_path"),
                    "url": metadata.get("url"),
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
                        "logos_available": len(self.logo_manager.logos),
                    },
                    "results": results,
                    "errors": errors,
                }, f, indent=2, ensure_ascii=False)
            print(f"📊 Статистика: {stats_path}")
        
        return results


def main():
    parser = argparse.ArgumentParser(
        description="Генератор баннеров народной медицины с QR-кодами"
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
    
    # Логотипы
    parser.add_argument("--logo-archive", type=str,
                        default="/mldata/logo_for_qr.rar",
                        help="Путь к архиву с логотипами")
    parser.add_argument("--logo-dir", type=str,
                        default="/mldata/logo_for_qr_extracted",
                        help="Директория для распаковки логотипов")
    
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
    parser.add_argument("--output", type=str, default="output/folk_medicine_with_qr")
    
    args = parser.parse_args()
    
    # Типы данных
    dtype_map = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}
    dtype = dtype_map[args.dtype]
    
    # Создаём пайплайн
    pipeline = FolkMedicineQRPipeline(
        logo_archive=args.logo_archive,
        logo_dir=args.logo_dir,
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
    filepath = output_dir / f"test_folk_medicine_qr_{args.seed or 'random'}.png"
    banner.save(filepath, quality=95)
    print(f"✅ Сохранено: {filepath}")
    print(f"   QR: {metadata.get('url', 'Нет')}")


if __name__ == "__main__":
    main()
