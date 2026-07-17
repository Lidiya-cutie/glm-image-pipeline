#!/usr/bin/env python3
"""
Text Overlay Module for Banner Generation

Наложение текста на изображения в стиле рекламных баннеров.

Примеры:
    # Базовое использование
    python scripts/text_overlay.py --image output/banners/courthouse_0000.png --output output/final/

    # С кастомным текстом
    python scripts/text_overlay.py --image bg.png --headline "Адвокат" --description "Опыт более 15 лет"

    # Batch обработка всех изображений в папке
    python scripts/text_overlay.py --input-dir output/banners/ --output output/final/ --all-variations

    # Конкретный лейаут и стиль
    python scripts/text_overlay.py --image bg.png --layout classic_left --style gold
"""

import argparse
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from typing import Dict, List, Optional, Tuple, Any
import random
import json
import textwrap

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Configurations
# =============================================================================

LAYOUTS = [
    {
        "name": "classic_left",
        "headline": {"x": 60, "y": 100, "max_w": 480, "align": "left"},
        "description": {"x": 60, "y": 420, "max_w": 450, "align": "left"},
        "phone": {"x": 60, "y": 700, "align": "left"},
        "disclaimer": {"x": 60, "y": 950, "max_w": 500, "align": "left"},
        "card_zone": {"x": 40, "y": 80, "w": 520, "h": 700}
    },
    {
        "name": "classic_right",
        "headline": {"x": 520, "y": 100, "max_w": 420, "align": "left"},
        "description": {"x": 520, "y": 420, "max_w": 400, "align": "left"},
        "phone": {"x": 520, "y": 700, "align": "left"},
        "disclaimer": {"x": 520, "y": 950, "max_w": 420, "align": "left"},
        "card_zone": {"x": 500, "y": 80, "w": 460, "h": 700}
    },
    {
        "name": "top_bottom",
        "headline": {"x": 512, "y": 80, "max_w": 900, "align": "center"},
        "description": {"x": 512, "y": 750, "max_w": 800, "align": "center"},
        "phone": {"x": 512, "y": 870, "align": "center"},
        "disclaimer": {"x": 512, "y": 960, "max_w": 700, "align": "center"},
        "card_zone": None
    },
    {
        "name": "center_stack",
        "headline": {"x": 512, "y": 180, "max_w": 800, "align": "center"},
        "description": {"x": 512, "y": 500, "max_w": 700, "align": "center"},
        "phone": {"x": 512, "y": 700, "align": "center"},
        "disclaimer": {"x": 512, "y": 920, "max_w": 600, "align": "center"},
        "card_zone": {"x": 106, "y": 150, "w": 812, "h": 600}
    },
    {
        "name": "diagonal",
        "headline": {"x": 80, "y": 80, "max_w": 500, "align": "left"},
        "description": {"x": 500, "y": 520, "max_w": 480, "align": "left"},
        "phone": {"x": 500, "y": 750, "align": "left"},
        "disclaimer": {"x": 80, "y": 960, "max_w": 600, "align": "left"},
        "card_zone": None
    },
]

TEXT_STYLES = [
    {
        "name": "gold",
        "headline_color": (255, 215, 100),
        "text_color": (255, 255, 255),
        "accent_color": (212, 175, 55),
        "shadow_color": (0, 0, 0),
        "shadow_opacity": 180
    },
    {
        "name": "white",
        "headline_color": (255, 255, 255),
        "text_color": (240, 240, 240),
        "accent_color": (255, 255, 255),
        "shadow_color": (0, 0, 0),
        "shadow_opacity": 200
    },
    {
        "name": "cream",
        "headline_color": (255, 248, 220),
        "text_color": (250, 250, 245),
        "accent_color": (230, 220, 180),
        "shadow_color": (50, 40, 30),
        "shadow_opacity": 180
    },
    {
        "name": "silver",
        "headline_color": (220, 220, 235),
        "text_color": (240, 240, 250),
        "accent_color": (180, 180, 200),
        "shadow_color": (20, 20, 40),
        "shadow_opacity": 180
    },
    {
        "name": "bronze",
        "headline_color": (205, 150, 80),
        "text_color": (255, 255, 255),
        "accent_color": (180, 130, 70),
        "shadow_color": (40, 25, 10),
        "shadow_opacity": 180
    },
]

# Default Russian texts
DEFAULT_HEADLINES = [
    "Профессиональный адвокат",
    "Защита ваших интересов",
    "Юридическая помощь",
    "Опытный адвокат",
    "Правовая поддержка",
    "Квалифицированная защита",
    "Адвокат по любым делам",
    "Юридические услуги",
    "Надежная защита прав",
    "Консультация адвоката",
    "Ваш личный адвокат",
    "Правовая защита"
]

DEFAULT_DESCRIPTIONS = [
    "Бесплатная первая консультация",
    "Опыт работы более 15 лет",
    "Работаем круглосуточно",
    "Полная конфиденциальность",
    "Индивидуальный подход к каждому",
    "Защита в суде любой инстанции",
    "Быстрое решение вопросов",
    "Представительство в суде",
    "Семейные и наследственные споры",
    "Уголовные и гражданские дела",
    "Арбитражные споры",
    "Сопровождение сделок"
]

DEFAULT_DISCLAIMERS = [
    "Требуется консультация специалиста",
    "Не является публичной офертой",
    "Необходима предварительная консультация",
    "Консультация обязательна"
]


# =============================================================================
# Font Management
# =============================================================================

class FontManager:
    """Manages font loading with fallbacks."""
    
    # Common font paths for different systems
    FONT_PATHS = [
        # Linux
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-Regular.ttf",
        # Cyrillic-specific
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
        "/Library/Fonts/Arial.ttf",
        # Windows
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]
    
    _cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}
    _found_font: Optional[str] = None
    
    @classmethod
    def find_font(cls) -> Optional[str]:
        """Find first available font."""
        if cls._found_font:
            return cls._found_font
            
        for path in cls.FONT_PATHS:
            if Path(path).exists():
                cls._found_font = path
                return path
        return None
    
    @classmethod
    def get_font(cls, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        """Get font with specified size."""
        cache_key = (str(bold), size)
        if cache_key in cls._cache:
            return cls._cache[cache_key]
            
        font_path = cls.find_font()
        
        if font_path:
            try:
                font = ImageFont.truetype(font_path, size)
                cls._cache[cache_key] = font
                return font
            except Exception as e:
                print(f"Warning: Could not load font {font_path}: {e}")
        
        # Fallback to default
        font = ImageFont.load_default()
        cls._cache[cache_key] = font
        return font


# =============================================================================
# Text Renderer
# =============================================================================

class TextRenderer:
    """Renders text with effects on images."""
    
    def __init__(
        self,
        style: Dict[str, Any],
        headline_size: int = 72,
        text_size: int = 36,
        phone_size: int = 48,
        disclaimer_size: int = 18,
    ):
        self.style = style
        self.headline_size = headline_size
        self.text_size = text_size
        self.phone_size = phone_size
        self.disclaimer_size = disclaimer_size
        
        # Load fonts
        self.headline_font = FontManager.get_font(headline_size, bold=True)
        self.text_font = FontManager.get_font(text_size)
        self.phone_font = FontManager.get_font(phone_size, bold=True)
        self.disclaimer_font = FontManager.get_font(disclaimer_size)
        
    def draw_text_with_shadow(
        self,
        draw: ImageDraw.ImageDraw,
        position: Tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont,
        fill: Tuple[int, int, int],
        shadow_offset: int = 3,
        shadow_blur: int = 5,
        align: str = "left",
        max_width: Optional[int] = None,
        anchor: Optional[str] = None,
    ) -> int:
        """
        Draw text with shadow effect.
        Returns the height of the rendered text.
        """
        x, y = position
        shadow_color = (*self.style.get("shadow_color", (0, 0, 0)), 
                       self.style.get("shadow_opacity", 180))
        
        # Wrap text if max_width specified
        if max_width:
            lines = self._wrap_text(text, font, max_width)
        else:
            lines = [text]
        
        # Calculate anchor based on alignment
        if anchor is None:
            anchor = "la" if align == "left" else "ma" if align == "center" else "ra"
        
        total_height = 0
        line_spacing = 1.2
        
        for i, line in enumerate(lines):
            line_y = y + int(i * font.size * line_spacing)
            
            # Draw shadow
            draw.text(
                (x + shadow_offset, line_y + shadow_offset),
                line,
                font=font,
                fill=shadow_color,
                anchor=anchor,
            )
            
            # Draw main text
            draw.text(
                (x, line_y),
                line,
                font=font,
                fill=fill,
                anchor=anchor,
            )
            
            total_height = int((i + 1) * font.size * line_spacing)
        
        return total_height
    
    def _wrap_text(
        self,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_width: int
    ) -> List[str]:
        """Wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = " ".join(current_line + [word])
            bbox = font.getbbox(test_line)
            width = bbox[2] - bbox[0]
            
            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(" ".join(current_line))
        
        return lines if lines else [text]
    
    def draw_decorative_line(
        self,
        draw: ImageDraw.ImageDraw,
        start: Tuple[int, int],
        width: int,
        color: Tuple[int, int, int],
        thickness: int = 3,
    ):
        """Draw a decorative line."""
        x, y = start
        draw.rectangle(
            [x, y, x + width, y + thickness],
            fill=color
        )
    
    def draw_card_background(
        self,
        image: Image.Image,
        zone: Dict[str, int],
        opacity: int = 120,
    ) -> Image.Image:
        """Draw semi-transparent card background."""
        overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Draw rounded rectangle (approximated with regular rect)
        x, y, w, h = zone['x'], zone['y'], zone['w'], zone['h']
        draw.rectangle(
            [x, y, x + w, y + h],
            fill=(0, 0, 0, opacity)
        )
        
        # Composite
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        return Image.alpha_composite(image, overlay)


# =============================================================================
# Banner Overlay
# =============================================================================

class BannerOverlay:
    """Overlays text on banner images."""
    
    # Reference size for layout coordinates
    REF_WIDTH = 1024
    REF_HEIGHT = 1024
    
    def __init__(
        self,
        layout: Dict[str, Any] = None,
        style: Dict[str, Any] = None,
    ):
        self.layout = layout or LAYOUTS[0]
        self.style = style or TEXT_STYLES[0]
    
    def _scale_position(self, x: int, y: int, img_width: int, img_height: int) -> Tuple[int, int]:
        """Scale position from reference size to actual image size."""
        scale_x = img_width / self.REF_WIDTH
        scale_y = img_height / self.REF_HEIGHT
        return int(x * scale_x), int(y * scale_y)
    
    def _scale_value(self, value: int, img_width: int) -> int:
        """Scale a single value (like max_width) based on image width."""
        scale = img_width / self.REF_WIDTH
        return int(value * scale)
    
    def _get_font_sizes(self, img_width: int, img_height: int) -> Dict[str, int]:
        """Calculate font sizes based on image dimensions."""
        # Base sizes for 1024x1024
        base_headline = 72
        base_text = 36
        base_phone = 48
        base_disclaimer = 18
        
        # Scale based on smaller dimension
        scale = min(img_width, img_height) / self.REF_WIDTH
        
        return {
            "headline": max(24, int(base_headline * scale)),
            "text": max(14, int(base_text * scale)),
            "phone": max(18, int(base_phone * scale)),
            "disclaimer": max(10, int(base_disclaimer * scale)),
        }
    
    def _clamp_position(self, x: int, y: int, img_width: int, img_height: int, 
                        margin: int = 20, align: str = "left", 
                        text_width: int = 0) -> Tuple[int, int]:
        """Ensure position is within image bounds with margin."""
        if align == "left":
            # For left-aligned text, ensure x + text_width fits
            max_x = img_width - margin - text_width if text_width else img_width - margin
            x = max(margin, min(x, max_x))
        elif align == "center":
            # For centered text, keep x as center point within bounds
            half_width = text_width // 2 if text_width else 0
            x = max(margin + half_width, min(x, img_width - margin - half_width))
        else:  # right
            x = max(margin + text_width if text_width else margin, min(x, img_width - margin))
        
        y = max(margin, min(y, img_height - margin))
        return x, y
    
    def _estimate_text_width(self, text: str, font: ImageFont.FreeTypeFont, max_width: int = None) -> int:
        """Estimate the width of text after wrapping."""
        if max_width:
            # If we have max_width, text will wrap
            return min(font.getbbox(text)[2], max_width)
        return font.getbbox(text)[2] if text else 0
    
    def apply(
        self,
        image: Image.Image,
        headline: str,
        description: str,
        phone: str,
        disclaimer: str,
        add_card_bg: bool = True,
    ) -> Image.Image:
        """
        Apply text overlay to image.
        
        Args:
            image: PIL Image
            headline: Main headline text
            description: Description text
            phone: Phone number
            disclaimer: Disclaimer text
            add_card_bg: Whether to add semi-transparent background
            
        Returns:
            PIL Image with text overlay
        """
        # Convert to RGBA for transparency support
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        img_width, img_height = image.size
        
        # Get scaled font sizes
        font_sizes = self._get_font_sizes(img_width, img_height)
        
        # Create renderer with scaled fonts
        renderer = TextRenderer(
            self.style,
            headline_size=font_sizes["headline"],
            text_size=font_sizes["text"],
            phone_size=font_sizes["phone"],
            disclaimer_size=font_sizes["disclaimer"],
        )
        
        # Add card background if layout has card_zone
        if add_card_bg and self.layout.get('card_zone'):
            zone = self.layout['card_zone']
            scaled_zone = {
                'x': self._scale_value(zone['x'], img_width),
                'y': self._scale_value(zone['y'], img_height),
                'w': self._scale_value(zone['w'], img_width),
                'h': self._scale_value(zone['h'], img_height),
            }
            # Clamp zone to image bounds
            scaled_zone['w'] = min(scaled_zone['w'], img_width - scaled_zone['x'] - 20)
            scaled_zone['h'] = min(scaled_zone['h'], img_height - scaled_zone['y'] - 20)
            
            image = renderer.draw_card_background(image, scaled_zone, opacity=100)
        
        # Create draw context
        draw = ImageDraw.Draw(image)
        
        # ЖЁСТКИЕ границы - 8% от каждого края
        margin = int(min(img_width, img_height) * 0.08)
        
        # Безопасные зоны
        safe_left = margin
        safe_right = img_width - margin
        safe_top = margin
        safe_bottom = img_height - margin
        safe_width = safe_right - safe_left  # доступная ширина для текста
        
        # ===== HEADLINE =====
        hl = self.layout['headline']
        
        # Максимальная ширина текста - не более 45% изображения
        max_w = min(int(img_width * 0.45), safe_width - margin)
        
        # Позиция в зависимости от выравнивания
        if hl['align'] == 'center':
            hl_x = img_width // 2
            anchor = "ma"
        else:  # left
            hl_x = safe_left
            anchor = "la"
        
        hl_y = safe_top
        
        renderer.draw_text_with_shadow(
            draw,
            (hl_x, hl_y),
            headline,
            renderer.headline_font,
            self.style['headline_color'],
            shadow_offset=max(2, int(3 * img_width / self.REF_WIDTH)),
            align=hl['align'],
            max_width=max_w,
            anchor=anchor,
        )
        
        # Декоративная линия
        line_width = min(int(img_width * 0.15), max_w)
        line_y = hl_y + font_sizes["headline"] + int(img_height * 0.015)
        if hl['align'] == 'center':
            line_x = (img_width - line_width) // 2
        else:
            line_x = safe_left
        
        # Проверка что линия в границах
        line_x = max(safe_left, min(line_x, safe_right - line_width))
        
        renderer.draw_decorative_line(
            draw,
            (line_x, line_y),
            line_width,
            self.style['accent_color'],
            thickness=max(2, int(3 * img_width / self.REF_WIDTH))
        )
        
        # ===== DESCRIPTION =====
        desc = self.layout['description']
        desc_max_w = min(int(img_width * 0.42), safe_width - margin)
        
        # Позиция description - ниже headline
        desc_y_base = self._scale_value(desc['y'], img_height)
        desc_y = max(line_y + int(img_height * 0.05), min(desc_y_base, int(img_height * 0.45)))
        
        if desc['align'] == 'center':
            desc_x = img_width // 2
            anchor = "ma"
        else:
            desc_x = safe_left
            anchor = "la"
        
        renderer.draw_text_with_shadow(
            draw,
            (desc_x, desc_y),
            description,
            renderer.text_font,
            self.style['text_color'],
            shadow_offset=max(1, int(2 * img_width / self.REF_WIDTH)),
            align=desc['align'],
            max_width=desc_max_w,
            anchor=anchor,
        )
        
        # ===== PHONE =====
        ph = self.layout['phone']
        phone_width = self._estimate_text_width(phone, renderer.phone_font)
        
        # Позиция phone - в нижней трети
        ph_y = int(img_height * 0.68)
        ph_y = max(desc_y + int(img_height * 0.1), min(ph_y, safe_bottom - font_sizes["phone"] - margin))
        
        if ph['align'] == 'center':
            ph_x = img_width // 2
            anchor = "ma"
        else:
            # Убедимся что помещается
            ph_x = safe_left
            if ph_x + phone_width > safe_right:
                ph_x = safe_right - phone_width
            ph_x = max(safe_left, ph_x)
            anchor = "la"
        
        renderer.draw_text_with_shadow(
            draw,
            (ph_x, ph_y),
            phone,
            renderer.phone_font,
            self.style['headline_color'],
            shadow_offset=max(2, int(3 * img_width / self.REF_WIDTH)),
            align=ph['align'],
            anchor=anchor,
        )
        
        # ===== DISCLAIMER =====
        disc = self.layout['disclaimer']
        disc_max_w = min(int(img_width * 0.6), safe_width)
        
        # Позиция disclaimer - внизу изображения
        disc_y = safe_bottom - font_sizes["disclaimer"] - int(margin * 0.3)
        disc_y = max(ph_y + font_sizes["phone"] + int(margin * 0.5), disc_y)
        
        if disc['align'] == 'center':
            disc_x = img_width // 2
            anchor = "ma"
        else:
            disc_x = safe_left
            anchor = "la"
        
        renderer.draw_text_with_shadow(
            draw,
            (disc_x, disc_y),
            disclaimer,
            renderer.disclaimer_font,
            (*self.style['text_color'][:3],),
            shadow_offset=1,
            align=disc['align'],
            max_width=disc_max_w,
            anchor=anchor,
        )
        
        return image


# =============================================================================
# Helper Functions
# =============================================================================

def generate_phone() -> str:
    """Generate random Russian phone number."""
    return f"+7 ({random.randint(900, 999)}) {random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(10, 99)}"


def get_layout_by_name(name: str) -> Dict:
    """Get layout by name."""
    for layout in LAYOUTS:
        if layout['name'] == name:
            return layout
    return LAYOUTS[0]


def get_style_by_name(name: str) -> Dict:
    """Get style by name."""
    for style in TEXT_STYLES:
        if style['name'] == name:
            return style
    return TEXT_STYLES[0]


def process_single_image(
    image_path: Path,
    output_path: Path,
    headline: str = None,
    description: str = None,
    phone: str = None,
    disclaimer: str = None,
    layout_name: str = None,
    style_name: str = None,
    add_card_bg: bool = True,
) -> Path:
    """Process a single image with text overlay."""
    # Load image
    image = Image.open(image_path)
    
    # Get layout and style
    layout = get_layout_by_name(layout_name) if layout_name else random.choice(LAYOUTS)
    style = get_style_by_name(style_name) if style_name else random.choice(TEXT_STYLES)
    
    # Get text content
    headline = headline or random.choice(DEFAULT_HEADLINES)
    description = description or random.choice(DEFAULT_DESCRIPTIONS)
    phone = phone or generate_phone()
    disclaimer = disclaimer or random.choice(DEFAULT_DISCLAIMERS)
    
    # Apply overlay
    overlay = BannerOverlay(layout=layout, style=style)
    result = overlay.apply(
        image,
        headline=headline,
        description=description,
        phone=phone,
        disclaimer=disclaimer,
        add_card_bg=add_card_bg,
    )
    
    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert to RGB for JPEG or keep RGBA for PNG
    if output_path.suffix.lower() in ['.jpg', '.jpeg']:
        result = result.convert('RGB')
    
    result.save(output_path, quality=95)
    return output_path


def process_batch(
    input_dir: Path,
    output_dir: Path,
    all_variations: bool = False,
    **kwargs,
) -> List[Path]:
    """Process all images in a directory."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    input_dir = Path(input_dir)
    image_files = list(input_dir.glob("*.png")) + list(input_dir.glob("*.jpg"))
    
    results = []
    
    for img_path in image_files:
        if all_variations:
            # Generate all layout+style combinations
            for layout in LAYOUTS:
                for style in TEXT_STYLES:
                    output_name = f"{img_path.stem}_{layout['name']}_{style['name']}.png"
                    output_path = output_dir / output_name
                    
                    result = process_single_image(
                        img_path,
                        output_path,
                        layout_name=layout['name'],
                        style_name=style['name'],
                        **kwargs,
                    )
                    results.append(result)
                    print(f"Created: {result}")
        else:
            # Single random variation
            output_path = output_dir / f"{img_path.stem}_overlay.png"
            result = process_single_image(img_path, output_path, **kwargs)
            results.append(result)
            print(f"Created: {result}")
    
    return results


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Add text overlay to banner images")
    
    # Input
    parser.add_argument("--image", type=str, help="Single image path")
    parser.add_argument("--input-dir", type=str, help="Directory with images for batch processing")
    
    # Output
    parser.add_argument("--output", type=str, default="output/overlayed",
                        help="Output path (file or directory)")
    
    # Text content
    parser.add_argument("--headline", type=str, help="Headline text")
    parser.add_argument("--description", type=str, help="Description text")
    parser.add_argument("--phone", type=str, help="Phone number")
    parser.add_argument("--disclaimer", type=str, help="Disclaimer text")
    
    # Style options
    parser.add_argument("--layout", type=str, 
                        choices=[l['name'] for l in LAYOUTS],
                        help="Layout name")
    parser.add_argument("--style", type=str,
                        choices=[s['name'] for s in TEXT_STYLES],
                        help="Text style name")
    parser.add_argument("--no-card-bg", action="store_true",
                        help="Disable semi-transparent card background")
    
    # Batch options
    parser.add_argument("--all-variations", action="store_true",
                        help="Generate all layout+style combinations")
    parser.add_argument("--random-text", action="store_true",
                        help="Use random text for each image")
    
    # Utilities
    parser.add_argument("--list-layouts", action="store_true",
                        help="List available layouts")
    parser.add_argument("--list-styles", action="store_true",
                        help="List available styles")
    
    args = parser.parse_args()
    
    # Utility actions
    if args.list_layouts:
        print("\n=== Available Layouts ===")
        for l in LAYOUTS:
            print(f"  - {l['name']}")
        return
    
    if args.list_styles:
        print("\n=== Available Styles ===")
        for s in TEXT_STYLES:
            print(f"  - {s['name']}: headline={s['headline_color']}, text={s['text_color']}")
        return
    
    # Validate input
    if not args.image and not args.input_dir:
        parser.error("Either --image or --input-dir is required")
    
    # Common kwargs
    kwargs = {
        "headline": args.headline if not args.random_text else None,
        "description": args.description if not args.random_text else None,
        "phone": args.phone if not args.random_text else None,
        "disclaimer": args.disclaimer if not args.random_text else None,
        "layout_name": args.layout,
        "style_name": args.style,
        "add_card_bg": not args.no_card_bg,
    }
    
    if args.image:
        # Single image
        image_path = Path(args.image)
        if not image_path.exists():
            print(f"Error: Image not found: {image_path}")
            return
        
        output_path = Path(args.output)
        if output_path.is_dir() or not output_path.suffix:
            output_path = output_path / f"{image_path.stem}_overlay.png"
        
        result = process_single_image(image_path, output_path, **kwargs)
        print(f"Created: {result}")
        
    elif args.input_dir:
        # Batch processing
        input_dir = Path(args.input_dir)
        if not input_dir.exists():
            print(f"Error: Directory not found: {input_dir}")
            return
        
        output_dir = Path(args.output)
        results = process_batch(
            input_dir,
            output_dir,
            all_variations=args.all_variations,
            **kwargs,
        )
        print(f"\nTotal: {len(results)} images created in {output_dir}")


if __name__ == "__main__":
    main()
