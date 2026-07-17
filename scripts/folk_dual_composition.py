#!/usr/bin/env python3
"""
Скрипт создания композитных баннеров из двух изображений с QR-кодами.
Поддерживает автоподбор фона, массовую генерацию и умное размещение элементов.
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

# Импорты из основного проекта
try:
    from scripts.folk_medicine_overlay_2 import (
        FolkMedicineBannerOverlay,
        get_random_content,
        FOLK_MEDICINE_STYLES,
        get_layout_by_name,
        DISCLAIMER_BG_STYLES,
        generate_phone
    )
    from scripts.text_overlay import TextRenderer
    from scripts.generate_folk_medicine_with_qr_2 import FolkMedicineQRPipeline
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    sys.exit(1)

# Опционально: DomainProcessor для QR по доменам из CSV (не ломает скрипт при отсутствии)
DOMAIN_PROCESSOR_AVAILABLE = False
DomainProcessor = None
try:
    _qr_gen_path = Path("/mldata/custom-qr-generator")
    if _qr_gen_path.exists():
        sys.path.insert(0, str(_qr_gen_path))
        from qr_generator.domain_processor import DomainProcessor as _DP
        DomainProcessor = _DP
        DOMAIN_PROCESSOR_AVAILABLE = True
except ImportError:
    pass

# Домены для блока «Наши контакты» (как в generate_folk_medicine_with_qr.py, стр. 643–650)
CONTACT_DOMAINS = [
    "newnorma.ru", "namasteguru.ru", "vladimirosipov-online.ru",
    "mariya-gadanie.tilda.ws", "travogor.ru", "happy4woman.ru",
    "sujokonline.ru", "velarinka.ru", "buraev.ru", "osteopatik.ru",
    "массаж-пента.рф", "clinic-amrita.ru", "tibetspb.ru",
    "life-plus.online", "brahmaspb.com", "insam.spb.ru",
    "ayurvedakamala.ru", "medi-cn.ru", "ayurdara.ru", "medfolk.ru",
]


def _load_contact_logos(favicons_dir: Optional[str], logo_height: int, count: int) -> List[Image.Image]:
    """Загружает до count логотипов из favicons_dir, высота = logo_height. Возвращает список RGBA-изображений."""
    out: List[Image.Image] = []
    if not favicons_dir:
        return out
    d = Path(favicons_dir)
    if not d.is_dir():
        return out
    files = list(d.glob("*.png"))
    if not files:
        return out
    n = min(count, len(files))
    chosen = random.sample(files, n)
    for p in chosen:
        try:
            im = Image.open(p).convert("RGBA")
            bw, bh = im.size
            if bh <= 0:
                continue
            scale = logo_height / bh
            nw = max(1, int(bw * scale))
            im = im.resize((nw, logo_height), Image.LANCZOS)
            out.append(im)
        except Exception:
            continue
    return out


class DualCompositionEngine:
    def __init__(self, width: int = 1200, height: int = 800):
        self.width = width
        self.height = height
        self.canvas = None

    def get_average_color(self, img: Image.Image) -> Tuple[int, int, int]:
        """Вычисляет средний медианный цвет для гармоничного фона."""
        # Конвертируем в RGB для гарантированного получения 3 каналов
        if img.mode != 'RGB':
            img_rgb = img.convert('RGB')
        else:
            img_rgb = img
        stat = ImageStat.Stat(img_rgb)
        median = stat.median
        # Берем только первые 3 элемента (R, G, B), игнорируя альфа-канал если есть
        return tuple(map(int, median[:3]))

    def create_soft_mask(self, size: Tuple[int, int], shape: str = "circle") -> Image.Image:
        """Создает маску с мягкими краями для эффекта виньетки."""
        mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        if shape == "circle":
            draw.ellipse([5, 5, size[0]-5, size[1]-5], fill=255)
        else:
            draw.rectangle([10, 10, size[0]-10, size[1]-10], fill=255)
        # Сильное размытие для очень мягкого перехода (воздушный эффект)
        return mask.filter(ImageFilter.GaussianBlur(radius=30))

    def generate_pastel_color(self, base_color: Tuple[int, int, int], color_family: str = None) -> Tuple[int, int, int]:
        """Генерирует пастельный цвет на основе базового цвета.
        
        Args:
            base_color: Базовый цвет (R, G, B)
            color_family: Семейство цветов ("gold", "blue", "green", None для случайного)
        
        Returns:
            Пастельный цвет (R, G, B)
        """
        if color_family is None:
            color_family = random.choice(["gold", "blue", "green"])
        
        r, g, b = base_color
        
        if color_family == "gold":
            # Пастельные золотые оттенки: теплые желто-бежевые
            target = (random.randint(240, 255), random.randint(230, 250), random.randint(200, 230))
            # Смешиваем с базовым цветом
            mix_factor = 0.3  # 30% базового цвета, 70% целевого пастельного
            r = int(r * mix_factor + target[0] * (1 - mix_factor))
            g = int(g * mix_factor + target[1] * (1 - mix_factor))
            b = int(b * mix_factor + target[2] * (1 - mix_factor))
        elif color_family == "blue":
            # Пастельные голубые оттенки: нежно-голубые, бирюзовые
            target = (random.randint(200, 240), random.randint(230, 250), random.randint(240, 255))
            mix_factor = 0.3
            r = int(r * mix_factor + target[0] * (1 - mix_factor))
            g = int(g * mix_factor + target[1] * (1 - mix_factor))
            b = int(b * mix_factor + target[2] * (1 - mix_factor))
        elif color_family == "green":
            # Пастельные зеленые оттенки: мятные, салатовые
            target = (random.randint(200, 230), random.randint(240, 255), random.randint(220, 245))
            mix_factor = 0.3
            r = int(r * mix_factor + target[0] * (1 - mix_factor))
            g = int(g * mix_factor + target[1] * (1 - mix_factor))
            b = int(b * mix_factor + target[2] * (1 - mix_factor))
        else:
            # Общий пастельный подход - осветляем и смягчаем
            r = int(r + (255 - r) * 0.94)
            g = int(g + (255 - g) * 0.94)
            b = int(b + (255 - b) * 0.94)
        
        # Ограничиваем значения
        r = max(200, min(255, r))
        g = max(200, min(255, g))
        b = max(200, min(255, b))
        
        return (r, g, b)

    def pick_bg_color(self, img1: Image.Image, img2: Image.Image = None, auto_mode: bool = True) -> Tuple[int, int, int]:
        """Выбирает цвет фона на основе изображений с пастельными оттенками."""
        if not auto_mode:
            # Если автоподбор выключен, возвращаем случайный пастельный цвет
            color_family = random.choice(["gold", "blue", "green"])
            if color_family == "gold":
                return (random.randint(245, 255), random.randint(240, 250), random.randint(220, 235))
            elif color_family == "blue":
                return (random.randint(220, 240), random.randint(235, 250), random.randint(245, 255))
            else:  # green
                return (random.randint(220, 235), random.randint(245, 255), random.randint(230, 245))
        
        # Получаем средние цвета изображений
        c1 = self.get_average_color(img1)
        if img2 is not None:
            c2 = self.get_average_color(img2)
            # Смешиваем цвета двух изображений
            mixed = tuple(int((a + b) / 2) for a, b in zip(c1, c2))
        else:
            mixed = c1
        
        # Определяем, к какому семейству цветов ближе смешанный цвет
        r, g, b = mixed
        
        # Анализируем доминирующий канал
        max_channel = max(r, g, b)
        if max_channel == r and r > g + 20 and r > b + 20:
            color_family = "gold"  # Преобладает красный/желтый
        elif max_channel == b and b > r + 20 and b > g + 20:
            color_family = "blue"  # Преобладает синий
        elif max_channel == g and g > r + 20 and g > b + 20:
            color_family = "green"  # Преобладает зеленый
        else:
            # Если нет явного доминирования, выбираем случайно
            color_family = random.choice(["gold", "blue", "green"])
        
        # Генерируем пастельный цвет на основе смешанного
        return self.generate_pastel_color(mixed, color_family)

    def compose(self, img1_path: Path, img2_path: Path, shape: str = "circle", auto_bg: bool = True, num_backgrounds: int = None):
        """Создает композицию из одного или двух изображений с отслеживанием зон фонов.
        
        Args:
            img1_path: Путь к первому изображению
            img2_path: Путь ко второму изображению (используется если num_backgrounds == 2)
            shape: Форма маски ("circle" или "square")
            auto_bg: Автоматический подбор цвета фона
            num_backgrounds: Количество фонов (1 или 2). Если None - выбирается случайно.
        """
        img1 = Image.open(img1_path).convert("RGBA")
        img2 = Image.open(img2_path).convert("RGBA") if img2_path else None
        
        # Рандомное количество фонов (1 или 2)
        if num_backgrounds is None:
            num_backgrounds = random.choice([1, 2])
        
        # Выбираем изображения для использования и генерируем пастельный фон
        if num_backgrounds == 1:
            used_img = random.choice([img1, img2]) if img2 else img1
            bg_color = self.pick_bg_color(used_img, None, auto_bg)
        else:
            bg_color = self.pick_bg_color(img1, img2, auto_bg)
        
        # Убеждаемся, что bg_color это кортеж из 3 элементов (R, G, B)
        if len(bg_color) != 3:
            bg_color = tuple(bg_color[:3]) if len(bg_color) >= 3 else (255, 255, 255)
        # Создаем RGBA цвет: (R, G, B, A)
        rgba_color = (*bg_color, 255)
        self.canvas = Image.new("RGBA", (self.width, self.height), rgba_color)
        self.background_zones = []  # Сбрасываем зоны
        
        is_horizontal = self.width > self.height
        # Размер фонов
        side = int(min(self.width, self.height) * 0.35)
        size = (side, side)
        mask = self.create_soft_mask(size, shape)
        margin = int(side * 0.1)  # Отступ для зон
        
        if is_horizontal:
            # Горизонтальный баннер
            base_y = int((self.height - side) / 2)
            # Усиленное смещение для горизонтального баннера (25% вместо 15%)
            offset_factor = 0.25
            offset = int(side * offset_factor)
            
            if num_backgrounds == 1:
                # Один фон - случайно слева или справа
                side_pos = random.choice(["left", "right"])
                if side_pos == "left":
                    pos_x = int(self.width * 0.04)
                    pos_y = max(20, base_y - offset)
                    used_img = img1
                else:
                    pos_x = int(self.width * 0.96 - side)
                    pos_y = min(self.height - side - 20, base_y + offset)
                    used_img = img2 if img2 else img1
                
                self.canvas.paste(ImageOps.fit(used_img, size, Image.LANCZOS), (pos_x, pos_y), mask)
                self.background_zones = [
                    (pos_x - margin, pos_y - margin, pos_x + side + margin, pos_y + side + margin)
                ]
                layout_type = "classic_right" if side_pos == "left" else "classic_left"
            else:
                # Два фона - усиленное смещение
                pos1_x = int(self.width * 0.04)
                pos1_y = max(20, base_y - offset)
                pos2_x = int(self.width * 0.96 - side)
                pos2_y = min(self.height - side - 20, base_y + offset)
                
                self.canvas.paste(ImageOps.fit(img1, size, Image.LANCZOS), (pos1_x, pos1_y), mask)
                self.canvas.paste(ImageOps.fit(img2, size, Image.LANCZOS), (pos2_x, pos2_y), mask)
                
                self.background_zones = [
                    (pos1_x - margin, pos1_y - margin, pos1_x + side + margin, pos1_y + side + margin),
                    (pos2_x - margin, pos2_y - margin, pos2_x + side + margin, pos2_y + side + margin),
                ]
                layout_type = "center_stack"
        else:
            # Вертикальный баннер
            # Верхний фон - больше вправо или влево к стороне
            top_side = random.choice(["left", "right"])
            top_offset_factor = 0.3  # 30% смещения к краю
            top_base_x = int((self.width - side) / 2)
            
            if top_side == "left":
                top_pos_x = max(20, int(self.width * 0.05))
            else:
                top_pos_x = min(self.width - side - 20, int(self.width * 0.95 - side))
            
            top_pos_y = int(self.height * 0.04)
            
            # Нижний фон - поднять выше и ближе к правому/левому краю
            bottom_side = random.choice(["left", "right"])
            bottom_offset_factor = 0.3
            bottom_pos_y = int(self.height * 0.85 - side)  # Поднят выше (было 0.96)
            
            if bottom_side == "left":
                bottom_pos_x = max(20, int(self.width * 0.05))
            else:
                bottom_pos_x = min(self.width - side - 20, int(self.width * 0.95 - side))
            
            if num_backgrounds == 1:
                # Один фон - случайно верхний или нижний
                use_top = random.choice([True, False])
                if use_top:
                    self.canvas.paste(ImageOps.fit(img1, size, Image.LANCZOS), (top_pos_x, top_pos_y), mask)
                    self.background_zones = [
                        (top_pos_x - margin, top_pos_y - margin, top_pos_x + side + margin, top_pos_y + side + margin)
                    ]
                    layout_type = "classic_left" if top_side == "right" else "classic_right"
                else:
                    self.canvas.paste(ImageOps.fit(img2 if img2 else img1, size, Image.LANCZOS), (bottom_pos_x, bottom_pos_y), mask)
                    self.background_zones = [
                        (bottom_pos_x - margin, bottom_pos_y - margin, bottom_pos_x + side + margin, bottom_pos_y + side + margin)
                    ]
                    layout_type = "classic_left" if bottom_side == "right" else "classic_right"
            else:
                # Два фона
                self.canvas.paste(ImageOps.fit(img1, size, Image.LANCZOS), (top_pos_x, top_pos_y), mask)
                self.canvas.paste(ImageOps.fit(img2, size, Image.LANCZOS), (bottom_pos_x, bottom_pos_y), mask)
                
                self.background_zones = [
                    (top_pos_x - margin, top_pos_y - margin, top_pos_x + side + margin, top_pos_y + side + margin),
                    (bottom_pos_x - margin, bottom_pos_y - margin, bottom_pos_x + side + margin, bottom_pos_y + side + margin),
                ]
                layout_type = "top_bottom"

        return self.canvas, layout_type, self.background_zones, num_backgrounds

def find_safe_text_position(
    img_width: int, img_height: int, 
    background_zones: List[Tuple[int, int, int, int]],
    layout_name: str
) -> Tuple[int, int]:
    """Находит безопасную позицию для текста, избегая зон фонов."""
    margin = int(img_width * 0.06)
    
    # Определяем базовую позицию по лейауту
    if "left" in layout_name:
        base_x = margin
        align = "left"
    elif "right" in layout_name:
        base_x = img_width - margin
        align = "right"
    else:  # center
        base_x = img_width // 2
        align = "center"
    
    # Проверяем пересечение с зонами фонов
    text_width = int(img_width * 0.6)  # Примерная ширина текста
    text_height = int(img_height * 0.4)  # Примерная высота текстового блока
    
    # Пробуем разные Y позиции
    for y_offset in [0, int(img_height * 0.1), int(img_height * 0.2), int(img_height * -0.1)]:
        test_y = max(margin, min(img_height - text_height - margin, img_height // 3 + y_offset))
        
        # Определяем границы текстовой зоны
        if align == "left":
            text_x1, text_x2 = base_x, base_x + text_width
        elif align == "right":
            text_x1, text_x2 = base_x - text_width, base_x
        else:  # center
            text_x1, text_x2 = base_x - text_width // 2, base_x + text_width // 2
        
        text_y1, text_y2 = test_y, test_y + text_height
        
        # Проверяем пересечение с зонами фонов
        overlaps = False
        for bg_x1, bg_y1, bg_x2, bg_y2 in background_zones:
            if not (text_x2 < bg_x1 or text_x1 > bg_x2 or text_y2 < bg_y1 or text_y1 > bg_y2):
                overlaps = True
                break
        
        if not overlaps:
            return (base_x, test_y)
    
    # Если не нашли идеальную позицию, возвращаем базовую
    return (base_x, margin)


def find_safe_qr_position(
    img_width: int, img_height: int,
    background_zones: List[Tuple[int, int, int, int]],
    text_zones: List[Tuple[int, int, int, int]],
    qr_size: int = 150
) -> Tuple[int, int]:
    """Находит безопасную позицию для QR-кода, избегая фонов и текста."""
    # Защита от неправильного типа
    if not isinstance(background_zones, list):
        background_zones = []
    if not isinstance(text_zones, list):
        text_zones = []
    
    margin = 20
    safety_margin = 15  # Дополнительный отступ вокруг QR
    
    # Кандидаты на позиции: верхний правый, левый нижний, правый нижний (рандомно)
    corner_candidates = [
        (img_width - qr_size - margin, margin),  # Правый верхний
        (margin, img_height - qr_size - margin),  # Левый нижний
        (img_width - qr_size - margin, img_height - qr_size - margin),  # Правый нижний
    ]
    # Рандомно выбираем один из углов
    candidates = [random.choice(corner_candidates)]
    
    # Проверяем каждую позицию
    for qr_x, qr_y in candidates:
        qr_x1 = qr_x - safety_margin
        qr_y1 = qr_y - safety_margin
        qr_x2 = qr_x + qr_size + safety_margin
        qr_y2 = qr_y + qr_size + safety_margin
        
        # Проверяем пересечение с зонами фонов
        overlaps_bg = False
        for bg_x1, bg_y1, bg_x2, bg_y2 in background_zones:
            if not (qr_x2 < bg_x1 or qr_x1 > bg_x2 or qr_y2 < bg_y1 or qr_y1 > bg_y2):
                overlaps_bg = True
                break
        
        if overlaps_bg:
            continue
        
        # Проверяем пересечение с текстовыми зонами
        overlaps_text = False
        for text_x1, text_y1, text_x2, text_y2 in text_zones:
            if not (qr_x2 < text_x1 or qr_x1 > text_x2 or qr_y2 < text_y1 or qr_y1 > text_y2):
                overlaps_text = True
                break
        
        if not overlaps_text:
            return (qr_x, qr_y)
    
    # Fallback: правый верхний угол
    return (img_width - qr_size - margin, margin)


def generate_qr_image(
    qr_pipeline: "FolkMedicineQRPipeline",
    domain_processor: Any,
) -> Image.Image:
    """
    Генерирует QR-код: либо по случайному домену из CSV (domain_processor),
    либо через внутренний пайплайн (qr_pipeline). Скрипты не ломаются:
    при отсутствии domain_processor используется прежняя логика.
    """
    if domain_processor is not None and getattr(domain_processor, "domains", None):
        # Случайный домен из DomainProcessor
        entry = random.choice(domain_processor.domains)
        url = entry.url if entry.url else f"https://{entry.domain}"
        favicon_path = domain_processor.get_favicon(entry.domain, strategy="random") if domain_processor.favicons else None
        img = domain_processor.generator.generate(
            data=url,
            style=domain_processor.default_style,
            logo_path=favicon_path,
        )
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        return img
    # Иначе — внутренний скрипт (как раньше)
    qr_type = random.choice(["simple", "artistic_white", "custom_color"])
    return qr_pipeline.generate_qr_variety("https://medfolk.ru/master", qr_type=qr_type)


def apply_text_with_avoidance(
    image: Image.Image,
    headline: str,
    description: str,
    phone: str,
    disclaimer: str,
    layout_name: str,
    style: Dict,
    background_zones: List[Tuple[int, int, int, int]],
    num_backgrounds: int = 2,
    is_horizontal: bool = True,
    favicons_dir: Optional[str] = None,
) -> Image.Image:
    """Накладывает текст на изображение, избегая зон фонов.
    
    Над телефоном: «Наши контакты:». Под телефоном (по левому краю): 1–3 логотипа
    из favicons_dir по высоте текста телефона, затем один домен из CONTACT_DOMAINS.
    
    Args:
        image: Изображение для наложения текста
        headline: Заголовок
        description: Описание
        phone: Телефон
        disclaimer: Дисклеймер
        layout_name: Название лейаута
        style: Стиль текста
        background_zones: Список зон фонов
        num_backgrounds: Количество фонов (1 или 2)
        is_horizontal: Горизонтальная ориентация баннера
        favicons_dir: Директория с логотипами для блока контактов (например /mldata/logo_for_qr_extracted)
    """
    # Защита от неправильного типа background_zones
    if not isinstance(background_zones, list):
        background_zones = []
    
    if image.mode != 'RGBA':
        image = image.convert('RGBA')
    
    w, h = image.size
    REF_WIDTH = 1024
    scale = min(w, h) / REF_WIDTH
    
    renderer = TextRenderer(
        style,
        headline_size=int(58 * scale),
        text_size=int(28 * scale),
        phone_size=int(40 * scale),
        disclaimer_size=int(13 * scale)
    )
    
    draw = ImageDraw.Draw(image)
    margin = int(w * 0.06)
    
    # Определяем ширину текста в зависимости от количества фонов
    if num_backgrounds == 1:
        # При одном фоне - обычная ширина, но смещаем в противоположную сторону
        text_width = int(w * 0.6)
    else:
        # При двух фонах - сужаем пространство для текста
        text_width = int(w * 0.45)
    
    # Определяем базовую позицию по лейауту и количеству фонов
    # ВАЖНО: Текст всегда в противоположной стороне от фона(ов)
    
    if len(background_zones) > 0:
        if num_backgrounds == 1:
            # При одном фоне - смещаем текст в противоположную сторону
            bg_x1, bg_y1, bg_x2, bg_y2 = background_zones[0]
            bg_center_x = (bg_x1 + bg_x2) / 2
            
            if bg_center_x < w / 2:
                # Фон слева - текст справа
                base_x = int(w * 0.65)
                align = "right"
                layout_name = "classic_right"
            else:
                # Фон справа - текст слева
                base_x = int(w * 0.35)
                align = "left"
                layout_name = "classic_left"
        else:
            # При двух фонах - определяем, где больше места для текста
            # Находим центр между фонами или свободную зону
            if is_horizontal:
                # Горизонтальный: фоны по краям, текст в центре, но ниже
                base_x = w // 2
                align = "center"
            else:
                # Вертикальный: фоны сверху и снизу, текст в центре, но в противоположной стороне от верхнего
                top_bg = min(background_zones, key=lambda z: z[1])
                bg_x1, bg_y1, bg_x2, bg_y2 = top_bg
                bg_center_x = (bg_x1 + bg_x2) / 2
                
                if bg_center_x < w / 2:
                    # Верхний фон слева - текст справа
                    base_x = int(w * 0.65)
                    align = "right"
                else:
                    # Верхний фон справа - текст слева
                    base_x = int(w * 0.35)
                    align = "left"
    else:
        # Если нет фонов - используем лейаут по умолчанию
        if "left" in layout_name:
            base_x = margin
            align = "left"
        elif "right" in layout_name:
            base_x = w - margin
            align = "right"
        else:  # center
            base_x = w // 2
            align = "center"
    
    # Для вертикальной ориентации - заголовок смещаем в противоположную сторону от верхнего фона
    if not is_horizontal and len(background_zones) > 0:
        # Находим верхний фон
        top_bg = min(background_zones, key=lambda z: z[1])
        bg_x1, bg_y1, bg_x2, bg_y2 = top_bg
        bg_center_x = (bg_x1 + bg_x2) / 2
        
        if bg_center_x < w / 2:
            # Верхний фон слева - заголовок справа
            headline_x = int(w * 0.65)
            headline_align = "right"
        else:
            # Верхний фон справа - заголовок слева
            headline_x = int(w * 0.35)
            headline_align = "left"
    else:
        # Для горизонтального - заголовок на той же позиции, что и основной текст
        headline_x = base_x
        headline_align = align
    
    # Находим безопасную Y позицию для заголовка (ниже, чем было)
    headline_y = int(h * 0.20)  # Начинаем еще ниже (20% от высоты)
    headline_height = int(renderer.headline_font.size * 1.5)
    
    # Определяем границы текстовой зоны для проверки пересечений
    if headline_align == "left":
        text_x1, text_x2 = headline_x, headline_x + text_width
    elif headline_align == "right":
        text_x1, text_x2 = headline_x - text_width, headline_x
    else:  # center
        text_x1, text_x2 = headline_x - text_width // 2, headline_x + text_width // 2
    
    # Проверяем пересечение с фонами и корректируем позицию заголовка
    for offset in [0, int(h * 0.05), int(h * 0.1), int(h * 0.15)]:
        test_y = int(h * 0.20) + offset
        if test_y + headline_height > h - 300:  # Оставляем место для описания, телефона и дисклеймера
            break
        
        text_y1, text_y2 = test_y, test_y + headline_height
        
        # Проверяем пересечение с зонами фонов
        overlaps = False
        for bg_x1, bg_y1, bg_x2, bg_y2 in background_zones:
            if not (text_x2 < bg_x1 or text_x1 > bg_x2 or text_y2 < bg_y1 or text_y1 > bg_y2):
                overlaps = True
                break
        
        if not overlaps:
            headline_y = test_y
            break
    
    # Рисуем заголовок (используем headline_x для вертикальной ориентации)
    renderer.draw_text_with_shadow(
        draw, (headline_x, headline_y), headline,
        renderer.headline_font, style['headline_color'],
        align=headline_align, max_width=text_width
    )
    
    # Описание - НИЖЕ заголовка с большим отступом (для горизонтальных и вертикальных)
    # Увеличиваем отступ между заголовком и описанием
    desc_y = headline_y + headline_height + int(renderer.headline_font.size * 1.2)  # Больший отступ
    desc_height = int(renderer.text_font.size * 10)  # Увеличена примерная высота для многострочного текста
    
    # Определяем границы текстовой зоны для описания
    if align == "left":
        desc_x1, desc_x2 = base_x, base_x + text_width
    elif align == "right":
        desc_x1, desc_x2 = base_x - text_width, base_x
    else:  # center
        desc_x1, desc_x2 = base_x - text_width // 2, base_x + text_width // 2
    
    # Корректируем позицию описания если нужно (проверяем пересечения с фонами)
    for offset in [0, int(h * 0.05), int(h * 0.1), int(h * 0.15)]:
        test_y = desc_y + offset
        if test_y + desc_height > h - 200:  # Оставляем место для телефона и дисклеймера
            break
        
        text_y1, text_y2 = test_y, test_y + desc_height
        overlaps = False
        for bg_x1, bg_y1, bg_x2, bg_y2 in background_zones:
            if not (desc_x2 < bg_x1 or desc_x1 > bg_x2 or text_y2 < bg_y1 or text_y1 > bg_y2):
                overlaps = True
                break
        
        if not overlaps:
            desc_y = test_y
            break
    
    # Рисуем описание (используем base_x и align для правильного позиционирования)
    renderer.draw_text_with_shadow(
        draw, (base_x, desc_y), description,
        renderer.text_font, style['text_color'],
        align=align, max_width=text_width
    )
    
    # Телефон - ниже описания. Над телефоном «Наши контакты:» — закладываем место
    label_height = int(renderer.phone_font.size * 1.0)
    gap = int(renderer.phone_font.size * 0.35)
    block_offset = label_height + gap + int(renderer.text_font.size * 0.8)
    phone_y = desc_y + desc_height + block_offset
    phone_height = int(renderer.phone_font.size * 1.2)
    
    # Определяем границы зоны телефона для проверки пересечений
    if align == "left":
        phone_x1, phone_x2 = base_x, base_x + int(text_width * 0.5)  # Телефон уже текста
    elif align == "right":
        phone_x1, phone_x2 = base_x - int(text_width * 0.5), base_x
    else:  # center
        phone_x1, phone_x2 = base_x - int(text_width * 0.25), base_x + int(text_width * 0.25)
    
    # Проверяем пересечение телефона с фонами
    phone_text_y1, phone_text_y2 = phone_y, phone_y + phone_height
    phone_overlaps = False
    for bg_x1, bg_y1, bg_x2, bg_y2 in background_zones:
        if not (phone_x2 < bg_x1 or phone_x1 > bg_x2 or phone_text_y2 < bg_y1 or phone_text_y1 > bg_y2):
            phone_overlaps = True
            break
    
    if phone_overlaps:
        # Сдвигаем телефон ниже
        phone_y = max(phone_y, int(h * 0.75))
    
    # Над телефоном: «Наши контакты:»
    contacts_label = "Наши контакты:"
    contacts_y = phone_y - label_height - gap
    renderer.draw_text_with_shadow(
        draw, (base_x, contacts_y), contacts_label,
        renderer.phone_font, style['headline_color'],
        align=align
    )
    
    renderer.draw_text_with_shadow(
        draw, (base_x, phone_y), phone,
        renderer.phone_font, style['headline_color'],
        align=align
    )
    
    # Под телефоном, по левому краю: 1–3 логотипа из favicons_dir (высота = текст телефона), затем домен
    logo_height = int(renderer.phone_font.size * 1.0)
    n_logos = random.randint(1, 3)
    logos = _load_contact_logos(favicons_dir, logo_height, n_logos)
    row_gap = int(renderer.phone_font.size * 0.4)
    row_y = phone_y + phone_height + row_gap
    left_x = margin
    disclaimer_top = h - 92
    
    if row_y + logo_height < disclaimer_top:
        cursor_x = left_x
        logo_spacing = max(4, logo_height // 6)
        for logo_im in logos:
            lw, lh = logo_im.size
            if cursor_x + lw > w - margin:
                break
            image.paste(logo_im, (cursor_x, row_y), logo_im)
            cursor_x += lw + logo_spacing
        
        domain = random.choice(CONTACT_DOMAINS)
        domain_x = cursor_x if cursor_x > left_x else left_x
        draw = ImageDraw.Draw(image)
        renderer.draw_text_with_shadow(
            draw, (domain_x, row_y), domain,
            renderer.phone_font, style['headline_color'],
            align="left"
        )
    
    # Дисклеймер - всегда внизу по центру
    disc_style = random.choice(DISCLAIMER_BG_STYLES)
    disc_y = h - 80
    actual_h = int((h - disc_y + 10) * disc_style.get('height_multiplier', 1.0))
    adj_y = max(0, h - actual_h)
    
    bg_layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
    disc_draw = ImageDraw.Draw(bg_layer)
    if disc_style.get('type', 'solid') == 'solid':
        disc_draw.rectangle(
            [0, adj_y, w, h],
            fill=(*disc_style.get('color', (0, 0, 0)), disc_style.get('alpha', 150))
        )
    image = Image.alpha_composite(image, bg_layer)
    
    draw = ImageDraw.Draw(image)
    renderer.draw_text_with_shadow(
        draw, (w // 2, h - 60), disclaimer,
        renderer.disclaimer_font, (255, 255, 255),
        align="center", max_width=int(w * 0.9)
    )
    
    return image


def get_text_zones(
    img_width: int, img_height: int,
    layout_name: str,
    text_x: int, text_y: int
) -> List[Tuple[int, int, int, int]]:
    """Определяет зоны, занятые текстом и телефоном."""
    zones = []
    margin = int(img_width * 0.06)
    text_width = int(img_width * 0.6)
    
    # Зона заголовка
    headline_height = int(img_height * 0.08)
    if "left" in layout_name:
        h_x1, h_x2 = text_x, text_x + text_width
    elif "right" in layout_name:
        h_x1, h_x2 = text_x - text_width, text_x
    else:  # center
        h_x1, h_x2 = text_x - text_width // 2, text_x + text_width // 2
    zones.append((h_x1, text_y, h_x2, text_y + headline_height))
    
    # Зона описания
    desc_y = int(img_height // 2.5)
    desc_height = int(img_height * 0.25)
    zones.append((h_x1, desc_y, h_x2, desc_y + desc_height))
    
    # Зона телефона
    phone_y = int(img_height // 1.4)
    phone_height = int(img_height * 0.06)
    zones.append((h_x1, phone_y, h_x2, phone_y + phone_height))
    
    # Зона дисклеймера (внизу по центру)
    disc_y = img_height - 80
    disc_height = 40
    disc_width = int(img_width * 0.9)
    disc_x1 = (img_width - disc_width) // 2
    zones.append((disc_x1, disc_y, disc_x1 + disc_width, disc_y + disc_height))
    
    return zones


def process_batch(input_dir: str, output_dir: str, count: int, 
                  h_ratio: float, v_ratio: float, circle_ratio: float, square_ratio: float,
                  qr_chance: float, auto_bg: bool,
                  domains_csv: Optional[str] = None,
                  favicons_dir: Optional[str] = None):
    
    in_path = Path(input_dir)
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    images = list(in_path.glob("*.png")) + list(in_path.glob("*.jpg"))
    if len(images) < 2:
        print("Ошибка: В папке должно быть минимум 2 изображения")
        return

    # Загружаем QR пайплайн. Важно: используем CPU, чтобы не конфликтовать с основной памятью GPU
    print("Инициализация QR пайплайна...")
    qr_pipeline = FolkMedicineQRPipeline(device="cpu")

    # Опционально: DomainProcessor для QR по доменам из CSV
    domain_processor = None
    if domains_csv and DOMAIN_PROCESSOR_AVAILABLE and DomainProcessor is not None:
        try:
            domain_processor = DomainProcessor(
                domains_csv=domains_csv,
                favicons_dir=favicons_dir,
            )
            domain_processor.load_domains()
            if domain_processor.domains:
                print(f"QR по доменам из CSV: {domains_csv} ({len(domain_processor.domains)} доменов)")
            else:
                domain_processor = None
        except Exception as e:
            print(f"Предупреждение: DomainProcessor не загружен ({e}), QR — внутренний скрипт.")
            domain_processor = None
    elif domains_csv and not DOMAIN_PROCESSOR_AVAILABLE:
        print("Предупреждение: --domains-csv задан, но custom-qr-generator недоступен. QR — внутренний скрипт.")

    print(f"Старт генерации {count} композитных баннеров...")
    
    for i in range(count):
        # 1. Выбор параметров
        orient = random.choices(["h", "v"], weights=[h_ratio, v_ratio])[0]
        w, h = (1200, 800) if orient == "h" else (800, 1200)
        shape = random.choices(["circle", "square"], weights=[circle_ratio, square_ratio])[0]
        pair = random.sample(images, 2)
        
        engine = DualCompositionEngine(w, h)
        is_horizontal = orient == "h"
        composed_img, suggested_layout, background_zones, num_backgrounds = engine.compose(
            pair[0], pair[1], shape=shape, auto_bg=auto_bg
        )
        
        # Убеждаемся, что background_zones это список
        if not isinstance(background_zones, list):
            background_zones = []
        
        # 2. Текст с учетом зон фонов
        layout_obj = get_layout_by_name(suggested_layout)
        layout_name = layout_obj.get("name", "center_stack") if layout_obj else "center_stack"
        content = get_random_content()
        style = random.choice(FOLK_MEDICINE_STYLES)
        
        try:
            # Накладываем текст с учетом зон фонов («Наши контакты:», логотипы, домен)
            final_banner = apply_text_with_avoidance(
                composed_img.copy(),
                content['headline'],
                content['description'],
                content.get('phone') or generate_phone(),
                content['disclaimer'],
                layout_name,
                style,
                background_zones,
                num_backgrounds=num_backgrounds,
                is_horizontal=is_horizontal,
                favicons_dir=favicons_dir,
            )
            
            # Определяем текстовые зоны для QR (приблизительно)
            margin = int(w * 0.06)
            text_width = int(w * 0.45 if num_backgrounds == 2 else w * 0.6)
            if "left" in layout_name:
                text_x = margin
            elif "right" in layout_name:
                text_x = w - margin
            else:
                text_x = w // 2
            text_zones = get_text_zones(w, h, layout_name, text_x, int(h * 0.15))
            
            # 3. QR-код (накладываем после текста, чтобы избежать пересечений)
            # Либо по случайному домену из CSV (domain_processor), либо внутренний скрипт
            if random.random() * 100 < qr_chance:
                qr_img = generate_qr_image(qr_pipeline, domain_processor)
                qr_size = 120  # Уменьшенный размер
                qr_img = qr_img.resize((qr_size, qr_size), Image.LANCZOS).convert("RGBA")
                
                # Находим безопасную позицию для QR (рандомно в одном из углов)
                qr_pos = find_safe_qr_position(w, h, background_zones, text_zones, qr_size)
                final_banner.paste(qr_img, qr_pos, qr_img)
            
            ts = int(time.time() * 1000)
            file_name = f"dual_qr_{i:03d}_{ts}.png"
            final_banner.save(out_path / file_name, quality=95)
            print(f"[{i+1}/{count}] Создан: {file_name}")
        except Exception as e:
            print(f"Ошибка при наложении текста на баннер {i}: {e}")
            import traceback
            traceback.print_exc()

def main():
    parser = argparse.ArgumentParser(description="Dual Composition QR Generator")
    parser.add_argument("--input-dir", type=str, required=True)
    parser.add_argument("--output", type=str, default="output/dual_composition_qr")
    parser.add_argument("--count", type=int, default=10)
    
    parser.add_argument("--percent-h", type=float, default=50)
    parser.add_argument("--percent-v", type=float, default=50)
    parser.add_argument("--percent-circle", type=float, default=70)
    parser.add_argument("--percent-square", type=float, default=30)
    parser.add_argument("--qr-chance", type=float, default=60)
    
    parser.add_argument("--no-auto-bg", action="store_true")
    
    # Опционально: QR по доменам из CSV (domain_processor); если не задано — QR как раньше
    parser.add_argument(
        "--domains-csv",
        type=str,
        default=None,
        help="Путь к CSV с доменами для случайной генерации QR (например /mldata/traditional_healers_domains.csv). Без указания используется внутренний скрипт.",
    )
    parser.add_argument(
        "--favicons-dir",
        type=str,
        default=None,
        help="Директория с фавиконами для QR при использовании --domains-csv.",
    )
    
    args = parser.parse_args()
    
    process_batch(
        input_dir=args.input_dir,
        output_dir=args.output,
        count=args.count,
        h_ratio=args.percent_h,
        v_ratio=args.percent_v,
        circle_ratio=args.percent_circle,
        square_ratio=args.percent_square,
        qr_chance=args.qr_chance,
        auto_bg=not args.no_auto_bg,
        domains_csv=args.domains_csv,
        favicons_dir=args.favicons_dir,
    )

if __name__ == "__main__":
    main()