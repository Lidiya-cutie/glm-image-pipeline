#!/usr/bin/env python3
"""
Folk Medicine Ad Banner Overlay (Народная медицина)

Генерация рекламных баннеров услуг народной медицины
с учётом требований российского законодательства.

ОБЯЗАТЕЛЬНЫЕ ТРЕБОВАНИЯ:
- Дисклеймеры: "ИМЕЮТСЯ ПРОТИВОПОКАЗАНИЯ" и "НЕОБХОДИМА КОНСУЛЬТАЦИЯ СПЕЦИАЛИСТА"
- Чёткая идентификация как народная медицина (не медицинская услуга)

ДОПУСТИМАЯ ТЕРМИНОЛОГИЯ:
- "Нетрадиционная медицина", "Народный целитель", "знахарь", "гадалка"
- "Лечение травами", "энерготерапия", "биоэнергетика", "заговоры"
- "природные", "древние", "ведические", "тибетские", "шаманские" методы
- Экстрасенсы, колдуны, маги, хироманты, спириты, прорицатели, ясновидящие

РАЗГРАНИЧЕНИЕ МАССАЖА:
- "Лечебный массаж поясничной области" — медицинская услуга (не здесь!)
- "Шаманский массаж с раскрытием чакр" — народная медицина (здесь!)

Примеры:
    python scripts/folk_medicine_overlay.py --image bg.png --output output/folk_medicine/
    python scripts/folk_medicine_overlay.py --list-headlines
    python scripts/folk_medicine_overlay.py --list-services
"""

import argparse
import sys
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, List, Optional, Tuple, Any
import random

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.text_overlay import (
    TextRenderer,
    FontManager,
    LAYOUTS,
    TEXT_STYLES,
    get_layout_by_name,
    get_style_by_name,
)


# =============================================================================
# Legal Compliance / Юридическое соответствие
# =============================================================================

# Обязательные дисклеймеры
MANDATORY_DISCLAIMER_1 = "ИМЕЮТСЯ ПРОТИВОПОКАЗАНИЯ"
MANDATORY_DISCLAIMER_2 = "НЕОБХОДИМА КОНСУЛЬТАЦИЯ СПЕЦИАЛИСТА"

# Слова, указывающие на медицинские услуги (НЕ народная медицина!)
MEDICAL_SERVICE_INDICATORS = [
    r"лечебн[ыойаяие]+\s+массаж",
    r"медицинск[ийаяое]+\s+массаж",
    r"врач[еа]?",
    r"клиник[аиу]",
    r"медицинск[ийаяое]+\s+центр",
    r"поликлиник",
    r"больниц",
    r"диагноз",
    r"диагностик",
    r"анализ[ыов]",
    r"рентген",
    r"мрт",
    r"узи",
    r"рецепт\s+врача",
]

# Ключевые слова народной медицины (для валидации)
FOLK_MEDICINE_KEYWORDS = [
    r"народн[ыойаяие]+\s+(медицин|целител|средств)",
    r"нетрадиционн[ыойаяие]+\s+медицин",
    r"целител[ьяией]+",
    r"знахар[ьяией]+",
    r"гадал[коуе]+",
    r"шаман",
    r"экстрасенс",
    r"колдун",
    r"маг[аои]?\b",
    r"ясновид[яеящ]+",
    r"прорицател",
    r"хиромант",
    r"спирит",
    r"оккультист",
    r"биоэнергет",
    r"энерготерап",
    r"чакр[ыау]",
    r"аур[уыа]",
    r"карм[ыуае]",
    r"траво?лечен",
    r"фитотерап",
    r"заговор[ыов]?",
    r"молитв[ыау]",
    r"ведическ",
    r"тибетск",
    r"аюрвед",
    r"натуропат",
    r"рейки",
    r"гомеопат",
]


class FolkMedicineValidator:
    """Валидатор текстов на соответствие законодательству о народной медицине."""
    
    @staticmethod
    def check_medical_indicators(text: str) -> List[str]:
        """
        Проверяет текст на признаки медицинских услуг.
        Народная медицина НЕ должна позиционироваться как медицинские услуги.
        """
        text_lower = text.lower()
        issues = []
        
        for pattern in MEDICAL_SERVICE_INDICATORS:
            if re.search(pattern, text_lower):
                match = re.search(pattern, text_lower)
                issues.append(f"Признак мед. услуги: '{match.group()}' (недопустимо для народной медицины)")
        
        return issues
    
    @staticmethod
    def check_folk_medicine_context(text: str) -> bool:
        """Проверяет наличие контекста народной медицины."""
        text_lower = text.lower()
        
        for pattern in FOLK_MEDICINE_KEYWORDS:
            if re.search(pattern, text_lower):
                return True
        return False
    
    @staticmethod
    def check_disclaimers(text: str) -> Dict[str, bool]:
        """Проверяет наличие обязательных дисклеймеров."""
        text_upper = text.upper()
        
        return {
            "has_contraindications": "ПРОТИВОПОКАЗАНИ" in text_upper,
            "has_consultation": "КОНСУЛЬТАЦИ" in text_upper and "СПЕЦИАЛИСТ" in text_upper,
        }
    
    @staticmethod
    def validate(headline: str, description: str, disclaimer: str) -> Dict[str, Any]:
        """
        Полная валидация всех текстов.
        
        Returns:
            {
                "valid": bool,
                "has_folk_context": bool,
                "medical_issues": [...],
                "disclaimer_check": {...},
                "warnings": [...]
            }
        """
        full_text = f"{headline} {description} {disclaimer}"
        
        medical_issues = FolkMedicineValidator.check_medical_indicators(full_text)
        has_folk_context = FolkMedicineValidator.check_folk_medicine_context(f"{headline} {description}")
        disclaimer_check = FolkMedicineValidator.check_disclaimers(disclaimer)
        
        warnings = []
        
        if not has_folk_context:
            warnings.append("Отсутствует явный контекст народной медицины в тексте")
        
        if not disclaimer_check["has_contraindications"]:
            warnings.append("Отсутствует обязательный дисклеймер 'ИМЕЮТСЯ ПРОТИВОПОКАЗАНИЯ'")
        
        if not disclaimer_check["has_consultation"]:
            warnings.append("Отсутствует обязательный дисклеймер 'НЕОБХОДИМА КОНСУЛЬТАЦИЯ СПЕЦИАЛИСТА'")
        
        valid = (
            len(medical_issues) == 0 and
            disclaimer_check["has_contraindications"] and
            disclaimer_check["has_consultation"]
        )
        
        return {
            "valid": valid,
            "has_folk_context": has_folk_context,
            "medical_issues": medical_issues,
            "disclaimer_check": disclaimer_check,
            "warnings": warnings,
        }


# =============================================================================
# Контент для баннеров (15+ разноплановых текстов)
# =============================================================================

# Заголовки по категориям

# 1. Целители и знахари
HEALER_HEADLINES = [
    "Народный целитель",
    "Потомственный знахарь",
    "Целительство природными силами",
    "Древние методы исцеления",
    "Сеансы народного целителя",
]

# 2. Экстрасенсы и ясновидящие
PSYCHIC_HEADLINES = [
    "Приём экстрасенса",
    "Ясновидящая помощь",
    "Сеансы ясновидения",
    "Экстрасенсорная диагностика",
    "Дар ясновидения",
]

# 3. Гадалки и прорицатели
FORTUNE_TELLER_HEADLINES = [
    "Гадание на картах Таро",
    "Потомственная гадалка",
    "Прорицатель судьбы",
    "Хиромантия — линии судьбы",
    "Предсказание будущего",
]

# 4. Шаманы и духовные практики
SHAMAN_HEADLINES = [
    "Шаманские практики",
    "Сила древних шаманов",
    "Духовное исцеление",
    "Тибетские методы очищения",
    "Ведические ритуалы",
]

# 5. Спиритизм и магия
SPIRIT_HEADLINES = [
    "Спиритический сеанс",
    "Связь с духами предков",
    "Магическая защита",
    "Снятие порчи и сглаза",
    "Очищение кармы",
]

# 6. Траволечение и натуропатия
HERBAL_HEADLINES = [
    "Лечение травами",
    "Фитотерапия по старинным рецептам",
    "Натуропатия и травничество",
    "Сила целебных растений",
    "Травяные сборы для здоровья",
]

# 7. Энергетические практики
ENERGY_HEADLINES = [
    "Биоэнергетический массаж",
    "Энерготерапия и рейки",
    "Работа с чакрами",
    "Раскрытие энергетических каналов",
    "Аюрведический массаж",
]

# 8. Молитвы и заговоры
PRAYER_HEADLINES = [
    "Исцеляющие молитвы",
    "Заговоры на здоровье",
    "Православные обряды исцеления",
    "Молитвенное целительство",
    "Старинные заговоры",
]

# Все заголовки
FOLK_MEDICINE_HEADLINES = (
    HEALER_HEADLINES +
    PSYCHIC_HEADLINES +
    FORTUNE_TELLER_HEADLINES +
    SHAMAN_HEADLINES +
    SPIRIT_HEADLINES +
    HERBAL_HEADLINES +
    ENERGY_HEADLINES +
    PRAYER_HEADLINES
)

# Описания (15+ разноплановых)
FOLK_MEDICINE_DESCRIPTIONS = [
    # Целители
    "Приём ведёт потомственный целитель в 7-м поколении",
    "Индивидуальный подход к каждому посетителю",
    "Древние знания и природные методы",
    "Приём ведёт потомственный целитель в 7-м поколении \nПередача тайных знаний от предков \nПроверенные временем техники диагностики",
    "Проверенные временем техники диагностики \nИсцеление не только тела, но и рода",
    "Индивидуальные обряды для вашего случая \nМудрость, накопленная веками",
    "Индивидуальный подход к каждому посетителю \nДиагностика по уникальным признакам \nПерсональный план восстановления",
    "Учёт вашей истории и особенностей \nАдаптация методов под ваши ритмы \nПостоянная поддержка на пути к здоровью",
    "Древние знания и природные методы \nСимбиоз мудрости Востока и Запада \nСила целительных трав и минералов",
    "Ритуалы, согласованные с циклами природы \nПробуждение внутреннего целителя \nПуть к гармонии через естественные законы",
    
    # Экстрасенсы
    "Диагностика биополя и энергетических блоков",
    "Выявление причин недомоганий на тонком уровне",
    "Работа с аурой и энергетическими центрами",
    "Диагностика биополя и энергетических блоков \nВизуализация разрывов и искажений ауры \nВыявление подсознательных программ",
    "Очистка от энергетических привязок \nВосстановление целостности светового тела \nКарта энергетического здоровья",
    "Выявление причин недомоганий на тонком уровне \nПоиск корня болезни в прошлых событиях \nРабота с кармическими узлами и долгами",
    "Связь физических симптомов с эмоциональными блоками \nДиагностика влияния окружающих людей \nРасшифровка сигналов вашего высшего «Я»",
    "Работа с аурой и энергетическими центрами \nСбалансирование семи основных чакр \nЗарядка и уплотнение энергетической оболочки",
    "Техники цветокоррекции ауры \nОткрытие каналов для потока жизненной силы \nАктивация спящих энергоцентров",
    
    # Гадалки
    "Гадание на Таро, рунах, кофейной гуще",
    "Раскрытие прошлого, настоящего и будущего",
    "Линии судьбы расскажут о вашем пути",
    "Гадание на Таро, рунах, кофейной гуще: \nАрхетипы Таро раскроют сюжет вашей жизни \nДревние символы рун укажут верное направление",
    "Узоры на гуще расскажут о скрытых переменах \nСинтез методов для максимальной точности \nКлючи к пониманию знаков судьбы",
    "Раскрытие прошлого, настоящего и будущего: \nПонять уроки, данные вашими предками \nУвидеть истинные причины текущих ситуаций",
    "Рассмотреть вероятные ветки развития событий \nНайти точки приложения силы для изменений \nСоединить времена в единую линию смысла",
    "Линии судьбы расскажут о вашем пути \nУвидите скрытые возможности \nРаспознаете поворотные точки \nПоймёте язык сердца",
    "Откроете ресурсы для реализации \nОбретёте ясность здесь и сейчас",
    
    # Шаманы
    "Шаманские ритуалы очищения и защиты",
    "Связь с духами природы и предков",
    "Тибетские поющие чаши и благовония",
    "Шаманские ритуалы очищения и защиты \nИзгнание негативных сущностей и влияний \nСоздание сильного личного обережного поля",
    "Очищение дома и пространства от старой энергии \nБлагословение на новые начинания \nСвязь с духом-хранителем для guidance",
    "Связь с духами природы и предков \nПутешествия в нижний и верхний миры за советом \nПолучение силы от тотемных животных",
    "Медитации у священных мест силы \nИспользование голоса (горловое пение) и бубна \nРитуалы благодарения стихий",
    "Тибетские поющие чаши и благовония \nГлубокий массаж звуком на клеточном уровне \nСнятие ментальных и эмоциональных зажимов",
    "Синхронизация биоритмов с вибрациями чаш \nОчищение пространства ароматами смол и трав \nПогружение в состояние медитативного покоя",
    
    # Травы
    "Авторские травяные сборы по старинным рецептам",
    "Только экологически чистые травы из Алтая",
    "Фитотерапия для гармонии тела и духа",
    "Авторские травяные сборы по старинным рецептам \nУникальные комбинации, известные лишь избранным \nСекретные пропорции для усиления эффекта",
    "Сбор в определённые лунные дни и часы \nНастои, отвары, мази и обережные мешочки \nПередача рецепта только доверившемуся",
    "Только экологически чистые травы из Алтая \nСила растений, выросших в местах силы \nРучной сбор с соблюдением древних традиций",
    "Отсутствие промышленного загрязнения и химии \nЭнергетика первозданной природы в каждой травинке \nПодарок от сердца гор и чистых рек",
    "Фитотерапия для гармонии тела и духа: \nТравы для успокоения ума и ясности мысли \nРастения, укрепляющие дух и волю",
    "Сборы для очищения физического и тонкого тел \nЧайные церемонии как медитативная практика \nПуть к целостности через царство растений",
    
    # Энергетика
    "Массаж с раскрытием чакр и меридианов",
    "Восстановление энергетического баланса",
    "Рейки-сеансы для глубокой релаксации",
    "Массаж с раскрытием чакр и меридианов \nРабота с биоактивными точками для запуска энергии \nПроработка энергетических каналов (нади)",
    "Снятие блоков, мешающих свободному течению Ци/Праны \nСочетание тактильного воздействия с визуализацией \nПробуждение Кундалини и чувства внутреннего света",
    "Восстановление энергетического баланса \nВыравнивание переизбытка или недостатка энергии \nГармонизация взаимодействия Инь и Ян",
    "Заземление и наполнение силой Земли и Неба \nТехники для самостоятельного поддержания баланса \nОщущение внутренней целостности и спокойной силы",
    "Рейки-сеансы для глубокой релаксации: \nПередача универсальной жизненной энергии \nИнициация в канал Рейки для самопомощи",
    "Исцеление на расстоянии (дистанционные сеансы) \nРабота с кристаллами и символами для усиления потока \nПутешествие в состояние безмятежности и принятия",
    
    # Общие
    "Предварительная запись обязательна",
    "Опыт практики более 20 лет",
    "Положительные отзывы благодарных посетителей",
]

# Дисклеймеры (ОБЯЗАТЕЛЬНЫЕ)
FOLK_MEDICINE_DISCLAIMERS = [
    "ИМЕЮТСЯ ПРОТИВОПОКАЗАНИЯ. НЕОБХОДИМА КОНСУЛЬТАЦИЯ СПЕЦИАЛИСТА. Не является медицинской услугой.",
    "ИМЕЮТСЯ ПРОТИВОПОКАЗАНИЯ. НЕОБХОДИМА КОНСУЛЬТАЦИЯ СПЕЦИАЛИСТА. Услуги народной медицины.",
    "ВНИМАНИЕ! ИМЕЮТСЯ ПРОТИВОПОКАЗАНИЯ. НЕОБХОДИМА КОНСУЛЬТАЦИЯ СПЕЦИАЛИСТА перед посещением.",
    "ИМЕЮТСЯ ПРОТИВОПОКАЗАНИЯ. НЕОБХОДИМА КОНСУЛЬТАЦИЯ СПЕЦИАЛИСТА. Нетрадиционная медицина.",
    "УСЛУГИ НАРОДНОЙ МЕДИЦИНЫ. ИМЕЮТСЯ ПРОТИВОПОКАЗАНИЯ. НЕОБХОДИМА КОНСУЛЬТАЦИЯ СПЕЦИАЛИСТА.",
]

# =============================================================================
# Сценарии для генерации фонов
# =============================================================================

# Фоны без людей
FOLK_MEDICINE_SCENARIOS_NO_PEOPLE = [
    {
        "name": "herbs_jars",
        "prompt": "vintage apothecary shelf with glass jars full of dried herbs and flowers, natural wood shelves, soft warm lighting, mystical atmosphere, no people, rustic style, 8k quality",
        "has_person": False,
    },
    {
        "name": "thai_massage_room",
        "prompt": "traditional Thai massage room interior, bamboo mats, incense holder, candles, oriental decorations, warm ambient lighting, peaceful atmosphere, no people, 8k quality",
        "has_person": False,
    },
    {
        "name": "incense_altar",
        "prompt": "mystical altar with burning incense sticks, candles, crystals, dried flowers, dark atmospheric background, spiritual setting, warm glow, no people, 8k quality",
        "has_person": False,
    },
    {
        "name": "guru_cabinet",
        "prompt": "spiritual guru meditation room, cushions, mandalas on walls, tibetan singing bowls, prayer beads, warm golden lighting, peaceful atmosphere, no people, 8k quality",
        "has_person": False,
    },
    {
        "name": "folk_pharmacy",
        "prompt": "old folk medicine workshop, mortar and pestle, dried herbs hanging, wooden bowls with powders, vintage bottles, rustic table, warm lighting, no people, 8k quality",
        "has_person": False,
    },
    {
        "name": "spiritism_symbols",
        "prompt": "mystical spiritism setting, ouija board, crystal ball, tarot cards, candles, dark velvet cloth, mysterious atmosphere, soft lighting, no people, 8k quality",
        "has_person": False,
    },
    {
        "name": "forest_herbs",
        "prompt": "enchanted forest clearing with wild medicinal herbs and flowers, morning mist, sunlight rays through trees, magical atmosphere, nature healing, no people, 8k quality",
        "has_person": False,
    },
    {
        "name": "chakra_room",
        "prompt": "meditation room with chakra symbols, colored crystals arranged in pattern, soft ambient lighting, spiritual energy, zen atmosphere, no people, 8k quality",
        "has_person": False,
    },
]

# Фоны с людьми
FOLK_MEDICINE_SCENARIOS_WITH_PEOPLE = [
    {
        "name": "ayurvedist_right",
        "prompt": "ayurvedic practitioner in traditional clothing on right side of image, herbs and oils visible, warm lighting, professional setting, left side empty for text, 8k quality",
        "has_person": True,
        "person_position": "right",
    },
    {
        "name": "spiritual_teacher_left",
        "prompt": "wise spiritual teacher in meditation pose on left side, wearing traditional robes, peaceful expression, candles and incense, right side empty for text, 8k quality",
        "has_person": True,
        "person_position": "left",
    },
    {
        "name": "spiritist_table",
        "prompt": "mysterious spiritist sitting at table with crystal ball and candles, dramatic lighting, mystical atmosphere, face partially visible, space for text on sides, 8k quality",
        "has_person": True,
        "person_position": "center",
    },
    {
        "name": "naturopath_left",
        "prompt": "female naturopath herbalist on left side, surrounded by dried herbs and jars, natural warm lighting, kind expression, right side empty for text, 8k quality",
        "has_person": True,
        "person_position": "left",
    },
    {
        "name": "patient_healer_session",
        "prompt": "patient receiving healing session from folk healer shaman, hands hovering above, energy visualization, soft mystical lighting, peaceful atmosphere, 8k quality",
        "has_person": True,
        "person_position": "center",
    },
    {
        "name": "fortune_teller_left",
        "prompt": "mysterious fortune teller woman on left side with tarot cards, colorful scarves, golden jewelry, candlelit atmosphere, right side empty for text, 8k quality",
        "has_person": True,
        "person_position": "left",
    },
    {
        "name": "sorcerer_right",
        "prompt": "wise old sorcerer mage on right side of image, long beard, mystical staff, ancient books, dark atmospheric setting, left side empty for text, 8k quality",
        "has_person": True,
        "person_position": "right",
    },
]

# Все сценарии
FOLK_MEDICINE_SCENARIOS = FOLK_MEDICINE_SCENARIOS_NO_PEOPLE + FOLK_MEDICINE_SCENARIOS_WITH_PEOPLE

# =============================================================================
# Стили оформления
# =============================================================================

# =============================================================================
# Стили фона для дисклеймера (разные варианты)
# =============================================================================

DISCLAIMER_BG_STYLES = [
    {
        "name": "standard",
        "description": "Стандартный полупрозрачный",
        "type": "solid",
        "alpha": 150,
        "height_multiplier": 1.0,  # обычная высота
        "color": (0, 0, 0),
    },
    {
        "name": "opaque",
        "description": "Непрозрачный чёрный",
        "type": "solid",
        "alpha": 255,
        "height_multiplier": 1.0,
        "color": (0, 0, 0),
    },
    {
        "name": "opaque_dark_blue",
        "description": "Непрозрачный тёмно-синий",
        "type": "solid",
        "alpha": 255,
        "height_multiplier": 1.0,
        "color": (10, 20, 40),
    },
    {
        "name": "semi_transparent",
        "description": "Полупрозрачный средний",
        "type": "solid",
        "alpha": 120,
        "height_multiplier": 1.0,
        "color": (0, 0, 0),
    },
    {
        "name": "sparse",
        "description": "Разряженный (очень прозрачный)",
        "type": "solid",
        "alpha": 70,
        "height_multiplier": 1.0,
        "color": (0, 0, 0),
    },
    {
        "name": "very_sparse",
        "description": "Очень разряженный",
        "type": "solid",
        "alpha": 50,
        "height_multiplier": 1.2,
        "color": (0, 0, 0),
    },
    {
        "name": "compressed",
        "description": "Сжатый (0.7x высота)",
        "type": "solid",
        "alpha": 180,
        "height_multiplier": 0.7,
        "color": (0, 0, 0),
    },
    {
        "name": "compressed_opaque",
        "description": "Сжатый непрозрачный",
        "type": "solid",
        "alpha": 255,
        "height_multiplier": 0.6,
        "color": (0, 0, 0),
    },
    {
        "name": "gradient_top_fade",
        "description": "Градиент с затуханием вверх",
        "type": "gradient",
        "alpha_bottom": 200,
        "alpha_top": 0,
        "height_multiplier": 1.1,
        "color": (0, 0, 0),
    },
    {
        "name": "gradient_tall_fade",
        "description": "Высокий градиент с плавным затуханием",
        "type": "gradient",
        "alpha_bottom": 180,
        "alpha_top": 0,
        "height_multiplier": 0.8,
        "color": (0, 0, 0),
    },
    {
        "name": "gradient_soft",
        "description": "Мягкий градиент",
        "type": "gradient",
        "alpha_bottom": 150,
        "alpha_top": 30,
        "height_multiplier": 1.5,
        "color": (0, 0, 0),
    },
    {
        "name": "gradient_purple",
        "description": "Градиент с фиолетовым оттенком",
        "type": "gradient",
        "alpha_bottom": 180,
        "alpha_top": 0,
        "height_multiplier": 1.4,
        "color": (20, 10, 40),
    },
    {
        "name": "full_width_banner",
        "description": "Баннер на всю ширину (как на примере)",
        "type": "solid",
        "alpha": 230,
        "height_multiplier": 1.2,
        "color": (15, 15, 25),
    },
]


def get_random_disclaimer_bg_style() -> Dict:
    """Возвращает случайный стиль фона для дисклеймера."""
    return random.choice(DISCLAIMER_BG_STYLES)


def get_disclaimer_bg_style_by_name(name: str) -> Optional[Dict]:
    """Возвращает стиль фона для дисклеймера по имени."""
    for style in DISCLAIMER_BG_STYLES:
        if style['name'] == name:
            return style
    return None


# =============================================================================
# Стили оформления текста
# =============================================================================

FOLK_MEDICINE_STYLES = [
    {
        "name": "gold",
        "headline_color": (212, 175, 55),  # Золотой
        "text_color": (255, 250, 240),
        "accent_color": (255, 215, 0),
        "shadow_color": (30, 20, 0),
        "shadow_opacity": 200,
    },
    {
        "name": "white",
        "headline_color": (255, 255, 255),
        "text_color": (245, 245, 245),
        "accent_color": (220, 220, 220),
        "shadow_color": (0, 0, 0),
        "shadow_opacity": 220,
    },
    {
        "name": "cream",
        "headline_color": (255, 253, 208),  # Кремовый
        "text_color": (255, 250, 240),
        "accent_color": (245, 235, 200),
        "shadow_color": (40, 30, 10),
        "shadow_opacity": 180,
    },
    {
        "name": "silver",
        "headline_color": (192, 192, 210),  # Серебряный
        "text_color": (230, 230, 240),
        "accent_color": (170, 170, 190),
        "shadow_color": (20, 20, 40),
        "shadow_opacity": 200,
    },
    {
        "name": "bronze",
        "headline_color": (205, 127, 50),  # Бронзовый
        "text_color": (255, 245, 230),
        "accent_color": (184, 115, 51),
        "shadow_color": (40, 20, 0),
        "shadow_opacity": 190,
    },
    {
        "name": "mystic_purple",
        "headline_color": (200, 160, 255),  # Мистический фиолетовый
        "text_color": (240, 230, 255),
        "accent_color": (180, 140, 230),
        "shadow_color": (20, 10, 40),
        "shadow_opacity": 200,
    },
    {
        "name": "earth_green",
        "headline_color": (144, 190, 109),  # Травяной зелёный
        "text_color": (240, 255, 240),
        "accent_color": (120, 160, 90),
        "shadow_color": (10, 30, 10),
        "shadow_opacity": 180,
    },
]


def get_random_content() -> Dict[str, str]:
    """Возвращает случайный набор контента для баннера."""
    return {
        "headline": random.choice(FOLK_MEDICINE_HEADLINES),
        "description": random.choice(FOLK_MEDICINE_DESCRIPTIONS),
        "disclaimer": random.choice(FOLK_MEDICINE_DISCLAIMERS),
    }


def generate_phone() -> str:
    """Генерирует случайный российский номер телефона."""
    return f"+7 ({random.randint(900, 999)}) {random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(10, 99)}"


def get_layout_for_scenario(scenario: Dict) -> Dict:
    """Подбирает подходящий лейаут для сценария."""
    if not scenario.get("has_person"):
        # Без людей - любой лейаут
        return random.choice(LAYOUTS)
    
    position = scenario.get("person_position", "center")
    
    if position == "right":
        # Человек справа -> текст слева
        return get_layout_by_name("classic_left") or LAYOUTS[0]
    elif position == "left":
        # Человек слева -> текст справа
        return get_layout_by_name("classic_right") or LAYOUTS[1]
    else:
        # Центр -> верх/низ или диагональ
        layouts = [get_layout_by_name("top_bottom"), get_layout_by_name("diagonal")]
        return random.choice([l for l in layouts if l]) or LAYOUTS[0]


# =============================================================================
# Banner Overlay для народной медицины
# =============================================================================

class FolkMedicineBannerOverlay:
    """
    Наложение текста на баннеры о народной медицине.
    С валидацией текстов на соответствие законодательству.
    """
    
    REF_WIDTH = 1024
    REF_HEIGHT = 1024
    
    def __init__(
        self,
        layout: Dict[str, Any] = None,
        style: Dict[str, Any] = None,
        disclaimer_bg_style: Dict[str, Any] = None,
        validate: bool = True,
    ):
        self.layout = layout or LAYOUTS[0]
        self.style = style or FOLK_MEDICINE_STYLES[0]
        self.disclaimer_bg_style = disclaimer_bg_style  # None = случайный выбор
        self.validate = validate
    
    def _draw_disclaimer_background(
        self,
        image: Image.Image,
        disc_y: int,
        bg_style: Dict,
    ) -> Image.Image:
        """
        Рисует фон для дисклеймера с учётом выбранного стиля.
        
        Args:
            image: Исходное изображение
            disc_y: Y-координата начала дисклеймера
            bg_style: Стиль фона из DISCLAIMER_BG_STYLES
            
        Returns:
            Изображение с наложенным фоном
        """
        img_width, img_height = image.size
        
        # Получаем параметры стиля
        height_mult = bg_style.get('height_multiplier', 1.0)
        color = bg_style.get('color', (0, 0, 0))
        bg_type = bg_style.get('type', 'solid')
        
        # Рассчитываем высоту фона
        base_height = img_height - disc_y + 10
        actual_height = int(base_height * height_mult)
        
        # Корректируем Y-координату для вытянутых фонов
        adjusted_y = max(0, img_height - actual_height)
        
        # Создаём слой для фона
        disc_bg = Image.new('RGBA', image.size, (0, 0, 0, 0))
        disc_draw = ImageDraw.Draw(disc_bg)
        
        if bg_type == 'solid':
            # Сплошной фон с заданной прозрачностью
            alpha = bg_style.get('alpha', 150)
            disc_draw.rectangle(
                [0, adjusted_y, img_width, img_height],
                fill=(*color, alpha)
            )
        
        elif bg_type == 'gradient':
            # Градиентный фон
            alpha_bottom = bg_style.get('alpha_bottom', 200)
            alpha_top = bg_style.get('alpha_top', 0)
            
            # Рисуем градиент построчно
            gradient_height = img_height - adjusted_y
            for i in range(gradient_height):
                # Линейная интерполяция альфа-канала
                progress = i / max(1, gradient_height - 1)
                current_alpha = int(alpha_top + (alpha_bottom - alpha_top) * progress)
                y_pos = adjusted_y + i
                disc_draw.line(
                    [(0, y_pos), (img_width, y_pos)],
                    fill=(*color, current_alpha)
                )
        
        # Накладываем фон на изображение
        return Image.alpha_composite(image, disc_bg)
    
    def apply(
        self,
        image: Image.Image,
        headline: str = None,
        description: str = None,
        phone: str = None,
        disclaimer: str = None,
    ) -> Image.Image:
        """
        Применяет текстовый оверлей на изображение.
        
        Если validate=True, проверяет тексты на соответствие закону.
        """
        # Дефолтные значения
        headline = headline or random.choice(FOLK_MEDICINE_HEADLINES)
        description = description or random.choice(FOLK_MEDICINE_DESCRIPTIONS)
        phone = phone or generate_phone()
        disclaimer = disclaimer or random.choice(FOLK_MEDICINE_DISCLAIMERS)
        
        # Валидация
        if self.validate:
            result = FolkMedicineValidator.validate(headline, description, disclaimer)
            
            if result["medical_issues"]:
                print("⚠️  ПРОБЛЕМЫ (признаки мед. услуг):")
                for issue in result["medical_issues"]:
                    print(f"   - {issue}")
                raise ValueError("Текст содержит признаки медицинских услуг!")
            
            if result["warnings"]:
                print("⚠️  ПРЕДУПРЕЖДЕНИЯ:")
                for w in result["warnings"]:
                    print(f"   - {w}")
        
        # Конвертация в RGBA
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        img_width, img_height = image.size
        
        # Размеры шрифтов
        scale = min(img_width, img_height) / self.REF_WIDTH
        font_sizes = {
            "headline": max(28, int(58 * scale)),
            "text": max(16, int(30 * scale)),
            "phone": max(20, int(40 * scale)),
            "disclaimer": max(11, int(13 * scale)),
        }
        
        renderer = TextRenderer(
            self.style,
            headline_size=font_sizes["headline"],
            text_size=font_sizes["text"],
            phone_size=font_sizes["phone"],
            disclaimer_size=font_sizes["disclaimer"],
        )
        
        draw = ImageDraw.Draw(image)
        
        # Границы
        margin = int(min(img_width, img_height) * 0.06)
        safe_left = margin
        safe_right = img_width - margin
        safe_top = margin
        safe_bottom = img_height - margin
        safe_width = safe_right - safe_left
        
        # Определяем позицию текста по лейауту
        layout_name = self.layout.get("name", "classic_left")
        
        if layout_name == "classic_right":
            # Текст справа
            text_x = safe_left + int(safe_width * 0.5)
            max_w = int(safe_width * 0.45)
            align = "left"
        elif layout_name == "center_stack":
            # Текст по центру
            text_x = img_width // 2
            max_w = int(safe_width * 0.7)
            align = "center"
        elif layout_name == "top_bottom":
            # Заголовок сверху, описание снизу
            text_x = img_width // 2
            max_w = int(safe_width * 0.8)
            align = "center"
        elif layout_name == "diagonal":
            # Диагональ - заголовок сверху-слева, описание снизу-справа
            text_x = safe_left
            max_w = int(safe_width * 0.5)
            align = "left"
        else:
            # classic_left (по умолчанию)
            text_x = safe_left
            max_w = int(safe_width * 0.5)
            align = "left"
        
        # ===== HEADLINE =====
        if layout_name == "top_bottom":
            hl_y = safe_top
            hl_anchor = "ma"
        elif layout_name == "diagonal":
            hl_y = safe_top
            hl_anchor = "la"
        else:
            hl_y = safe_top
            hl_anchor = "ma" if align == "center" else "la"
        
        renderer.draw_text_with_shadow(
            draw, (text_x, hl_y), headline,
            renderer.headline_font,
            self.style['headline_color'],
            shadow_offset=3,
            align=align,
            max_width=max_w,
            anchor=hl_anchor,
        )
        
        # Декоративная линия
        line_y = hl_y + font_sizes["headline"] + int(img_height * 0.015)
        if align == "center":
            line_x = img_width // 2 - int(img_width * 0.075)
        else:
            line_x = text_x
        
        renderer.draw_decorative_line(
            draw, (line_x, line_y),
            min(int(img_width * 0.15), max_w),
            self.style['accent_color'],
            thickness=3
        )
        
        # ===== DESCRIPTION =====
        # Определяем параметры для описания (включая max_w для всех лейаутов)
        if layout_name == "top_bottom":
            desc_y = int(img_height * 0.45)
            desc_x = img_width // 2
            desc_anchor = "ma"
            desc_max_w = int(safe_width * 0.8)  # Определяем max_w для top_bottom
        elif layout_name == "diagonal":
            desc_y = int(img_height * 0.55)
            desc_x = safe_right - int(safe_width * 0.02)
            desc_anchor = "ra"
            desc_max_w = int(safe_width * 0.45)
            align = "right"
        else:
            desc_y = int(img_height * 0.38)
            desc_x = text_x
            desc_anchor = "ma" if align == "center" else "la"
            desc_max_w = max_w  # Используем уже определённый max_w
        
        # Вычисляем высоту описания ДО отрисовки для принятия решения о позиции телефона
        # Разбиваем текст по \n и применяем wrap
        desc_lines_temp = description.split('\n')
        wrapped_lines = []
        for line in desc_lines_temp:
            if line.strip():
                # Применяем wrap к каждой строке
                words = line.strip().split()
                current_line = []
                for word in words:
                    test_line = " ".join(current_line + [word])
                    bbox = renderer.text_font.getbbox(test_line)
                    width = bbox[2] - bbox[0]
                    if width <= desc_max_w:
                        current_line.append(word)
                    else:
                        if current_line:
                            wrapped_lines.append(" ".join(current_line))
                        current_line = [word]
                if current_line:
                    wrapped_lines.append(" ".join(current_line))
            else:
                wrapped_lines.append("")  # Пустая строка для отступа
        
        # Вычисляем высоту описания
        line_spacing = 1.2
        desc_height = int(len(wrapped_lines) * font_sizes["text"] * line_spacing)
        
        # Рисуем описание
        renderer.draw_text_with_shadow(
            draw, (desc_x, desc_y), description,
            renderer.text_font,
            self.style['text_color'],
            shadow_offset=2,
            align=align,
            max_width=desc_max_w,
            anchor=desc_anchor,
        )
        
        # ===== PHONE =====
        # Определяем, нужно ли переместить телефон на противоположную сторону
        # Порог: если описание занимает больше 40% высоты изображения, разводим по сторонам
        desc_height_percent = (desc_height / img_height) * 100
        phone_spacing = max(font_sizes["phone"], int(font_sizes["text"] * 1.5))
        
        # Флаг: нужно ли переместить телефон на противоположную сторону
        move_phone_opposite = desc_height_percent > 40  # Порог 40% высоты изображения
        
        if layout_name == "top_bottom":
            # Для top_bottom размещаем телефон ниже или сбоку
            ph_y = desc_y + desc_height + phone_spacing
            ph_y = min(ph_y, int(img_height * 0.70))
            
            if move_phone_opposite:
                # Перемещаем телефон в правый верхний угол
                ph_x = safe_right - int(safe_width * 0.05)
                ph_y = safe_top + int(img_height * 0.05)
                ph_anchor = "ra"
                ph_align = "right"
            else:
                ph_x = img_width // 2
                ph_anchor = "ma"
                ph_align = "center"
        
        elif layout_name == "diagonal":
            # Для diagonal уже разнесены, но проверяем перекрытие
            ph_y = desc_y + desc_height + phone_spacing
            ph_y = min(ph_y, int(img_height * 0.75))
            ph_x = safe_right - int(safe_width * 0.02)
            ph_anchor = "ra"
            ph_align = "right"
        
        elif layout_name == "center_stack":
            # Для center_stack перемещаем телефон в сторону если текст длинный
            ph_y = desc_y + desc_height + phone_spacing
            ph_y = min(ph_y, int(img_height * 0.70))
            
            if move_phone_opposite:
                # Перемещаем телефон в правый верхний угол
                ph_x = safe_right - int(safe_width * 0.05)
                ph_y = safe_top + int(img_height * 0.05)
                ph_anchor = "ra"
                ph_align = "right"
            else:
                ph_x = img_width // 2
                ph_anchor = "ma"
                ph_align = "center"
        
        elif layout_name == "classic_right":
            # Текст справа - телефон слева если текст длинный
            ph_y = desc_y + desc_height + phone_spacing
            ph_y = min(ph_y, int(img_height * 0.70))
            
            if move_phone_opposite:
                # Перемещаем телефон налево
                ph_x = safe_left
                ph_y = desc_y  # На уровне начала описания
                ph_anchor = "la"
                ph_align = "left"
            else:
                ph_x = text_x  # Остаётся справа
                ph_anchor = "la"
                ph_align = "left"
        
        else:  # classic_left (по умолчанию)
            # Текст слева - телефон справа если текст длинный
            ph_y = desc_y + desc_height + phone_spacing
            ph_y = min(ph_y, int(img_height * 0.70))
            
            if move_phone_opposite:
                # Перемещаем телефон направо
                ph_x = safe_right - int(safe_width * 0.05)
                ph_y = desc_y  # На уровне начала описания
                ph_anchor = "ra"
                ph_align = "right"
            else:
                ph_x = text_x  # Остаётся слева
                ph_anchor = "la"
                ph_align = "left"
        
        renderer.draw_text_with_shadow(
            draw, (ph_x, ph_y), phone,
            renderer.phone_font,
            self.style['headline_color'],
            shadow_offset=2,
            align=ph_align,
            anchor=ph_anchor,
        )
        
        # ===== DISCLAIMER (обязательные предупреждения) =====
        disc_y = safe_bottom - font_sizes["disclaimer"] * 4
        disc_max_w = int(img_width * 0.92)
        
        # Выбираем стиль фона для дисклеймера (случайный или заданный)
        bg_style = self.disclaimer_bg_style or get_random_disclaimer_bg_style()
        
        # Применяем фон с выбранным стилем
        image = self._draw_disclaimer_background(image, disc_y, bg_style)
        draw = ImageDraw.Draw(image)
        
        # Для вытянутых фонов можем сдвинуть текст выше для лучшего размещения
        height_mult = bg_style.get('height_multiplier', 1.0)
        if height_mult >= 2.0:
            # Для высоких фонов центрируем текст в нижней трети
            disc_text_y = int(img_height - (img_height - disc_y + 10) * 0.35)
        else:
            disc_text_y = disc_y
        
        renderer.draw_text_with_shadow(
            draw, (img_width // 2, disc_text_y), disclaimer,
            renderer.disclaimer_font,
            (255, 255, 255),
            shadow_offset=1,
            align="center",
            max_width=disc_max_w,
            anchor="ma",
        )
        
        return image


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Генератор баннеров о народной медицине (с проверкой законодательства)"
    )
    
    # Input
    parser.add_argument("--image", type=str, help="Путь к изображению-фону")
    parser.add_argument("--input-dir", type=str, help="Папка с изображениями")
    
    # Output
    parser.add_argument("--output", type=str, default="output/folk_medicine",
                        help="Путь для сохранения")
    
    # Текст
    parser.add_argument("--headline", type=str, help="Заголовок")
    parser.add_argument("--description", type=str, help="Описание")
    parser.add_argument("--phone", type=str, help="Телефон")
    parser.add_argument("--disclaimer", type=str, help="Дисклеймер")
    
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
    
    # Валидация
    parser.add_argument("--no-validate", action="store_true",
                        help="Отключить проверку на соответствие закону")
    parser.add_argument("--validate-text", type=str,
                        help="Проверить текст")
    
    # Утилиты
    parser.add_argument("--list-headlines", action="store_true",
                        help="Показать доступные заголовки")
    parser.add_argument("--list-descriptions", action="store_true",
                        help="Показать доступные описания")
    parser.add_argument("--list-services", action="store_true",
                        help="Показать категории услуг")
    parser.add_argument("--list-scenarios", action="store_true",
                        help="Показать сценарии фонов")
    parser.add_argument("--list-styles", action="store_true",
                        help="Показать стили оформления текста")
    parser.add_argument("--list-disclaimer-styles", action="store_true",
                        help="Показать стили фона дисклеймера")
    
    args = parser.parse_args()
    
    # Утилиты
    if args.validate_text:
        issues = FolkMedicineValidator.check_medical_indicators(args.validate_text)
        has_context = FolkMedicineValidator.check_folk_medicine_context(args.validate_text)
        
        print(f"\nПроверка: \"{args.validate_text}\"")
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
    
    if args.list_headlines:
        print("\n=== Заголовки по категориям ===")
        categories = [
            ("Целители и знахари", HEALER_HEADLINES),
            ("Экстрасенсы и ясновидящие", PSYCHIC_HEADLINES),
            ("Гадалки и прорицатели", FORTUNE_TELLER_HEADLINES),
            ("Шаманы и духовные практики", SHAMAN_HEADLINES),
            ("Спиритизм и магия", SPIRIT_HEADLINES),
            ("Траволечение и натуропатия", HERBAL_HEADLINES),
            ("Энергетические практики", ENERGY_HEADLINES),
            ("Молитвы и заговоры", PRAYER_HEADLINES),
        ]
        for cat_name, headlines in categories:
            print(f"\n[{cat_name}]:")
            for h in headlines:
                print(f"  • {h}")
        return
    
    if args.list_descriptions:
        print("\n=== Описания ===")
        for d in FOLK_MEDICINE_DESCRIPTIONS:
            print(f"  • {d}")
        return
    
    if args.list_services:
        print("""
╔══════════════════════════════════════════════════════════════════╗
║           КАТЕГОРИИ УСЛУГ НАРОДНОЙ МЕДИЦИНЫ                      ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  🌿 ЦЕЛИТЕЛИ И ЗНАХАРИ                                           ║
║     Народный целитель, потомственный знахарь,                    ║
║     целительство природными силами                               ║
║                                                                  ║
║  🔮 ЭКСТРАСЕНСЫ И ЯСНОВИДЯЩИЕ                                    ║
║     Экстрасенсорная диагностика, работа с биополем,              ║
║     ясновидение, дар предвидения                                 ║
║                                                                  ║
║  🃏 ГАДАЛКИ И ПРОРИЦАТЕЛИ                                        ║
║     Таро, руны, хиромантия, кофейная гуща,                       ║
║     предсказание судьбы                                          ║
║                                                                  ║
║  🌀 ШАМАНЫ И ДУХОВНЫЕ ПРАКТИКИ                                   ║
║     Шаманские ритуалы, тибетские методы,                         ║
║     ведические практики, духовное очищение                       ║
║                                                                  ║
║  ✨ СПИРИТИЗМ И МАГИЯ                                            ║
║     Спиритические сеансы, связь с духами,                        ║
║     снятие порчи, очищение кармы                                 ║
║                                                                  ║
║  🌱 ТРАВОЛЕЧЕНИЕ И НАТУРОПАТИЯ                                   ║
║     Фитотерапия, травяные сборы, природные                       ║
║     средства, старинные рецепты                                  ║
║                                                                  ║
║  ⚡ ЭНЕРГЕТИЧЕСКИЕ ПРАКТИКИ                                      ║
║     Рейки, работа с чакрами, биоэнергетика,                      ║
║     аюрведический массаж                                         ║
║                                                                  ║
║  🙏 МОЛИТВЫ И ЗАГОВОРЫ                                           ║
║     Исцеляющие молитвы, старинные заговоры,                      ║
║     православные обряды исцеления                                ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
        """)
        return
    
    if args.list_scenarios:
        print("\n=== Сценарии фонов ===")
        print("\n[Без людей]:")
        for s in FOLK_MEDICINE_SCENARIOS_NO_PEOPLE:
            print(f"  • {s['name']}")
            print(f"    {s['prompt'][:60]}...")
        print("\n[С людьми]:")
        for s in FOLK_MEDICINE_SCENARIOS_WITH_PEOPLE:
            pos = s.get('person_position', 'center')
            print(f"  • {s['name']} (человек {pos})")
            print(f"    {s['prompt'][:60]}...")
        return
    
    if args.list_styles:
        print("\n=== Стили оформления текста ===")
        for s in FOLK_MEDICINE_STYLES:
            r, g, b = s['headline_color']
            print(f"  • {s['name']}: RGB({r}, {g}, {b})")
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
    
    # Проверка входных данных
    if not args.image and not args.input_dir:
        parser.error("Укажите --image или --input-dir")
    
    # Получаем стиль текста
    style = None
    if args.style:
        for s in FOLK_MEDICINE_STYLES:
            if s['name'] == args.style:
                style = s
                break
    
    # Получаем стиль фона дисклеймера
    disclaimer_bg_style = None
    if args.disclaimer_bg_style:
        disclaimer_bg_style = get_disclaimer_bg_style_by_name(args.disclaimer_bg_style)
    
    layout = get_layout_by_name(args.layout) if args.layout else LAYOUTS[0]
    
    # Создаём оверлей
    overlay = FolkMedicineBannerOverlay(
        layout=layout,
        style=style,
        disclaimer_bg_style=disclaimer_bg_style,
        validate=not args.no_validate,
    )
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if args.image:
        # Один файл
        image_path = Path(args.image)
        image = Image.open(image_path)
        
        result = overlay.apply(
            image,
            headline=args.headline,
            description=args.description,
            phone=args.phone,
            disclaimer=args.disclaimer,
        )
        
        output_path = output_dir / f"{image_path.stem}_folk_medicine.png"
        result.save(output_path, quality=95)
        print(f"✅ Создано: {output_path}")
        
    elif args.input_dir:
        # Batch
        input_dir = Path(args.input_dir)
        images = list(input_dir.glob("*.png")) + list(input_dir.glob("*.jpg"))
        
        for img_path in images:
            print(f"\nОбработка: {img_path.name}")
            image = Image.open(img_path)
            
            try:
                result = overlay.apply(image)
                output_path = output_dir / f"{img_path.stem}_folk_medicine.png"
                result.save(output_path, quality=95)
                print(f"✅ Создано: {output_path}")
            except ValueError as e:
                print(f"❌ Пропущено: {e}")
        
        print(f"\n✅ Готово! Результаты в: {output_dir}")


if __name__ == "__main__":
    main()
