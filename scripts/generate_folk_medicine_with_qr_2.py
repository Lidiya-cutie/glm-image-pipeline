#!/usr/bin/env python3
"""
Массовая генерация баннеров народной медицины с QR-кодами.
"""

import argparse
import sys
from pathlib import Path
import json
import random
from typing import Dict, List, Optional, Any, Tuple
import time
import torch
from PIL import Image, ImageDraw
import subprocess

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_folk_medicine_banners import FolkMedicineBannerPipeline
from scripts.folk_medicine_overlay import (
    FOLK_MEDICINE_SCENARIOS,
    FOLK_MEDICINE_HEADLINES,
    FOLK_MEDICINE_DESCRIPTIONS,
    FOLK_MEDICINE_STYLES,
    generate_phone,
    get_layout_for_scenario,
)

sys.path.insert(0, str(Path("/mldata/custom-qr-generator")))

try:
    from qr_generator.core import QRGenerator
    from qr_generator.styles import QRStyle, PRESET_STYLES, ModuleStyle, ColorMode, ErrorCorrection
    try:
        from qr_generator.artistic import ArtisticQRGenerator, BlendMode
        HAS_ARTISTIC = True
    except ImportError:
        HAS_ARTISTIC = False
except ImportError as e:
    print(f"Ошибка импорта QR генератора: {e}")
    print("Проверьте пути и установите зависимости: pip install qrcode[pil] Pillow")
    sys.exit(1)

class LogoManager:
    def __init__(self, archive_path="/mldata/logo_for_qr.rar", extract_dir="/mldata/logo_for_qr_extracted"):
        self.archive_path = Path(archive_path)
        self.extract_dir = Path(extract_dir)
        self.logos = []
        self._ensure_extracted()
        self._load_logos()

    def _ensure_extracted(self):
        if self.extract_dir.exists() and any(self.extract_dir.iterdir()): return
        self.extract_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["unrar", "x", "-o+", str(self.archive_path), str(self.extract_dir)], capture_output=True)
        except: pass

    def _load_logos(self):
        if not self.extract_dir.exists(): return
        self.logos = [f for f in self.extract_dir.rglob('*') if f.suffix.lower() in {'.png', '.jpg', '.jpeg'} and f.is_file()]

    def get_random_logo(self):
        return random.choice(self.logos) if self.logos else None

class QRPlacementStrategy:
    @staticmethod
    def find_safe_position(img_width, img_height, qr_size, layout_name="classic_left"):
        # Если текст слева, ставим QR справа и наоборот
        if "left" in layout_name:
            return (img_width - qr_size - 30, 30)
        elif "right" in layout_name:
            return (30, 30)
        else:
            return (img_width - qr_size - 30, 30)

class FolkMedicineQRPipeline:
    def __init__(self, device="cuda", dtype=torch.float16, quantize=None):
        self.banner_pipeline = FolkMedicineBannerPipeline(device=device, dtype=dtype, quantize=quantize)
        self.logo_manager = LogoManager()
        self.qr_generator = QRGenerator()
        if HAS_ARTISTIC:
            self.artistic_qr = ArtisticQRGenerator()
        else:
            self.artistic_qr = None

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
            if HAS_ARTISTIC:
                qr_type = random.choice([
                    "simple",
                    "artistic_white",
                    "artistic_transparent",
                    "custom_color",
                ])
            else:
                qr_type = random.choice([
                    "simple",
                    "artistic_white",
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
            if HAS_ARTISTIC:
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
            else:
                # Fallback на простой стиль
                style = PRESET_STYLES.get("rounded", QRStyle())
                return self.qr_generator.generate(
                    data=url,
                    style=style,
                    logo_path=logo_path,
                )
        
        elif qr_type == "artistic_transparent":
            # Артистичный QR на прозрачном фоне
            if HAS_ARTISTIC and self.artistic_qr:
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
                    except Exception:
                        pass  # Игнорируем ошибки с логотипом
                
                return qr_img
            else:
                # Fallback на простой стиль
                style = PRESET_STYLES.get("rounded", QRStyle())
                return self.qr_generator.generate(
                    data=url,
                    style=style,
                    logo_path=logo_path,
                )
        
        elif qr_type == "custom_color":
            # Кастомный цветной QR
            if HAS_ARTISTIC:
                colors = [
                    ((200, 50, 100), (50, 150, 200)),  # Розово-синий
                    ((100, 200, 50), (200, 100, 50)),  # Зелено-оранжевый
                    ((150, 100, 200), (50, 200, 150)), # Фиолетово-бирюзовый
                ]
                fg_color, bg_color = random.choice(colors)
                
                style = QRStyle(
                    module_style=random.choice([ModuleStyle.ROUNDED, ModuleStyle.CIRCLE]),
                    color_mode=ColorMode.SOLID,
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
                # Fallback на простой стиль
                style = PRESET_STYLES.get("rounded", QRStyle())
                return self.qr_generator.generate(
                    data=url,
                    style=style,
                    logo_path=logo_path,
                )
        
        else:
            # Fallback на простой стиль
            style = PRESET_STYLES.get("rounded", QRStyle())
            return self.qr_generator.generate(
                data=url,
                style=style,
                logo_path=logo_path,
            )

    def generate_banner_with_qr(self, add_qr=True, **kwargs):
        scenario = kwargs.get("scenario") or random.choice(FOLK_MEDICINE_SCENARIOS)
        layout = get_layout_for_scenario(scenario)
        layout_name = layout.get("name", "classic_left")
        
        banner = self.banner_pipeline.generate_banner(scenario=scenario, layout=layout, **kwargs)
        
        if add_qr:
            url = f"https://{random.choice(['travogor.ru', 'medfolk.ru', 'ayurveda.pro'])}"
            logo = self.logo_manager.get_random_logo()
            qr = self.qr_generator.generate(data=url, style=PRESET_STYLES.get("rounded", QRStyle()), logo_path=logo)
            
            w, h = banner.size
            qr_size = int(w * 0.15)
            qr = qr.resize((qr_size, qr_size), Image.LANCZOS).convert("RGBA")
            pos = QRPlacementStrategy.find_safe_position(w, h, qr_size, layout_name)
            
            banner = banner.convert("RGBA")
            banner.paste(qr, pos, qr)
            
        return banner

    def mass_generate(self, output_dir, count=10):
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        for i in range(count):
            try:
                img = self.generate_banner_with_qr()
                img.save(out / f"folk_qr_{i:04d}.png")
                print(f"Готово: {i+1}/{count}")
            except Exception as e:
                print(f"Ошибка {i}: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--output", type=str, default="output/folk_medicine_qr")
    args = parser.parse_args()
    
    pipeline = FolkMedicineQRPipeline()
    pipeline.mass_generate(args.output, count=args.count)

if __name__ == "__main__":
    main()