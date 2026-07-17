#!/usr/bin/env python3
"""
Скрипт создания композитных баннеров ломбардов из двух изображений с QR-кодами.
Поддерживает форматы: квадрат 1024x1024, горизонтальный 1200x700, вертикальный 800x1200.
Разнообразные варианты размещения текста и шрифтов в соответствии со ст. 28 ФЗ-38 и ФЗ-196.
"""

import argparse
import sys
import random
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageStat
from typing import List, Tuple, Dict, Any, Optional
import torch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.lombard_overlay import (
    LombardBannerOverlay,
    get_random_content,
    get_random_company,
    get_random_disclaimer,
    LOMBARD_STYLES,
    LOMBARD_HEADLINES,
    LOMBARD_DESCRIPTIONS,
    LOMBARD_DISCLAIMERS,
    DISCLAIMER_BG_STYLES,
    generate_phone,
    format_source_info,
)
from scripts.text_overlay import TextRenderer, FontManager
from scripts.folk_dual_composition import (
    DualCompositionEngine,
    find_safe_qr_position,
)

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

# URL по умолчанию для QR (ломбарды)
DEFAULT_QR_URL = "https://www.example.ru/lombard"


def get_company_qr_url(company: Optional[Dict[str, str]] = None) -> str:
    """Возвращает URL для QR-кода из данных компании."""
    if company and company.get("website"):
        url = company["website"]
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url
    return DEFAULT_QR_URL


def get_layout_by_name(name: str) -> Dict:
    from scripts.text_overlay import LAYOUTS
    for layout in LAYOUTS:
        if layout["name"] == name:
            return layout
    return LAYOUTS[0]


# Варианты размещения текста для разнообразия
TEXT_PLACEMENT_VARIANTS = [
    "left_aligned",      # Текст слева
    "right_aligned",     # Текст справа
    "center_top",        # Текст по центру сверху
    "center_middle",     # Текст по центру в середине
    "diagonal_left",     # Диагональное размещение слева
    "diagonal_right",    # Диагональное размещение справа
    "split_horizontal",  # Разделение по горизонтали
    "split_vertical",    # Разделение по вертикали
]


# Варианты размеров шрифтов для разнообразия
FONT_SIZE_VARIANTS = [
    {"headline": 1.0, "text": 1.0, "phone": 1.0},      # Стандартный
    {"headline": 1.2, "text": 0.9, "phone": 1.1},      # Крупный заголовок
    {"headline": 0.9, "text": 1.1, "phone": 0.95},    # Крупный текст
    {"headline": 1.15, "text": 1.0, "phone": 1.15},   # Крупные заголовок и телефон
    {"headline": 0.85, "text": 0.95, "phone": 0.9},   # Компактный
]


def check_text_overlaps_background(
    text_x: int,
    text_y: int,
    text_width: int,
    text_height: int,
    align: str,
    background_zones: List[Tuple[int, int, int, int]],
) -> bool:
    """
    Проверяет, пересекается ли текст с зонами фонов.
    
    Args:
        text_x: X позиция текста (зависит от align)
        text_y: Y позиция текста
        text_width: Ширина текста
        text_height: Высота текста
        align: Выравнивание текста ("left", "right", "center")
        background_zones: Список зон фонов [(x1, y1, x2, y2), ...]
    
    Returns:
        True если текст пересекается с фоном, False иначе
    """
    if not isinstance(background_zones, list) or len(background_zones) == 0:
        return False
    
    # Вычисляем реальные границы текста в зависимости от выравнивания
    if align == "left":
        text_x1 = text_x
        text_x2 = text_x + text_width
    elif align == "right":
        text_x1 = text_x - text_width
        text_x2 = text_x
    else:  # center
        text_x1 = text_x - text_width // 2
        text_x2 = text_x + text_width // 2
    
    text_y1 = text_y
    text_y2 = text_y + text_height
    
    # Проверяем пересечение с каждой зоной фона
    for bg_x1, bg_y1, bg_x2, bg_y2 in background_zones:
        # Проверяем, есть ли пересечение прямоугольников
        if not (text_x2 < bg_x1 or text_x1 > bg_x2 or text_y2 < bg_y1 or text_y1 > bg_y2):
            return True
    
    return False


def find_safe_text_position(
    base_x: int,
    base_y: int,
    text_width: int,
    text_height: int,
    align: str,
    w: int,
    h: int,
    margin: int,
    background_zones: List[Tuple[int, int, int, int]],
) -> Tuple[int, int]:
    """
    Находит безопасную позицию для текста, избегая зон фонов.
    
    Args:
        base_x: Базовая X позиция
        base_y: Базовая Y позиция
        text_width: Ширина текста
        text_height: Высота текста
        align: Выравнивание текста
        w: Ширина изображения
        h: Высота изображения
        margin: Отступ от краев
        background_zones: Список зон фонов
    
    Returns:
        Кортеж (safe_x, safe_y) - безопасная позиция для текста
    """
    if not isinstance(background_zones, list) or len(background_zones) == 0:
        return (base_x, base_y)
    
    # Пробуем несколько позиций, начиная с базовой
    candidates = []
    
    # Если текущая позиция не пересекается с фоном, используем её
    if not check_text_overlaps_background(base_x, base_y, text_width, text_height, align, background_zones):
        return (base_x, base_y)
    
    # Пробуем позиции слева и справа от фонов
    for bg_x1, bg_y1, bg_x2, bg_y2 in background_zones:
        bg_center_x = (bg_x1 + bg_x2) / 2
        
        # Позиция слева от фона
        if align == "left":
            candidate_x_left = max(margin, bg_x1 - text_width - margin)
        elif align == "right":
            candidate_x_left = max(margin + text_width, bg_x1 - margin)
        else:  # center
            candidate_x_left = max(margin + text_width // 2, bg_x1 - text_width // 2 - margin)
        
        # Позиция справа от фона
        if align == "left":
            candidate_x_right = min(w - margin - text_width, bg_x2 + margin)
        elif align == "right":
            candidate_x_right = min(w - margin, bg_x2 + text_width + margin)
        else:  # center
            candidate_x_right = min(w - margin - text_width // 2, bg_x2 + text_width // 2 + margin)
        
        candidates.append((candidate_x_left, base_y))
        candidates.append((candidate_x_right, base_y))
    
    # Пробуем позиции по краям баннера
    if align == "left":
        candidates.append((margin, base_y))
        candidates.append((w - margin - text_width, base_y))
    elif align == "right":
        candidates.append((w - margin, base_y))
        candidates.append((margin + text_width, base_y))
    else:  # center
        candidates.append((w // 2, base_y))
        candidates.append((margin + text_width // 2, base_y))
        candidates.append((w - margin - text_width // 2, base_y))
    
    # Ищем первую позицию, которая не пересекается с фоном
    for candidate_x, candidate_y in candidates:
        if not check_text_overlaps_background(candidate_x, candidate_y, text_width, text_height, align, background_zones):
            return (candidate_x, candidate_y)
    
    # Если не нашли идеальную позицию, возвращаем базовую (будет видно, что есть пересечение)
    return (base_x, base_y)


def apply_lombard_text(
    image: Image.Image,
    headline: str,
    description: str,
    phone: str,
    disclaimer: str,
    legal_entity: str,
    source_info: str,
    layout_name: str,
    style: Dict,
    background_zones: List[Tuple[int, int, int, int]],
    num_backgrounds: int = 2,
    is_horizontal: bool = True,
    placement_variant: str = None,
    font_variant: Dict = None,
) -> Image.Image:
    """
    Накладывает текст ломбарда с учётом зон фонов и разнообразными вариантами размещения.
    
    Args:
        placement_variant: Вариант размещения текста (из TEXT_PLACEMENT_VARIANTS)
        font_variant: Вариант размеров шрифтов (из FONT_SIZE_VARIANTS)
    """
    if not isinstance(background_zones, list):
        background_zones = []
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    w, h = image.size
    REF_WIDTH = 1024
    scale = min(w, h) / REF_WIDTH

    # Выбираем вариант размещения
    if placement_variant is None:
        placement_variant = random.choice(TEXT_PLACEMENT_VARIANTS)
    
    # Выбираем вариант размеров шрифтов
    if font_variant is None:
        font_variant = random.choice(FONT_SIZE_VARIANTS)
    
    # Базовые размеры с применением варианта (увеличены для лучшей читаемости)
    base_headline_size = int(72 * scale * font_variant["headline"])  # Было 58, увеличено до 72
    base_text_size = int(32 * scale * font_variant["text"])  # Было 26, увеличено до 32
    base_phone_size = int(48 * scale * font_variant["phone"])  # Было 38, увеличено до 48
    base_disclaimer_size = int(12 * scale)

    renderer = TextRenderer(
        style,
        headline_size=base_headline_size,
        text_size=base_text_size,
        phone_size=base_phone_size,
        disclaimer_size=base_disclaimer_size,
    )
    draw = ImageDraw.Draw(image)
    margin = int(w * 0.06)
    text_width = int(w * 0.45 if num_backgrounds == 2 else w * 0.6)

    # Определяем позицию текста в зависимости от варианта размещения (заголовки выше)
    if placement_variant == "left_aligned":
        base_x = margin
        align = "left"
        headline_y = int(h * 0.06)  # Было 0.12, поднято выше до 0.06
    elif placement_variant == "right_aligned":
        base_x = w - margin
        align = "right"
        headline_y = int(h * 0.06)  # Было 0.12, поднято выше до 0.06
    elif placement_variant == "center_top":
        base_x = w // 2
        align = "center"
        headline_y = int(h * 0.05)  # Было 0.10, поднято выше до 0.05
    elif placement_variant == "center_middle":
        base_x = w // 2
        align = "center"
        headline_y = int(h * 0.20)  # Было 0.25, поднято выше до 0.20
    elif placement_variant == "diagonal_left":
        base_x = margin
        align = "left"
        headline_y = int(h * 0.08)  # Было 0.15, поднято выше до 0.08
    elif placement_variant == "diagonal_right":
        base_x = w - margin
        align = "right"
        headline_y = int(h * 0.08)  # Было 0.15, поднято выше до 0.08
    elif placement_variant == "split_horizontal":
        # Заголовок слева, описание справа
        base_x = margin if random.random() < 0.5 else w - margin
        align = "left" if base_x == margin else "right"
        headline_y = int(h * 0.08)  # Было 0.15, поднято выше до 0.08
    else:  # split_vertical или по умолчанию
        base_x = w // 2
        align = "center"
        headline_y = int(h * 0.08)  # Было 0.15, поднято выше до 0.08
    
    # Корректируем позицию с учётом зон фонов
    if len(background_zones) > 0:
        if num_backgrounds == 1:
            bg_x1, bg_y1, bg_x2, bg_y2 = background_zones[0]
            bg_center_x = (bg_x1 + bg_x2) / 2
            if bg_center_x < w / 2:
                # Фон слева - текст справа
                base_x = int(w * 0.65)
                align = "right"
            else:
                # Фон справа - текст слева
                base_x = int(w * 0.35)
                align = "left"
        else:
            # Два фона - текст по центру или в свободной зоне
            if placement_variant in ["left_aligned", "diagonal_left"]:
                base_x = int(w * 0.35)
                align = "left"
            elif placement_variant in ["right_aligned", "diagonal_right"]:
                base_x = int(w * 0.65)
                align = "right"
            else:
                base_x = w // 2
                align = "center"

    # Корректируем ширину заголовка - разрешаем занимать всю ширину баннера
    if align == "left":
        # При выравнивании слева: base_x должен быть не меньше margin
        safe_base_x = max(margin, base_x)
        # Заголовок может занимать всю ширину до правого края
        # Но нужно убедиться, что текст не выйдет за правый край
        # Максимальная доступная ширина = расстояние от base_x до правого края минус margin
        headline_text_width = w - safe_base_x - margin
        # Убеждаемся, что ширина не отрицательная
        if headline_text_width < margin:
            headline_text_width = margin
        base_x = safe_base_x
    elif align == "right":
        # При выравнивании справа: base_x должен быть не больше w - margin
        safe_base_x = min(w - margin, base_x)
        # Заголовок может занимать всю ширину до левого края
        # При выравнивании "right" позиция base_x - это правая граница текста
        # Текст расширяется влево, поэтому максимальная ширина = safe_base_x - margin
        headline_text_width = safe_base_x - margin
        # Убеждаемся, что ширина не отрицательная и не слишком маленькая
        if headline_text_width < margin:
            headline_text_width = margin
        # Дополнительная проверка: убеждаемся, что текст не выйдет за левый край
        # При выравнивании "right" текст начинается справа от base_x и идет влево
        # Левая граница текста = base_x - headline_text_width, должна быть >= margin
        if safe_base_x - headline_text_width < margin:
            headline_text_width = safe_base_x - margin
        base_x = safe_base_x
    else:  # center
        # При выравнивании по центру: заголовок может занимать всю ширину баннера
        headline_text_width = w - 2 * margin
    
    # Проверяем и корректируем позицию заголовка, чтобы избежать пересечения с фонами
    # Оцениваем примерную высоту заголовка для проверки пересечений
    estimated_headline_height = base_headline_size * 2  # Примерная высота (с учетом переносов)
    safe_headline_x, safe_headline_y = find_safe_text_position(
        base_x, headline_y, headline_text_width, estimated_headline_height,
        align, w, h, margin, background_zones
    )
    
    # Заголовок - используем возвращаемое значение высоты
    headline_height = renderer.draw_text_with_shadow(
        draw, (safe_headline_x, safe_headline_y), headline,
        renderer.headline_font, style["headline_color"],
        align=align, max_width=headline_text_width,
    )
    
    # Обновляем base_x для последующих элементов, если позиция изменилась
    if safe_headline_x != base_x:
        base_x = safe_headline_x

    # Описание + юрлицо + источник
    full_desc = f"{legal_entity}\n{description}\n{source_info}"
    
    # Инициализируем desc_align по умолчанию
    desc_align = align
    
    # Для диагонального размещения смещаем описание (увеличен отступ от заголовка)
    if placement_variant in ["diagonal_left", "diagonal_right"]:
        desc_x = base_x + (int(w * 0.15) if placement_variant == "diagonal_left" else -int(w * 0.15))
        desc_y = headline_y + headline_height + int(h * 0.06)  # Было 0.04, увеличено до 0.06
        desc_align = align
    elif placement_variant == "split_horizontal":
        # Описание в противоположной стороне
        desc_x = w - margin if base_x == margin else margin
        desc_y = headline_y + headline_height + int(h * 0.05)  # Было 0.03, увеличено до 0.05
        desc_align = "right" if desc_x == w - margin else "left"
    else:
        desc_x = base_x
        desc_y = headline_y + headline_height + int(h * 0.05)  # Было 0.03, увеличено до 0.05
        desc_align = align
    
    # Корректируем позицию и ширину текста, чтобы не выходить за границы изображения
    if desc_align == "left":
        # При выравнивании слева: desc_x должен быть не меньше margin
        desc_x = max(margin, desc_x)
        # text_width ограничиваем так, чтобы desc_x + text_width не превышало w - margin
        max_available_width = w - desc_x - margin
        desc_text_width = min(text_width, max_available_width)
    elif desc_align == "right":
        # При выравнивании справа: desc_x должен быть не больше w - margin
        desc_x = min(w - margin, desc_x)
        # text_width ограничиваем так, чтобы desc_x - text_width не было меньше margin
        max_available_width = desc_x - margin
        desc_text_width = min(text_width, max_available_width)
    else:  # center
        # При выравнивании по центру: текст не должен выходить за границы
        # Левая граница: desc_x - text_width/2 >= margin
        # Правая граница: desc_x + text_width/2 <= w - margin
        max_left_width = (desc_x - margin) * 2
        max_right_width = (w - margin - desc_x) * 2
        max_available_width = min(max_left_width, max_right_width)
        desc_text_width = min(text_width, max_available_width)
    
    # Проверяем и корректируем позицию описания, чтобы избежать пересечения с фонами
    # Оцениваем примерную высоту описания для проверки пересечений
    estimated_desc_height = base_text_size * 10  # Примерная высота (с учетом переносов и нескольких строк)
    safe_desc_x, safe_desc_y = find_safe_text_position(
        desc_x, desc_y, desc_text_width, estimated_desc_height,
        desc_align, w, h, margin, background_zones
    )
    
    # Описание - используем возвращаемое значение высоты
    desc_height = renderer.draw_text_with_shadow(
        draw, (safe_desc_x, safe_desc_y), full_desc,
        renderer.text_font, style["text_color"],
        align=desc_align, max_width=desc_text_width,
    )
    
    # Обновляем desc_x и desc_y для последующих элементов, если позиция изменилась
    if safe_desc_x != desc_x or safe_desc_y != desc_y:
        desc_x = safe_desc_x
        desc_y = safe_desc_y

    # Дисклеймер - вычисляем позицию правильно (как в lombard_overlay.py)
    margin_bottom = int(min(w, h) * 0.06)
    safe_bottom = h - margin_bottom
    disc_y = safe_bottom - base_disclaimer_size * 4  # Верхняя граница блока дисклеймера
    disc_height = base_disclaimer_size * 4  # Высота блока дисклеймера
    
    # Телефон - размещаем ниже описания с учетом реальной высоты
    # Ограничиваем максимальную позицию, чтобы не перекрывать дисклеймер
    # Увеличен отступ между описанием и телефоном для предотвращения наложения
    # Для вертикальных баннеров увеличиваем отступ еще больше
    phone_spacing_base = int(base_text_size * 1.2)  # Базовый отступ
    if not is_horizontal:  # Вертикальный баннер
        phone_spacing = phone_spacing_base + int(base_text_size * 0.8)  # Дополнительный отступ для вертикальных
    else:
        phone_spacing = phone_spacing_base
    
    max_phone_y = disc_y - base_phone_size - int(h * 0.03)  # Было 0.02, увеличено до 0.03 для большего отступа от дисклеймера
    
    if placement_variant == "split_horizontal":
        phone_x = base_x  # Телефон рядом с заголовком
        phone_y_calc = headline_y + headline_height + int(h * 0.15)
        phone_y = min(phone_y_calc, max_phone_y)
        phone_align = align
    elif placement_variant in ["diagonal_left", "diagonal_right"]:
        phone_x = desc_x
        # Используем реальную высоту описания для точного позиционирования
        phone_y_calc = desc_y + desc_height + phone_spacing
        phone_y = min(phone_y_calc, max_phone_y)
        phone_align = desc_align  # Используем выравнивание описания
    else:
        phone_x = desc_x  # Используем позицию описания вместо base_x для вертикальных баннеров
        # Используем реальную высоту описания для точного позиционирования
        phone_y_calc = desc_y + desc_height + phone_spacing
        phone_y = min(phone_y_calc, max_phone_y)
        phone_align = desc_align  # Используем выравнивание описания
    
    # Корректируем позицию телефона, чтобы не выходить за границы
    if phone_align == "left":
        phone_x = max(margin, phone_x)
        # Проверяем ширину текста телефона, чтобы он не вышел за правый край
        # Получаем примерную ширину текста телефона
        phone_bbox = renderer.phone_font.getbbox(phone)
        phone_text_width = phone_bbox[2] - phone_bbox[0]
        # Если телефон может выйти за правый край, ограничиваем позицию
        if phone_x + phone_text_width > w - margin:
            phone_x = max(margin, w - margin - phone_text_width)
    elif phone_align == "right":
        phone_x = min(w - margin, phone_x)
        # Проверяем ширину текста телефона, чтобы он не вышел за левый край
        phone_bbox = renderer.phone_font.getbbox(phone)
        phone_text_width = phone_bbox[2] - phone_bbox[0]
        # Если телефон может выйти за левый край, ограничиваем позицию
        if phone_x - phone_text_width < margin:
            phone_x = min(w - margin, margin + phone_text_width)
    # Для center позиция уже должна быть корректной
    
    # Дополнительная проверка для вертикальных баннеров: убеждаемся, что телефон не накладывается на описание
    if not is_horizontal and phone_y_calc <= desc_y + desc_height:
        # Если телефон все еще может наложиться, увеличиваем отступ
        phone_y = desc_y + desc_height + phone_spacing + int(base_text_size * 0.5)
        phone_y = min(phone_y, max_phone_y)
    
    # Проверяем и корректируем позицию телефона, чтобы избежать пересечения с фонами
    # Оцениваем примерную высоту телефона для проверки пересечений
    estimated_phone_height = base_phone_size * 2  # Примерная высота (с учетом переносов)
    phone_max_width = w - 2 * margin if phone_align == "center" else (w - phone_x - margin if phone_align == "left" else phone_x - margin)
    if phone_max_width < margin:
        phone_max_width = margin
    
    safe_phone_x, safe_phone_y = find_safe_text_position(
        phone_x, phone_y, phone_max_width, estimated_phone_height,
        phone_align, w, h, margin, background_zones
    )
    
    # Телефон - используем возвращаемое значение высоты
    phone_height = renderer.draw_text_with_shadow(
        draw, (safe_phone_x, safe_phone_y), phone,
        renderer.phone_font, style["headline_color"],
        align=phone_align,
        max_width=phone_max_width,
    )
    
    disc_style = random.choice(DISCLAIMER_BG_STYLES)
    adj_y = max(0, h - int((h - disc_y + 10) * disc_style.get("height_multiplier", 1.0)))
    bg_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    disc_draw = ImageDraw.Draw(bg_layer)
    if disc_style.get("type", "solid") == "solid":
        disc_draw.rectangle(
            [0, adj_y, w, h],
            fill=(*disc_style.get("color", (0, 0, 0)), disc_style.get("alpha", 150)),
        )
    elif disc_style.get("type") == "gradient":
        alpha_bottom = disc_style.get("alpha_bottom", 210)
        alpha_top = disc_style.get("alpha_top", 0)
        gradient_height = h - adj_y
        for i in range(gradient_height):
            progress = i / max(1, gradient_height - 1)
            current_alpha = int(alpha_top + (alpha_bottom - alpha_top) * progress)
            y_pos = adj_y + i
            disc_draw.line([(0, y_pos), (w, y_pos)], fill=(*disc_style.get("color", (0, 0, 0)), current_alpha))
    
    image = Image.alpha_composite(image, bg_layer)
    draw = ImageDraw.Draw(image)
    # Дисклеймер - размещаем текст внутри блока
    disc_text_y = disc_y + int(base_disclaimer_size * 0.5)
    renderer.draw_text_with_shadow(
        draw, (w // 2, disc_text_y), disclaimer,
        renderer.disclaimer_font, (255, 255, 255),
        align="center", max_width=int(w * 0.9),
    )
    
    # Возвращаем информацию о позиции дисклеймера для QR
    image._disclaimer_y = disc_y
    image._disclaimer_height = disc_height
    
    return image


def generate_qr_image(url: str = None, company: Optional[Dict[str, str]] = None) -> Optional[Image.Image]:
    """Генерирует QR-код (если доступен пайплайн)."""
    if not QR_AVAILABLE:
        return None
    try:
        pipeline = FolkMedicineQRPipeline(device="cpu")
        qr_type = random.choice(["simple", "artistic_white", "custom_color"])
        qr_url = url or get_company_qr_url(company) or DEFAULT_QR_URL
        return pipeline.generate_qr_variety(qr_url, qr_type=qr_type)
    except Exception:
        return None


def process_batch(
    input_dir: str,
    output_dir: str,
    count: int = 10,
    format_name: str = "horizontal",
    qr_chance: float = 60,
    qr_url: str = None,
    use_real_companies: bool = True,
):
    """Обрабатывает пакет изображений для создания композитных баннеров."""
    in_path = Path(input_dir)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    w, h = BANNER_FORMATS.get(format_name, (1200, 700))

    images = list(in_path.glob("*.png")) + list(in_path.glob("*.jpg"))
    if len(images) < 2:
        print("Ошибка: В папке должно быть минимум 2 изображения")
        return

    for i in range(count):
        pair = random.sample(images, 2)
        engine = DualCompositionEngine(w, h)
        is_horizontal = w > h
        composed_img, layout_type, background_zones, num_backgrounds = engine.compose(
            pair[0], pair[1], shape=random.choice(["circle", "square"]), auto_bg=True
        )
        if not isinstance(background_zones, list):
            background_zones = []

        # Используем реальные компании
        company = get_random_company() if use_real_companies else None
        content = get_random_content(use_real_companies=use_real_companies)
        style = random.choice(LOMBARD_STYLES)
        headline = content["headline"]
        description = content["description"]
        disclaimer = content.get("disclaimer") or get_random_disclaimer(company=company)
        legal_entity = content["legal_entity"]
        source_info = content["source_info"]
        phone = content.get("phone") or generate_phone()
        website = content.get("website", "")

        # Выбираем случайные варианты размещения и шрифтов
        placement_variant = random.choice(TEXT_PLACEMENT_VARIANTS)
        font_variant = random.choice(FONT_SIZE_VARIANTS)

        try:
            final_banner = apply_lombard_text(
                composed_img.copy(),
                headline=headline,
                description=description,
                phone=phone,
                disclaimer=disclaimer,
                legal_entity=legal_entity,
                source_info=source_info,
                layout_name=layout_type,
                style=style,
                background_zones=background_zones,
                num_backgrounds=num_backgrounds,
                is_horizontal=is_horizontal,
                placement_variant=placement_variant,
                font_variant=font_variant,
            )

            # QR (используем сайт компании) - размещаем выше дисклеймера
            if random.random() * 100 < qr_chance:
                qr_url_to_use = qr_url or website or (company["website"] if company else None)
                qr_img = generate_qr_image(qr_url_to_use, company=company)
                if qr_img is not None:
                    qr_size = min(120, int(min(w, h) * 0.12))
                    qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS).convert("RGBA")
                    
                    # Используем правильную функцию для размещения QR выше дисклеймера
                    from scripts.lombard_overlay import find_safe_qr_position_for_lombard
                    
                    # Получаем позицию дисклеймера из изображения (если сохранена)
                    disc_y = getattr(final_banner, '_disclaimer_y', None)
                    disc_height = getattr(final_banner, '_disclaimer_height', None)
                    
                    # Если не сохранена, вычисляем как в lombard_overlay.py
                    if disc_y is None:
                        margin_bottom = int(min(w, h) * 0.06)
                        safe_bottom = h - margin_bottom
                        disc_y = safe_bottom - int(12 * min(w, h) / 1024) * 4
                        disc_height = int(12 * min(w, h) / 1024) * 4
                    
                    qr_pos = find_safe_qr_position_for_lombard(
                        w, h, qr_size, disclaimer_y=disc_y, disclaimer_height=disc_height
                    )
                    final_banner.paste(qr_img, qr_pos, qr_img)

            ts = int(time.time() * 1000)
            fn = f"lombard_dual_{format_name}_{i:03d}_{ts}.png"
            final_banner.save(out_path / fn, quality=100)
            print(f"[{i+1}/{count}] Создан: {fn} (размещение: {placement_variant}, шрифт: {font_variant})")
        except Exception as e:
            print(f"Ошибка при создании баннера {i}: {e}")
            import traceback
            traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="Lombard Dual Composition + QR")
    parser.add_argument("--input-dir", type=str, required=True, help="Папка с фоновыми изображениями")
    parser.add_argument("--output", type=str, default="output/lombard_dual")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--format", type=str, choices=list(BANNER_FORMATS), default="horizontal")
    parser.add_argument("--qr-chance", type=float, default=60, help="Вероятность добавления QR (0-100)")
    parser.add_argument("--qr-url", type=str, default=None, help="URL для QR-кода")
    parser.add_argument("--no-real-companies", action="store_true", help="Не использовать реальные компании из JSON")
    args = parser.parse_args()

    process_batch(
        input_dir=args.input_dir,
        output_dir=args.output,
        count=args.count,
        format_name=args.format,
        qr_chance=args.qr_chance,
        qr_url=args.qr_url,
        use_real_companies=not args.no_real_companies,
    )


if __name__ == "__main__":
    main()
