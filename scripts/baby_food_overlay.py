#!/usr/bin/env python3
"""
Baby Food Ad Banner Overlay (Детское питание 0–3 года)

Генерация рекламных баннеров детского питания с учётом требований ФЗ «О рекламе» РФ
и гайдлайна по категории «Детское питание (0–3 года)».

ОБЯЗАТЕЛЬНЫЕ ЭЛЕМЕНТЫ (Must-Have):
- Возрастная маркировка: «0+», «с 6 месяцев», «для детей с 1 года» и т.п.
- Предупредительная надпись (дисклеймер): «Молоко матери — идеальное питание...»,
  «Перед вводом нового продукта проконсультируйтесь со специалистом».

КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО (Red Lines):
- Утверждения о замене ГВ: продукт как полноценный заменитель женского молока.
- Преимущества искусственного вскармливания перед грудным.

Примеры:
    python scripts/baby_food_overlay.py --image bg.png --output output/baby_food/
    python scripts/baby_food_overlay.py --list-headlines
    python scripts/baby_food_overlay.py --validate-text "Лучше маминого молока"
"""

import argparse
import os
import sys
import re
import json
from pathlib import Path
from PIL import Image, ImageDraw
from typing import Any, Dict, List, Optional, Tuple
import random

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.text_overlay import (
    TextRenderer,
    LAYOUTS,
    get_layout_by_name,
)

# =============================================================================
# Legal Compliance / Гайдлайн «Детское питание (0–3 года)»
# =============================================================================

# ЗАПРЕЩЁННЫЕ формулировки (замена ГВ, преимущества ИВ)
FORBIDDEN_PHRASES = [
    r"лучше\s+маминого\s+молок",
    r"полная\s+замена\s+гв",
    r"заменяет\s+грудное\s+молоко",
    r"заменитель\s+грудного",
    r"забудьте\s+о\s+кормлении\s+грудью",
    r"не\s+требует\s+докорм",
    r"удобнее\s+грудного",
    r"полезнее\s+грудного",
    r"полноценная\s+замена\s+молок",
    r"искусственное\s+вскармливание\s+лучше",
    r"смесь\s+лучше\s+молок",
]

# Обязательные элементы в дисклеймере
REQUIRED_DISCLAIMER_BREAST = r"молоко\s+матери|идеальное\s+питание\s+для\s+грудного"
REQUIRED_DISCLAIMER_SPECIALIST = r"проконсультируйтесь\s+со\s+специалистом|консультация\s+специалиста|консультация\s+врача"


class BabyFoodValidator:
    """Валидатор текстов на соответствие гайдлайну детского питания (0–3 года)."""

    @staticmethod
    def check_forbidden(text: str) -> List[str]:
        """Проверяет текст на запрещённые формулировки (замена ГВ, преимущества ИВ)."""
        text_lower = text.lower()
        violations = []
        for pattern in FORBIDDEN_PHRASES:
            if re.search(pattern, text_lower):
                match = re.search(pattern, text_lower)
                violations.append(f"Запрещено: '{match.group()}' (недопустимо для детского питания)")
        return violations

    @staticmethod
    def check_disclaimer_breast(disclaimer: str) -> bool:
        """Проверяет наличие фразы о грудном молоке в дисклеймере."""
        return bool(re.search(REQUIRED_DISCLAIMER_BREAST, (disclaimer or "").lower()))

    @staticmethod
    def check_disclaimer_specialist(disclaimer: str) -> bool:
        """Проверяет наличие призыва проконсультироваться со специалистом."""
        return bool(re.search(REQUIRED_DISCLAIMER_SPECIALIST, (disclaimer or "").lower()))

    @staticmethod
    def check_age_marking(text: str) -> bool:
        """Проверяет наличие возрастной маркировки (0+, с N месяцев, для детей с N года)."""
        patterns = [
            r"0\s*\+",
            r"с\s+\d+\s*месяц",
            r"с\s+\d+\s*мес\.",
            r"для\s+детей\s+с\s+\d+\s*(года|лет)",
            r"с\s+рождения",
            r"прикорм\s+с\s+\d+",
        ]
        text_lower = (text or "").lower()
        return any(re.search(p, text_lower) for p in patterns)

    @staticmethod
    def validate(headline: str, description: str, disclaimer: str, age_marking: str = "") -> Dict[str, Any]:
        """
        Полная валидация текстов баннера.
        Returns: {"valid": bool, "violations": [...], "warnings": [...]}
        """
        full_text = f"{headline or ''} {description or ''} {disclaimer or ''} {age_marking or ''}"
        violations = BabyFoodValidator.check_forbidden(full_text)
        warnings = []

        if not BabyFoodValidator.check_disclaimer_breast(disclaimer or ""):
            warnings.append("В дисклеймере должна быть фраза о грудном молоке (идеальное питание для грудного ребенка)")
        if not BabyFoodValidator.check_disclaimer_specialist(disclaimer or ""):
            warnings.append("В дисклеймере должен быть призыв проконсультироваться со специалистом")
        if not BabyFoodValidator.check_age_marking(full_text):
            warnings.append("Должна присутствовать возрастная маркировка (0+, с 6 месяцев, для детей с 1 года и т.п.)")

        return {
            "valid": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
        }


# =============================================================================
# ТЕКСТЫ: заголовок и дисклеймер согласованы по возрасту; основной текст — без дублирования возраста
# Тональность: заботливая, экспертная. Упор на пользу, натуральность, безопасность.
# =============================================================================

# Нейтральные описания без возрастных паттернов (не дублируют заголовок и дисклеймер)
BABY_FOOD_DESCRIPTIONS_NEUTRAL = [
    "Витамины и нутриенты для гармоничного развития. Без добавления соли и сахара.",
    "Натуральные ингредиенты. Без ГМО и консервантов. Рекомендовано для прикорма.",
    "Сбалансированный состав. Разработано совместно с педиатрами. Нежная текстура.",
    "Гипоаллергенная формула. Идеально для первого прикорма. Мягкая консистенция.",
    "Только натуральные овощи и фрукты. Без искусственных добавок.",
    "Удобная упаковка для дома и прогулок. Сохраняем пользу и вкус.",
    "Богато витаминами и минералами. Вкусно и полезно для малыша.",
    "Экологичные ингредиенты. Контроль качества на каждом этапе.",
    "Рекомендовано для прикорма. Мягкая консистенция.",
    "Первый прикорм: мягко и полезно. Без красителей.",
    "Поддержка иммунитета и здорового роста. Рекомендовано специалистами.",
    "Нежная каша для комфортного пищеварения. Гипоаллергенная формула.",
    "Фруктовые и овощные пюре. Разнообразие вкусов для малыша.",
    "Качество и безопасность — наш приоритет.",
    "Сбалансированное питание для роста и развития.",
]

# Дополнительные безопасные заголовки (без возраста, по ФЗ-38)
GENERIC_BABY_FOOD_HEADLINES = [
    "Натуральное питание для здорового роста",
    "Вкус и польза в каждой ложке",
    "Питание, разработанное с учётом потребностей малыша",
    "Поддержка развития: питание с витаминами и минералами",
    "Натуральные ингредиенты — забота о здоровье ребёнка",
    "Питание, которое растёт вместе с малышом",
    "Качество, проверенное временем",
    "Питание для активного развития и хорошего настроения",
    "Безопасность и натуральность — наш приоритет",
    "Питание, созданное с любовью для вашего малыша",
    "Здоровье в каждой порции",
    "Питание, которое помогает расти и познавать мир",
    "Натуральные ингредиенты для здорового прикорма",
    "Питание, разработанное совместно с педиатрами",
    "Качество, которое выбирают мамы",
    "Питание, которое адаптировано под потребности ребёнка",
    "Натуральные вкусы для первых блюд",
    "Питание, которое укрепляет иммунитет",
    "Качество и безопасность — наши главные принципы",
    "Питание, которое дарит радость кормления",
]

# Группы: заголовок и age_marking согласованы; описание берётся из нейтрального списка
AGE_ALIGNED_CONTENT = [
    {"age_key": "0+", "age_marking": "0+", "headlines": [
        "Детское питание 0+",
        "Прикорм с 0 месяцев",
        "Питание для детей с рождения",
        "Адаптированное питание 0+",
        "Первый прикорм с рождения",
    ]},
    {"age_key": "4m", "age_marking": "С 4 месяцев", "headlines": [
        "Детское питание с 4 месяцев",
        "Адаптированное питание с 4 месяцев",
        "Прикорм с 4 месяцев",
        "Пюре и каши с 4 месяцев",
        "Первый прикорм с 4 месяцев",
    ]},
    {"age_key": "6m", "age_marking": "С 6 месяцев", "headlines": [
        "Детское питание с 6 месяцев",
        "Натуральное пюре для первого прикорма",
        "Каши для детей с 6 месяцев",
        "Прикорм с 6 месяцев",
        "Пюре и каши с 6 месяцев",
    ]},
    {"age_key": "12m", "age_marking": "С 1 года", "headlines": [
        "Детское питание с 1 года",
        "Для детей с 1 года",
        "Питание с года",
        "Каши и пюре с 1 года",
        "Прикорм для детей с года",
    ]},
    {"age_key": "12m_alt", "age_marking": "Для детей с 1 года", "headlines": [
        "Для детей с 1 года",
        "Детское питание для детей с 1 года",
        "Натуральные каши и пюре с 1 года",
    ]},
    {"age_key": "18m", "age_marking": "С 1.5 лет", "headlines": [
        "Детское питание с 1.5 лет",
        "Для детей с 1.5 лет",
        "Питание с полутора лет",
        "Каши и пюре с 1.5 лет",
    ]},
]

# Для обратной совместимости (--list-headlines и т.п.)
BABY_FOOD_HEADLINES = [h for g in AGE_ALIGNED_CONTENT for h in g["headlines"]]
BABY_FOOD_DESCRIPTIONS = BABY_FOOD_DESCRIPTIONS_NEUTRAL
AGE_MARKING_TEMPLATES = list(dict.fromkeys(g["age_marking"] for g in AGE_ALIGNED_CONTENT))

# Дисклеймеры: обязательно «Молоко матери...» и «Проконсультируйтесь со специалистом»
# Согласованы по возрасту с заголовками и текстом (age_key -> список дисклеймеров)
DISCLAIMERS_BY_AGE = {
    "0+": [
        "0+. Молоко матери — идеальное питание для грудного ребёнка. Необходима консультация специалиста перед вводом продукта.",
        "Для детей с рождения. Молоко матери — идеальное питание для грудного ребёнка. Перед вводом нового продукта проконсультируйтесь со специалистом.",
        "Прикорм с 0 месяцев. Молоко матери — идеальное питание. Перед введением продукта в рацион проконсультируйтесь с врачом.",
        "Грудное вскармливание — лучший выбор для здоровья ребёнка. Продукт предназначен для детей с рождения. Необходима консультация педиатра.",
        "Важно: грудное молоко — оптимальный выбор для питания младенца. Продукт используется по рекомендации специалиста. Требуется консультация врача.",
    ],
    "4m": [
        "С 4 месяцев. Молоко матери — идеальное питание для грудного ребёнка. Перед введением прикорма проконсультируйтесь с педиатром.",
        "Для детей с 4 месяцев. Молоко матери — идеальное питание для грудного ребёнка. Перед вводом нового продукта проконсультируйтесь со специалистом.",
        "С 4 месяцев. Идеальное питание для грудного ребёнка — молоко матери. Перед вводом нового продукта проконсультируйтесь со специалистом.",
        "Грудное вскармливание предпочтительнее. Продукт предназначен для детей с 4 месяцев. Перед применением проконсультируйтесь с врачом.",
        "Важно: грудное молоко — лучший выбор для питания младенца. Продукт подходит для детей с 4 месяцев. Необходима консультация специалиста.",
    ],
    "6m": [
        "С 6 месяцев. Молоко матери — идеальное питание для грудного ребёнка. Перед вводом прикорма необходима консультация специалиста.",
        "Для детей с 6 месяцев. Молоко матери — идеальное питание для грудного ребёнка. Перед вводом нового продукта проконсультируйтесь со специалистом.",
        "Прикорм с 6 месяцев. Молоко матери — идеальное питание. Перед введением продукта в рацион проконсультируйтесь с врачом.",
        "Грудное вскармливание — лучший выбор для здоровья ребёнка. Продукт предназначен для детей с 6 месяцев. Необходима консультация педиатра.",
        "Важно: грудное молоко — оптимальный выбор для питания младенца. Продукт подходит для детей с 6 месяцев. Требуется консультация специалиста.",
        "Продукт не заменяет грудное молоко. Рекомендуется для детей с 6 месяцев. Перед применением проконсультируйтесь с врачом.",
        "Перед введением в рацион проконсультируйтесь с врачом. Для детей старше 6 месяцев.",
    ],
    "12m": [
        "С 1 года. Молоко матери — идеальное питание для грудного ребёнка. Перед вводом продукта проконсультируйтесь со специалистом.",
        "Для детей с 1 года. Молоко матери — идеальное питание для грудного ребёнка. Перед вводом нового продукта проконсультируйтесь со специалистом.",
        "Для детей с 1 года. Грудное молоко — лучшее питание для малыша. Перед вводом продукта необходима консультация педиатра.",
        "Перед введением в рацион проконсультируйтесь с врачом. Для детей старше 1 года.",
        "Грудное вскармливание — лучший выбор для здоровья ребёнка. Продукт предназначен для детей старше 1 года. Необходима консультация педиатра.",
    ],
    "12m_alt": [
        "Для детей с 1 года. Молоко матери — идеальное питание для грудного ребёнка. Перед вводом продукта проконсультируйтесь со специалистом.",
        "Для детей с 1 года. Грудное молоко — лучший выбор для питания малыша. Перед применением продукта необходима консультация врача.",
    ],
    "18m": [
        "С 1.5 лет. Молоко матери — идеальное питание для грудного ребёнка. Перед вводом продукта проконсультируйтесь со специалистом.",
        "Для детей с 1.5 лет. Молоко матери — идеальное питание для грудного ребёнка. Перед вводом нового продукта проконсультируйтесь со специалистом.",
        "Перед введением в рацион проконсультируйтесь с врачом. Для детей старше 1.5 лет.",
    ],
}

# Объединённый список для обратной совместимости
BABY_FOOD_DISCLAIMERS = [d for disclaimers in DISCLAIMERS_BY_AGE.values() for d in disclaimers]

# Производители детского питания (РФ и зарубежные) — для справки и подстановки в шаблоны
BABY_FOOD_BRANDS_RU = [
    "Агуша", "ФрутоНяня", "Бабушкино лукошко", "Тёма", "Истра-Нутриция", "Лебедянский",
    "Флер Альпин", "Fleur Alpine", "Здоровое питание", "Прогресс Капитал", "НоваПродукт АГ",
]
BABY_FOOD_BRANDS_EU = [
    "Gerber", "Nutrilon", "NAN", "Nestlé", "Hipp", "Humana", "Semper", "Fleur Alpine",
    "Danone", "Nutricia", "Kabrita", "Blédina", "MD mil",
]
BABY_FOOD_BRANDS = BABY_FOOD_BRANDS_RU + BABY_FOOD_BRANDS_EU

# Производители из baby_food_companies.json (для дисклеймеров и заголовков по бренду)
BABY_FOOD_COMPANIES_PATH = Path(__file__).parent / "baby_food_companies.json"
try:
    if BABY_FOOD_COMPANIES_PATH.exists():
        with open(BABY_FOOD_COMPANIES_PATH, "r", encoding="utf-8") as _f:
            BABY_FOOD_COMPANIES: Dict[str, Dict[str, Any]] = json.load(_f)
    else:
        BABY_FOOD_COMPANIES = {}
except Exception:
    BABY_FOOD_COMPANIES = {}

# =============================================================================
# Стили фона дисклеймера (пастельные, спокойные)
# =============================================================================
DISCLAIMER_BG_STYLES = [
    # height_multiplier немного уменьшен (~10%), чтобы снизить высоту плашки дисклеймера
    {"name": "pastel_beige", "type": "solid", "alpha": 220, "color": (250, 245, 230), "height_multiplier": 1.08},
    {"name": "soft_cream", "type": "solid", "alpha": 230, "color": (255, 250, 240), "height_multiplier": 1.08},
    {"name": "light_warm", "type": "gradient", "alpha_bottom": 200, "alpha_top": 0, "color": (255, 248, 220), "height_multiplier": 1.35},
    {"name": "pastel_yellow", "type": "solid", "alpha": 210, "color": (255, 253, 231), "height_multiplier": 1.08},
    {"name": "white_soft", "type": "solid", "alpha": 240, "color": (255, 255, 250), "height_multiplier": 1.17},
]

# =============================================================================
# Стили текста (пастельная палитра, читаемость)
# Включаем стили из народной медицины и банкротства + классический синий
# =============================================================================
BABY_FOOD_STYLES = [
    # Мягкие тёплые стили под детское питание
    {"name": "warm_beige", "headline_color": (80, 60, 40), "text_color": (60, 50, 40), "accent_color": (180, 150, 100), "shadow_color": (0, 0, 0), "shadow_opacity": 80},
    {"name": "soft_brown", "headline_color": (70, 55, 45), "text_color": (55, 48, 42), "accent_color": (160, 130, 90), "shadow_color": (20, 15, 10), "shadow_opacity": 100},
    {"name": "pastel_dark", "headline_color": (50, 45, 55), "text_color": (45, 42, 50), "accent_color": (140, 120, 100), "shadow_color": (10, 10, 15), "shadow_opacity": 90},
    {"name": "cream_text", "headline_color": (90, 70, 50), "text_color": (70, 60, 50), "accent_color": (200, 170, 120), "shadow_color": (30, 25, 20), "shadow_opacity": 120},
    # Золотой / белый / кремовый / серебряный / бронзовый — как в народной медицине
    {"name": "gold", "headline_color": (212, 175, 55), "text_color": (255, 250, 240), "accent_color": (255, 215, 0), "shadow_color": (30, 20, 0), "shadow_opacity": 200},
    {"name": "white", "headline_color": (255, 255, 255), "text_color": (245, 245, 245), "accent_color": (220, 220, 220), "shadow_color": (0, 0, 0), "shadow_opacity": 220},
    {"name": "cream", "headline_color": (255, 253, 208), "text_color": (255, 250, 240), "accent_color": (245, 235, 200), "shadow_color": (40, 30, 10), "shadow_opacity": 180},
    {"name": "silver", "headline_color": (192, 192, 210), "text_color": (230, 230, 240), "accent_color": (170, 170, 190), "shadow_color": (20, 20, 40), "shadow_opacity": 200},
    {"name": "bronze", "headline_color": (205, 127, 50), "text_color": (255, 245, 230), "accent_color": (184, 115, 51), "shadow_color": (40, 20, 0), "shadow_opacity": 190},
    # Строгий «navy_gold» как в банкротстве (можно использовать на более деловых макетах)
    {"name": "navy_gold", "headline_color": (212, 175, 55), "text_color": (255, 255, 255), "accent_color": (212, 175, 55), "shadow_color": (0, 0, 30), "shadow_opacity": 200},
    # Классический синий заголовок «в белой окантовке» (используем белую тень как псевдо-обводку)
    {"name": "classic_blue_outline", "headline_color": (20, 60, 140), "text_color": (40, 40, 40), "accent_color": (20, 60, 140), "shadow_color": (255, 255, 255), "shadow_opacity": 230},
]

# Логотипы детского питания (малыши, бренды) для верхнего правого угла
BABY_LOGO_DIR = Path(os.environ.get("GLM_BABY_LOGO_DIR", str(PROJECT_ROOT / "baby_logo")))
BABY_LOGO_DIR_FALLBACK = Path(
    os.environ.get(
        "GLM_DATA_ROOT",
        "/mldata/glm-image-pipeline",
    )
) / "baby_logo"


def _load_baby_logos(logo_height: int, max_count: int = 2, max_width: Optional[int] = None) -> List[Image.Image]:
    """Загружает и масштабирует логотипы из BABY_LOGO_DIR. Подгоняет по высоте и при необходимости по max_width (важно для вертикальных баннеров)."""
    exts = {".png", ".jpg", ".jpeg"}
    logos: List[Image.Image] = []
    logo_dir = BABY_LOGO_DIR if BABY_LOGO_DIR.exists() else BABY_LOGO_DIR_FALLBACK
    if not logo_dir.exists():
        return logos
    paths = [p for p in logo_dir.iterdir() if p.is_file() and p.suffix.lower() in exts]
    random.shuffle(paths)
    for p in paths:
        if p.suffix.lower() != ".png":
            if any(lp.suffix.lower() == ".png" for lp in paths):
                continue
        try:
            im = Image.open(p).convert("RGBA")
            w, h = im.size
            if h <= 0 or w <= 0:
                continue
            scale = logo_height / float(h)
            if max_width is not None and w * scale > max_width:
                scale = min(scale, max_width / float(w))
            nw = max(1, int(w * scale))
            nh = max(1, int(h * scale))
            im = im.resize((nw, nh), Image.LANCZOS)
            logos.append(im)
            if len(logos) >= max_count:
                break
        except Exception:
            continue
    return logos

# =============================================================================
# СЦЕНАРИИ ФОНОВ (по аналогии с ломбардом: объект в углу + градиент / без людей)
# Тема: детское питание — баночки, бутылочки, каши, пюре, продуктовая группа
# =============================================================================

BABY_FOOD_SCENARIOS_NO_PEOPLE = [
    {
        "name": "jar_puree_lower_right_gradient",
        "prompt": "single realistic glass jar of baby fruit puree, in lower right corner of frame, not touching edge, small margin from border, rest of image soft vertical gradient background, pastel beige to white, minimal abstract background, no people, product photography, clean shot, 8k, no text, no distortion",
        "has_person": False,
    },
    {
        "name": "jar_puree_lower_left_gradient",
        "prompt": "one realistic baby food jar with puree, glass packaging, in lower left corner, not at edge, margin from border, rest of frame soft gradient background pastel yellow to cream, minimal abstract, no people, product photography style, sharp details, 8k, no distortion",
        "has_person": False,
    },
    {
        "name": "baby_bottle_lower_right_gradient",
        "prompt": "single realistic baby bottle with nipple, in lower right corner of frame, not touching edge, rest of image soft gradient background white to light beige, minimal abstract, no people, product shot, clean composition, 8k, no text, no distortion",
        "has_person": False,
    },
    {
        "name": "baby_bottle_lower_left_gradient",
        "prompt": "one realistic infant feeding bottle, in lower left corner, not at edge, margin from border, rest of frame soft gradient background cream to white, abstract minimal background, no people, product photography, 8k, no distortion",
        "has_person": False,
    },
    {
        "name": "spoon_jar_lower_corner_gradient",
        "prompt": "baby food glass jar with small spoon, in lower right corner, not touching edge, rest of image soft gradient background pastel beige, minimal abstract, no people, product photography, sharp, 8k, no distortion",
        "has_person": False,
    },
    {
        "name": "cereal_box_lower_corner_gradient",
        "prompt": "one realistic baby cereal or porridge box, in lower left corner, not at edge, rest of frame soft gradient background light yellow to white, minimal abstract, no people, product shot, 8k, no distortion",
        "has_person": False,
    },
    {
        "name": "puree_packs_lower_corner_gradient",
        "prompt": "baby food pouches or small jars, in lower right corner, not at edge, margin from border, rest of image soft gradient background pastel cream, minimal abstract, no people, product photography, 8k, no distortion",
        "has_person": False,
    },
    {
        "name": "fruit_vegetables_puree_gradient",
        "prompt": "fresh fruit and vegetable baby puree in jar, in lower left corner, not touching edge, rest soft gradient background white to soft yellow, minimal abstract, no people, natural lighting, 8k, no distortion",
        "has_person": False,
    },
    {
        "name": "feeding_set_lower_corner_gradient",
        "prompt": "baby feeding set: bowl and soft spoon, in lower right corner, not at edge, rest of frame soft gradient background beige to white, minimal abstract, no people, product shot, 8k, no distortion",
        "has_person": False,
    },
    {
        "name": "baby_food_abstract_gradient",
        "prompt": "baby food product group, jar and spoon, in lower right corner, not at edge, rest 65 percent soft pastel gradient, cream and white, abstract minimal, no people, product photography, 8k, no text",
        "has_person": False,
    },
]

# Детальные сценарии без людей (по описаниям референсных баннеров)
BABY_FOOD_SCENARIOS_DETAILED_NO_PEOPLE = [
    {
        "name": "gerber_style_jar_veggies_center",
        "prompt": "Professional advertising composition, baby vegetable puree in glass jar center frame, jar filled with bright orange puree, bright blue label with baby logo and product name, blue lid slightly angled showing top, ingredients behind and beside jar for depth: whole zucchini left with bright green skin and fresh green leaf tilted behind jar, potato right half tuber with light flesh, two bright orange carrot round slices on top of potato, frontal eye-level food photography, shallow depth of field jar sharp foreground vegetables softly blurred background, pure white minimal background, soft studio lighting, soft blurred shadows under jar and vegetables for volume, no people, 8k, no text",
        "has_person": False,
    },
    {
        "name": "tema_style_products_discount_mobile",
        "prompt": "Baby food promo banner, dairy products left: two plastic cups yogurt or curd with fruit images, two carton packs with straws, brand bear logo top left, central and right elements hung on thin grey strings like mobile: large red star with 30 percent, yellow heart with price, blue clouds with old price and text discounts every day, small hearts and stars on strings, neutral light grey gradient background, friendly child-oriented style, no people, product photography, 8k, no text",
        "has_person": False,
    },
]

# Сценарии с людьми (мама + ребёнок — по гайдлайну приоритет)
BABY_FOOD_SCENARIOS_WITH_PEOPLE = [
    {
        "name": "mom_baby_feeding_right",
        "prompt": "happy young mother feeding cute baby with spoon, baby food jar on table, cozy bright kitchen, soft morning light, pastel beige and white colors, person on right, space for text on left, high quality photography, 8k, no red or bright pink",
        "has_person": True,
        "person_position": "right",
    },
    {
        "name": "mom_baby_feeding_left",
        "prompt": "loving mother with baby, feeding moment, glass jar of puree visible, soft pastel background, warm natural light, person on left, space for text on right, calm happy mood, 8k, professional photo",
        "has_person": True,
        "person_position": "left",
    },
    {
        "name": "parent_baby_kitchen_center",
        "prompt": "happy young mother and father sitting together and feeding their cute baby with a spoon from a glass jar of baby food, all three smiling and looking joyful, bright cozy kitchen interior with white and beige colors, baby food jars and bowls on table, soft natural morning light, realistic high quality photography, family and table in center lower half of frame, large empty space at top for text, 8k, no cartoon, no red or bright pink",
        "has_person": True,
        "person_position": "center"
    },
]

# Детальные сценарии с людьми (по описаниям референсных баннеров)
BABY_FOOD_SCENARIOS_DETAILED_WITH_PEOPLE = [
    {
        "name": "chudo_chado_baby_apple_green",
        "prompt": "Advertising banner baby food, baby right half of frame, fair-skinned infant with bright blue eyes and blond tuft, slight smile looking at camera, white bib with orange trim, holding small orange plastic cup to chin, left lower corner whole bright green apple with one fresh green leaf and half apple cut side toward viewer showing light green flesh, water droplets on apples, bright green gradient background lighter in center behind baby darker at edges, realistic water droplets texture over entire background, frontal eye-level shot, soft even studio light, no harsh shadows, clean bright, 8k, no text",
        "has_person": True,
        "person_position": "right",
    },
    {
        "name": "nutrilon_mom_baby_piano_can",
        "prompt": "Baby formula ad, mother and child right side sitting at white piano, young mother blonde hair smiling at baby in white t-shirt, hand on keys, baby on her lap in white t-shirt reaching finger to piano keys, formula can left foreground bright blue with gold band at base, label Nutrilon 3 and child image, blue lid, number 3 visible, light interior background, light curtains top, white sofa edge left behind can, soft natural window light, slightly raised frontal angle, warm tender atmosphere, 8k, no text",
        "has_person": True,
        "person_position": "right",
    },
    {
        "name": "agusha_mom_baby_products_line",
        "prompt": "Baby food brand banner, mother and baby left, young woman long blonde hair denim shirt holding happy baby in plaid shirt both smiling, product line center and right behind them: cereal box with sleeping baby and stars, orange pouch with apple, doypack with berry puree, bottle with fruit drink, plastic yogurt cup, bright packaging recognizable style, light blue to white gradient background, soft bokeh and water droplets for freshness, slight frontal angle, bright positive summer mood lighting, 8k, no text",
        "has_person": True,
        "person_position": "left",
    },
    {
        "name": "md_baby_spoon_cereals_bows",
        "prompt": "Baby cereal ad, baby top right sitting looking at camera, yellow bib, white baby spoon in hand near mouth, central area rich product line: two large tin cans foreground with gift bows pink and blue ribbons heart-shaped age tags, more tins behind with gold green bows, three small portion sachets bottom right with ribbons, baby bottle with milk and latex nipple left behind cans, blue flower rattle with orange center left lower, soft pink gradient to white bottom, soft shadows under objects, frontal slightly from above, products stepped multi-plane, gift style, 8k, no text",
        "has_person": True,
        "person_position": "right",
    },
    {
        "name": "bledina_child_nature_jar_illustration",
        "prompt": "Split composition baby food ad, left side photo: small toddler in yellow sleeveless dress standing in green meadow with white dandelions, arm stretched toward a tiny yellow bird on fingertip, blurred natural background, soft daylight. Right side: off-white cream panel with soft curved edge, on it a clear packshot arrangement of two or three glass jars of bright orange vegetable puree and one or two baby cereal boxes for infants, cereal boxes showing grains at the bottom and a cute cartoon bear or bunny mascot near the logo, simple carrot and leaf illustrations around, clean commercial style, 8k, no text",
        "has_person": True,
        "person_position": "left",
    },
    {
        "name": "nan_mom_baby_arcs_can",
        "prompt": "Baby formula banner, headline area top, mother and baby center, young woman dark hair dark blue blouse smiling down at infant in arms, baby with light hair smiling at mother in light clothing, three curved glowing bands around them: blue arc Protection plus, yellow arc Bifidobacteria, orange-red arc Smart lipids, formula can bottom right white label blue and gold Nestle NAN Premium number 2, soft blurred light interior background possibly window with curtains, warm light tones blue yellow orange, soft diffused natural light, 8k, no text",
        "has_person": True,
        "person_position": "center",
    },
]

BABY_FOOD_SCENARIOS = (
    BABY_FOOD_SCENARIOS_NO_PEOPLE
    + BABY_FOOD_SCENARIOS_DETAILED_NO_PEOPLE
    + BABY_FOOD_SCENARIOS_WITH_PEOPLE
    + BABY_FOOD_SCENARIOS_DETAILED_WITH_PEOPLE
)


def get_random_disclaimer_bg_style() -> Dict:
    return random.choice(DISCLAIMER_BG_STYLES)


def get_disclaimer_bg_style_by_name(name: str) -> Optional[Dict]:
    for s in DISCLAIMER_BG_STYLES:
        if s.get("name") == name:
            return s
    return DISCLAIMER_BG_STYLES[0]


def get_random_company_with_mark() -> Optional[Dict[str, Any]]:
    """
    Возвращает случайную компанию из baby_food_companies.json
    с одним выбранным торговым названием (mark) для заголовка.
    """
    if not BABY_FOOD_COMPANIES:
        return None
    full_name, data = random.choice(list(BABY_FOOD_COMPANIES.items()))
    marks = data.get("marks") or []
    mark = random.choice(marks) if marks else full_name
    return {
        "mark": mark,
        "full_name": data.get("full_name", full_name),
        "inn": data.get("inn", ""),
        "ogrn": data.get("ogrn", ""),
        "address": data.get("address", ""),
        "phone": data.get("phone", ""),
        "site": data.get("site", ""),
    }


# Шаблоны полного дисклеймера с подстановкой реквизитов компании (для пайплайна с baby_food_companies.json)
FULL_DISCLAIMER_TEMPLATES_WITH_COMPANY = [
    "{age_marking} Молоко матери — идеальное питание для грудного ребёнка. Перед вводом нового продукта в рацион проконсультируйтесь со специалистом. {company_name}, ОГРН {ogrn}, ИНН {inn}, адрес: {address}. {contacts}",
    "Для питания детей {age_marking} в соответствии с законодательством РФ. Идеальной пищей для грудного ребёнка является молоко матери. Продолжайте грудное вскармливание как можно дольше после введения прикорма. Перед вводом продукта проконсультируйтесь со специалистом. Продавец: {company_name}, ОГРН {ogrn}, ИНН {inn}, адрес: {address}. {contacts}",
    "Необходима консультация специалиста. Идеальной пищей для грудного ребенка является молоко матери. Продолжайте грудное вскармливание как можно дольше после введения прикорма. Продукт для детей {age_marking}. {company_name}, ОГРН {ogrn}, ИНН {inn}, юр. адрес: {address}. {contacts}",
    "{age_marking} Молоко матери — идеальное питание для грудного ребёнка. Перед введением прикорма проконсультируйтесь с педиатром. Организатор/продавец: {company_name}, ОГРН {ogrn}, ИНН {inn}, адрес: {address}. {contacts}",
]


def _build_disclaimer_with_company(company_info: Dict[str, Any], age_marking: str) -> str:
    """Собирает полный дисклеймер с реквизитами компании (обязательно: молоко матери, консультация специалиста)."""
    parts = []
    if company_info.get("phone"):
        parts.append(f"Тел.: {company_info['phone']}")
    if company_info.get("site"):
        parts.append(company_info["site"])
    contacts = " ".join(parts) if parts else "Подробности на упаковке."
    template = random.choice(FULL_DISCLAIMER_TEMPLATES_WITH_COMPANY)
    return template.format(
        age_marking=age_marking,
        company_name=company_info.get("full_name", ""),
        inn=company_info.get("inn", ""),
        ogrn=company_info.get("ogrn", ""),
        address=company_info.get("address", ""),
        contacts=contacts,
    )


def _age_marking_to_key(age_marking: str) -> str:
    """Маппинг возрастной маркировки в age_key для выбора дисклеймера."""
    a = (age_marking or "").lower()
    if "0+" in a or "рождени" in a:
        return "0+"
    if "4 месяц" in a:
        return "4m"
    if "6 месяц" in a:
        return "6m"
    if "1 год" in a or "года" in a:
        return "12m"
    if "1.5" in a or "полтора" in a:
        return "18m"
    return "6m"


def get_random_content(
    headline: str = None,
    description: str = None,
    disclaimer: str = None,
    age_marking: str = None,
) -> Dict[str, Any]:
    """
    Возвращает согласованный набор контента для баннера детского питания:
    заголовок, описание и возрастная маркировка содержат один и тот же возраст (0+, с 4 месяцев,
    с 6 месяцев, с 1 года, с 1.5 лет). Дисклеймер согласован с возрастом.
    """
    company_info = get_random_company_with_mark()

    # Выбираем группу: если передан age_marking — ищем подходящую, иначе случайную
    if age_marking:
        target_key = _age_marking_to_key(age_marking)
        candidates = [g for g in AGE_ALIGNED_CONTENT if g["age_key"] == target_key or (target_key == "12m" and g["age_key"] == "12m_alt")]
        group = random.choice(candidates) if candidates else random.choice(AGE_ALIGNED_CONTENT)
        resolved_age = age_marking
    else:
        group = random.choice(AGE_ALIGNED_CONTENT)
        resolved_age = group["age_marking"]

    # Расширяем пул заголовков: возрастные + общие безопасные формулировки
    headline_pool = list(group["headlines"]) + GENERIC_BABY_FOOD_HEADLINES
    base_headline = headline or random.choice(headline_pool)
    base_description = description or random.choice(BABY_FOOD_DESCRIPTIONS_NEUTRAL)
    age_key = group["age_key"]

    if company_info:
        base_headline = f"{company_info['mark']} — {base_headline}"

    if disclaimer is None and company_info:
        disclaimer = _build_disclaimer_with_company(company_info, resolved_age)
    elif disclaimer is None:
        age_disclaimers = DISCLAIMERS_BY_AGE.get(age_key, DISCLAIMERS_BY_AGE.get("6m", BABY_FOOD_DISCLAIMERS))
        disclaimer = random.choice(age_disclaimers)

    content: Dict[str, Any] = {
        "headline": base_headline,
        "description": base_description,
        "disclaimer": disclaimer,
        "age_marking": resolved_age,
    }
    if company_info:
        content["brand_mark"] = company_info["mark"]
        content["company_full_name"] = company_info["full_name"]
        content["company_inn"] = company_info["inn"]
        content["company_ogrn"] = company_info["ogrn"]
        content["company_address"] = company_info["address"]
        content["company_phone"] = company_info["phone"]
        content["company_site"] = company_info["site"]
    return content


def get_layout_for_scenario(scenario: Dict) -> Dict:
    if not scenario.get("has_person"):
        return random.choice(LAYOUTS)
    position = scenario.get("person_position", "center")
    if position == "right":
        return get_layout_by_name("classic_left") or LAYOUTS[0]
    elif position == "left":
        return get_layout_by_name("classic_right") or LAYOUTS[1]
    return random.choice(LAYOUTS)


# =============================================================================
# Baby Food Banner Overlay
# =============================================================================

class BabyFoodBannerOverlay:
    """Наложение текста на баннер детского питания (0–3 года)."""

    REF_WIDTH = 1024
    REF_HEIGHT = 1024

    def __init__(self, layout: Dict = None, style: Dict = None, disclaimer_bg_style: Dict = None, validate: bool = True):
        self.layout = layout or LAYOUTS[0]
        self.style = style or BABY_FOOD_STYLES[0]
        self.disclaimer_bg_style = disclaimer_bg_style or get_random_disclaimer_bg_style()
        self.validate = validate

    def _draw_disclaimer_background(self, image: Image.Image, disc_y: int, bg_style: Dict) -> Image.Image:
        img_width, img_height = image.size
        height_mult = bg_style.get("height_multiplier", 1.0)
        color = bg_style.get("color", (255, 250, 240))
        bg_type = bg_style.get("type", "solid")
        base_height = img_height - disc_y + 10
        actual_height = int(base_height * height_mult)
        adjusted_y = max(0, img_height - actual_height)
        disc_bg = Image.new("RGBA", image.size, (0, 0, 0, 0))
        disc_draw = ImageDraw.Draw(disc_bg)
        if bg_type == "solid":
            alpha = bg_style.get("alpha", 220)
            disc_draw.rectangle([0, adjusted_y, img_width, img_height], fill=(*color, alpha))
        elif bg_type == "gradient":
            alpha_bottom = bg_style.get("alpha_bottom", 200)
            alpha_top = bg_style.get("alpha_top", 0)
            gradient_height = img_height - adjusted_y
            for i in range(gradient_height):
                progress = i / max(1, gradient_height - 1)
                current_alpha = int(alpha_top + (alpha_bottom - alpha_top) * progress)
                y_pos = adjusted_y + i
                disc_draw.line([(0, y_pos), (img_width, y_pos)], fill=(*color, current_alpha))
        return Image.alpha_composite(image, disc_bg)

    def apply(
        self,
        image: Image.Image,
        headline: str = None,
        description: str = None,
        disclaimer: str = None,
        age_marking: str = None,
    ) -> Image.Image:
        content = get_random_content(headline=headline, description=description, disclaimer=disclaimer, age_marking=age_marking)
        headline = headline or content["headline"]
        description = description or content["description"]
        disclaimer = disclaimer or content["disclaimer"]
        age_marking = age_marking or content["age_marking"]

        if self.validate:
            v = BabyFoodValidator.validate(headline, description, disclaimer, age_marking)
            if v["violations"]:
                raise ValueError(f"Нарушение гайдлайна детского питания: {v['violations']}")
            for w in v.get("warnings", []):
                print(f"  ⚠️  {w}")

        # Описание: возрастная маркировка + основной текст
        full_desc = f"{age_marking}\n{description}"

        if image.mode != "RGBA":
            image = image.convert("RGBA")
        img_width, img_height = image.size
        scale = min(img_width, img_height) / self.REF_WIDTH
        # Увеличиваем заголовок и основной текст примерно в 1.5 раза,
        # при этом заголовок делаем на ~10% меньше базового расчёта
        font_sizes = {
            "headline": max(28, int(56 * 1.5 * scale * 0.9)),
            "text": max(14, int(28 * 1.5 * scale)),
            "disclaimer": max(10, int(12 * scale)),
        }
        renderer = TextRenderer(
            self.style,
            headline_size=font_sizes["headline"],
            text_size=font_sizes["text"],
            phone_size=font_sizes["text"],
            disclaimer_size=font_sizes["disclaimer"],
        )
        draw = ImageDraw.Draw(image)
        margin = int(min(img_width, img_height) * 0.06)
        safe_left, safe_top = margin, margin
        safe_bottom = img_height - margin
        max_w = int(img_width * 0.55)

        # Заголовок
        renderer.draw_text_with_shadow(
            draw, (safe_left, safe_top), headline,
            renderer.headline_font, self.style["headline_color"],
            shadow_offset=2, align="left", max_width=max_w, anchor="la",
        )

        # Логотипы в правом верхнем углу: обязательно хотя бы один на любом формате (в т.ч. вертикальном)
        try:
            logo_height = int(font_sizes["headline"] * 3.0)
            logo_spacing = max(4, logo_height // 6)
            # На вертикальных баннерах ширина маленькая — ограничиваем ширину логотипа, чтобы поместился
            logo_zone_left = safe_left + max_w + logo_spacing
            available_logo_width = max(80, img_width - margin - logo_zone_left - margin)
            logos = _load_baby_logos(logo_height, max_count=1, max_width=available_logo_width)
            if logos:
                total_width = sum(im.size[0] for im in logos) + logo_spacing * (len(logos) - 1)
                start_x = max(logo_zone_left, img_width - margin - total_width)
                cursor_x = start_x
                center_y = safe_top + logo_height // 2
                for logo_im in logos:
                    lw, lh = logo_im.size
                    logo_y = center_y - lh // 2
                    if cursor_x + lw > img_width - margin:
                        break
                    image.paste(logo_im, (cursor_x, logo_y), logo_im)
                    cursor_x += lw + logo_spacing
                draw = ImageDraw.Draw(image)
        except Exception:
            pass

        line_y = safe_top + font_sizes["headline"] + int(img_height * 0.012)
        if hasattr(renderer, "draw_decorative_line"):
            renderer.draw_decorative_line(
                draw, (safe_left, line_y),
                min(int(img_width * 0.12), max_w), self.style["accent_color"], thickness=2
            )

        # Описание (возраст + описание) — ниже и с возможностью выравнивания слева/справа
        layout_name = (self.layout or {}).get("name", "")
        desc_align = "left"
        desc_x = safe_left
        if layout_name == "classic_right":
            desc_align = "right"
            desc_x = img_width - margin

        desc_y = int(img_height * 0.52)
        desc_max_w = int(img_width * 0.5)
        desc_height = renderer.draw_text_with_shadow(
            draw, (desc_x, desc_y), full_desc,
            renderer.text_font, self.style["text_color"],
            shadow_offset=1, align=desc_align, max_width=desc_max_w,
            anchor="la" if desc_align == "left" else "ra",
        )
        desc_bottom = desc_y + desc_height

        # Дисклеймер внизу: высота и позиция зависят от длины текста
        approx_lines = max(1, disclaimer.count("\n") + 1)
        base_lines = 2
        extra_lines = max(0, approx_lines - base_lines)
        block_lines = base_lines + extra_lines
        disc_height = font_sizes["disclaimer"] * (block_lines + 2)
        disc_y = safe_bottom - disc_height
        disc_max_w = int(img_width * 0.92)
        image = self._draw_disclaimer_background(image, disc_y, self.disclaimer_bg_style)
        draw = ImageDraw.Draw(image)
        disc_text_y = disc_y + int(font_sizes["disclaimer"] * 0.5)
        disclaimer_color = (50, 45, 40)  # тёмно-бежевый для читаемости на светлом фоне
        # Случайная ориентация текста дисклеймера
        disc_align_choice = random.choice(["left", "right", "center", "justify"])
        if disc_align_choice == "center":
            disc_x = img_width // 2
            anchor = "ma"
            disc_align = "center"
        elif disc_align_choice == "right":
            disc_x = img_width - margin
            anchor = "ra"
            disc_align = "right"
        else:  # left / justify — визуально как левое выравнивание
            disc_x = margin
            anchor = "la"
            disc_align = "left"

        renderer.draw_text_with_shadow(
            draw, (disc_x, disc_text_y), disclaimer,
            renderer.disclaimer_font, disclaimer_color,
            shadow_offset=1, align=disc_align, max_width=disc_max_w, anchor=anchor,
        )

        layout_bounds = {
            "disc_y": disc_y,
            "disc_height": disc_height,
            "desc_y": desc_y,
            "desc_bottom": desc_bottom,
            "desc_align": desc_align,
            "margin": margin,
            "img_width": img_width,
            "img_height": img_height,
        }
        return image, layout_bounds


def find_safe_qr_position_for_baby_food(
    img_width: int,
    img_height: int,
    qr_size: int,
    layout_bounds: Dict[str, Any],
    safety_margin: int = 25,
) -> Optional[Tuple[int, int]]:
    """
    Находит безопасную позицию для QR-кода: не накладывается на дисклеймер,
    описание, заголовок или логотипы.
    QR размещается в нижнем углу, ПРОТИВОПОЛОЖНОМ стороне описания,
    в зоне между нижним краем описания и верхним краем дисклеймера.
    """
    disc_y = layout_bounds["disc_y"]
    desc_bottom = layout_bounds["desc_bottom"]
    desc_align = layout_bounds.get("desc_align", "left")
    margin = layout_bounds.get("margin", int(min(img_width, img_height) * 0.06))

    # QR должен быть НИЖЕ описания и ВЫШЕ дисклеймера
    qr_top_min = desc_bottom + safety_margin
    qr_bottom_max = disc_y - safety_margin

    if qr_top_min + qr_size > qr_bottom_max:
        return None  # Нет места для QR — пропускаем

    qr_y = qr_bottom_max - qr_size
    qr_y = max(qr_top_min, min(qr_y, qr_bottom_max - qr_size))

    # Выбираем угол, противоположный описанию, чтобы не перекрывать текст
    if desc_align == "right":
        qr_x = margin  # Описание справа — QR слева
    else:
        qr_x = img_width - qr_size - margin  # Описание слева — QR справа

    qr_x = max(margin, min(qr_x, img_width - qr_size - margin))
    qr_y = max(margin, min(qr_y, img_height - qr_size - margin))

    return (qr_x, qr_y)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Baby Food Banner Overlay")
    parser.add_argument("--image", type=str, help="Путь к фоновому изображению")
    parser.add_argument("--output", type=str, default="output/baby_food")
    parser.add_argument("--list-headlines", action="store_true")
    parser.add_argument("--validate-text", type=str, help="Проверить текст на соответствие гайдлайну")
    args = parser.parse_args()

    if args.list_headlines:
        print("\n=== Заголовки (детское питание) ===")
        for h in BABY_FOOD_HEADLINES:
            print(f"  • {h}")
        print("\n=== Возрастная маркировка ===")
        for a in AGE_MARKING_TEMPLATES:
            print(f"  • {a}")
        sys.exit(0)

    if args.validate_text:
        v = BabyFoodValidator.check_forbidden(args.validate_text)
        if v:
            print("Нарушения:", v)
        else:
            print("Запрещённых формулировок не найдено.")
        sys.exit(0)

    if args.image:
        from PIL import Image
        img = Image.open(args.image).convert("RGBA")
        overlay = BabyFoodBannerOverlay(validate=True)
        out_img, _ = overlay.apply(img)
        Path(args.output).mkdir(parents=True, exist_ok=True)
        out_path = Path(args.output) / (Path(args.image).stem + "_baby_food.png")
        out_img.save(out_path, quality=95)
        print(f"Сохранено: {out_path}")
    else:
        parser.print_help()
