#!/usr/bin/env python3
"""
Bankruptcy Ad Banner Generator (Банкротство физлиц)

Генерация рекламных баннеров о банкротстве физических лиц
с учётом требований российского законодательства (38-ФЗ).

ОБЯЗАТЕЛЬНЫЕ ТРЕБОВАНИЯ:
- Слово "банкротство" или "банкротство физлиц" в явном виде
- С 01.09.2025: предупредительная надпись
- С 01.01.2026: предупреждение о негативных последствиях + льготные варианты

ЗАПРЕЩЕНО (проверяется валидатором):
- "спишем долги", "списание долгов", "избавим от долгов"
- "гарантированно", "100%", "навсегда"
- Обещания освобождения от долгов
- Банкротство юрлиц (только физлица!)

Примеры:
    python scripts/bankruptcy_overlay.py --image bg.png --output output/bankruptcy/
    python scripts/bankruptcy_overlay.py --list-headlines
    python scripts/bankruptcy_overlay.py --validate-text "Спишем ваши долги"
"""

import argparse
import sys
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, List, Optional, Tuple, Any
import random
from datetime import date

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

# ЗАПРЕЩЁННЫЕ формулировки (ст. 5 38-ФЗ и специфика банкротства)
FORBIDDEN_PHRASES = [
    # Обещания списания долгов
    r"спиш[е|у|ем|ите]м?\s+долг",
    r"списани[ея]\s+долг",
    r"избав[ия]м?\s+(вас\s+)?от\s+долг",
    r"реш[иу]м?\s+проблем[у|ы]\s+с\s+долг",
    r"законно[ое]?\s+списани[ея]",
    r"через\s+суд",
    r"без\s+суда",
    r"поможем\s+закрыть\s+долг",
    r"закро[ей]м?\s+долг",
    r"уберём?\s+долг",
    r"погас[ия]м?\s+долг",
    
    # Гарантии
    r"гарантир[у|о]",
    r"100\s*%",
    r"сто\s+процентов",
    r"навсегда",
    r"полностью\s+освобод",
    r"точно\s+спиш",
    r"обязательно\s+спиш",
    
    # Призывы не платить
    r"не\s+плат[ия]",
    r"прекрат[ия]те?\s+плат",
    r"перестан[ья]те?\s+плат",
    r"можно\s+не\s+плат",
    
    # Ложные утверждения о государстве
    r"государств[ао]\s+создал[оа]",
    r"государств[ао]\s+позволя",
    r"по\s+закону\s+можно\s+не\s+плат",
    
    # Юрлица (запрещено - только физлица)
    r"банкротств[оа]\s+компан",
    r"банкротств[оа]\s+бизнес",
    r"банкротств[оа]\s+юр[ия]дическ",
    r"банкротств[оа]\s+ооо",
    r"банкротств[оа]\s+предприят",
    r"ликвидаци[яи]\s+фирм",
]

# Обязательные элементы
REQUIRED_KEYWORD = r"банкротств[оа]"  # Должно быть слово "банкротство"


class TextValidator:
    """Валидатор текстов на соответствие законодательству."""
    
    @staticmethod
    def check_forbidden(text: str) -> List[str]:
        """
        Проверяет текст на запрещённые формулировки.
        Возвращает список найденных нарушений.
        """
        text_lower = text.lower()
        violations = []
        
        for pattern in FORBIDDEN_PHRASES:
            if re.search(pattern, text_lower):
                match = re.search(pattern, text_lower)
                violations.append(f"Запрещено: '{match.group()}' (паттерн: {pattern})")
        
        return violations
    
    @staticmethod
    def check_required(text: str) -> bool:
        """Проверяет наличие обязательного слова 'банкротство'."""
        return bool(re.search(REQUIRED_KEYWORD, text.lower()))
    
    @staticmethod
    def validate(headline: str, description: str, disclaimer: str) -> Dict[str, Any]:
        """
        Полная валидация всех текстов.
        
        Returns:
            {
                "valid": bool,
                "has_required_keyword": bool,
                "violations": [...],
                "warnings": [...]
            }
        """
        full_text = f"{headline} {description} {disclaimer}"
        
        violations = TextValidator.check_forbidden(full_text)
        has_keyword = TextValidator.check_required(full_text)
        
        warnings = []
        if not has_keyword:
            warnings.append("Отсутствует обязательное слово 'банкротство'")
        
        # Проверка даты для обязательных предупреждений
        today = date.today()
        if today >= date(2025, 9, 1):
            # С 01.09.2025 нужна предупредительная надпись
            if "предупрежд" not in disclaimer.lower() and "внимание" not in disclaimer.lower():
                warnings.append("С 01.09.2025 требуется предупредительная надпись")
        
        if today >= date(2026, 1, 1):
            # С 01.01.2026 нужно предупреждение о последствиях и льготах
            has_consequences = any(w in disclaimer.lower() for w in ["последств", "риск", "ограничен"])
            has_free_options = any(w in disclaimer.lower() for w in ["бесплатн", "льгот", "мфц"])
            
            if not has_consequences:
                warnings.append("С 01.01.2026 требуется предупреждение о негативных последствиях")
            if not has_free_options:
                warnings.append("С 01.01.2026 требуется информация о льготных/бесплатных вариантах")
        
        return {
            "valid": len(violations) == 0 and has_keyword,
            "has_required_keyword": has_keyword,
            "violations": violations,
            "warnings": warnings,
        }


# =============================================================================
# Контент для баннеров (законопослушный)
# =============================================================================

# Заголовки (ОБЯЗАТЕЛЬНО содержат "банкротство") — 20 вариантов
BANKRUPTCY_HEADLINES = [
    # Базовые формулировки
    "Банкротство физических лиц",
    "Банкротство граждан",
    "Процедура банкротства",
    "Банкротство: консультация",
    "Услуги по банкротству",
    "Банкротство физлиц",
    # Юридическая помощь
    "Юридическая помощь: банкротство",
    "Сопровождение банкротства",
    "Банкротство: правовая помощь",
    "Консультация по банкротству",
    "Банкротство под ключ",
    "Помощь в банкротстве",
    # Профессиональные формулировки
    "Банкротство: защита интересов",
    "Ведение дел о банкротстве",
    "Банкротство с юристом",
    "Арбитражное банкротство",
    "Банкротство: первый шаг",
    "Судебное банкротство физлиц",
    "Банкротство: анализ ситуации",
    "Внесудебное банкротство",
]

# Описания (БЕЗ обещаний списания) — 20 вариантов
BANKRUPTCY_DESCRIPTIONS = [
    # Консультации
    "Консультация юриста бесплатно",
    "Анализ вашей ситуации",
    "Первая консультация бесплатно",
    "Бесплатная оценка перспектив",
    "Консультация арбитражного управляющего",
    # Услуги
    "Подготовка документов",
    "Сопровождение процедуры",
    "Представительство в суде",
    "Полное юридическое сопровождение",
    "Защита ваших интересов в суде",
    # Опыт и подход
    "Опыт работы более 10 лет",
    "Индивидуальный подход",
    "Работаем по всей России",
    "Более 500 успешных дел",
    "Команда профессионалов",
    # Условия
    "Рассрочка оплаты услуг",
    "Фиксированная стоимость услуг",
    "Прозрачные условия работы",
    "Оплата по этапам",
    "Договор и гарантии качества",
]

# =============================================================================
# СТРУКТУРИРОВАННЫЕ ТЕКСТЫ С МАРКИРОВАННЫМИ СПИСКАМИ
# =============================================================================

# Маркированные списки услуг (для правой/левой части баннера)
BULLET_LISTS = [
    # Список 1 - Консультации
    {
        "title": "Консультация по вопросам:",
        "items": [
            "затруднения самостоятельного обслуживания кредитов",
            "представление интересов в общении с кредиторами",
            "полное сопровождение процедуры банкротства",
        ],
        "position": "right",
    },
    # Список 2 - Услуги юриста
    {
        "title": "Услуги юриста:",
        "items": [
            "анализ финансовой ситуации",
            "подготовка документов для суда",
            "представительство в арбитражном суде",
            "работа с арбитражным управляющим",
        ],
        "position": "right",
    },
    # Список 3 - Этапы работы
    {
        "title": "Этапы работы:",
        "items": [
            "бесплатная консультация юриста",
            "сбор и подготовка документов",
            "подача заявления в суд",
            "сопровождение процедуры",
        ],
        "position": "right",
    },
    # Список 4 - Преимущества
    {
        "title": "Наши преимущества:",
        "items": [
            "юридическая практика более 10 лет",
            "опыт в более чем 100 банках",
            "индивидуальный подход к каждому",
            "прозрачные условия работы",
        ],
        "position": "right",
    },
    # Список 5 - Что включено
    {
        "title": "Что входит в услугу:",
        "items": [
            "анализ долговой нагрузки",
            "консультация арбитражного управляющего",
            "подготовка всех документов",
            "юридическое сопровождение",
        ],
        "position": "right",
    },
    # Список 6 - Помощь
    {
        "title": "Мы поможем:",
        "items": [
            "разобраться в процедуре банкротства",
            "подготовить необходимые документы",
            "пройти процедуру с минимальными рисками",
        ],
        "position": "left",
    },
    # Список 7 - Для кого
    {
        "title": "Обратитесь к нам, если:",
        "items": [
            "долги превышают 500 000 рублей",
            "нет возможности платить по кредитам",
            "звонят коллекторы и кредиторы",
        ],
        "position": "left",
    },
    # Список 8 - Гарантии качества
    {
        "title": "Гарантии качества:",
        "items": [
            "договор и акты выполненных работ",
            "фиксированная стоимость услуг",
            "рассрочка оплаты без процентов",
        ],
        "position": "right",
    },
    # Список 9 - Документы
    {
        "title": "Подготовим документы:",
        "items": [
            "заявление о признании банкротом",
            "опись имущества и обязательств",
            "справки о доходах и задолженности",
        ],
        "position": "right",
    },
    # Список 10 - Работа с кредиторами
    {
        "title": "Работа с кредиторами:",
        "items": [
            "представление ваших интересов",
            "переговоры о реструктуризации",
            "защита от коллекторов",
        ],
        "position": "right",
    },
]

# Расширенные заголовки с подзаголовками
EXTENDED_HEADLINES = [
    {
        "main": "БАНКРОТСТВО\nФИЗИЧЕСКИХ ЛИЦ",
        "sub": "С ГАРАНТИЕЙ КАЧЕСТВА!",
        "position": "left",
    },
    {
        "main": "БАНКРОТСТВО\nГРАЖДАН",
        "sub": "Профессиональная помощь юриста",
        "position": "left",
    },
    {
        "main": "ПРОЦЕДУРА\nБАНКРОТСТВА",
        "sub": "Консультация бесплатно",
        "position": "left",
    },
    {
        "main": "БАНКРОТСТВО\nФИЗЛИЦ",
        "sub": "Полное юридическое сопровождение",
        "position": "left",
    },
    {
        "main": "ЮРИДИЧЕСКАЯ ПОМОЩЬ\nПО БАНКРОТСТВУ",
        "sub": "Опыт работы более 10 лет",
        "position": "left",
    },
    {
        "main": "БАНКРОТСТВО",
        "sub": "В Москве и по всей России!",
        "position": "left",
    },
    {
        "main": "УСЛУГИ ПО\nБАНКРОТСТВУ",
        "sub": "Первый шаг к финансовой свободе",
        "position": "left",
    },
    {
        "main": "БАНКРОТСТВО\nПОД КЛЮЧ",
        "sub": "От консультации до завершения",
        "position": "left",
    },
    {
        "main": "СОПРОВОЖДЕНИЕ\nБАНКРОТСТВА",
        "sub": "Индивидуальный подход",
        "position": "left",
    },
    {
        "main": "БАНКРОТСТВО\nФИЗИЧЕСКИХ ЛИЦ",
        "sub": "Работаем по всей России",
        "position": "left",
    },
]

# Призывы к действию (CTA)
CTA_BUTTONS = [
    "Бесплатная консультация",
    "Записаться на консультацию",
    "Получить консультацию",
    "Узнать подробнее",
    "Оставить заявку",
    "Позвонить юристу",
    "Заказать звонок",
    "Начать процедуру",
]

# Дополнительные информационные блоки
INFO_BLOCKS = [
    {
        "text": "юридическая практика\nпо снижению кредитных\nплатежей в более чем\nв 100 банках",
        "position": "bottom_right",
    },
    {
        "text": "более 500\nуспешных дел\nпо банкротству",
        "position": "bottom_right",
    },
    {
        "text": "работаем\nпо всей России\nдистанционно",
        "position": "bottom_right",
    },
    {
        "text": "рассрочка\nоплаты услуг\nбез процентов",
        "position": "bottom_right",
    },
    {
        "text": "фиксированная\nстоимость\nбез скрытых платежей",
        "position": "bottom_right",
    },
]

# Структурированные блоки контента (комплексные)
STRUCTURED_CONTENT = [
    # Блок 1 - Классический с правым списком
    {
        "headline": {
            "main": "БАНКРОТСТВО\nФИЗИЧЕСКИХ ЛИЦ",
            "sub": "С ГАРАНТИЕЙ КАЧЕСТВА!",
        },
        "left_block": {
            "location": "В Москве\nи по всей России!",
            "cta": "Бесплатная консультация",
        },
        "right_list": {
            "items": [
                "Консультация по вопросам затруднения\nсамостоятельного обслуживания кредитов",
                "Представление Ваших интересов\nв общении с кредиторами и коллекторами",
                "Полное сопровождение процедуры\nбанкротства физических лиц",
            ],
            "numbered": True,
        },
        "info_block": "юридическая практика\nпо снижению кредитных\nплатежей в более чем\nв 100 банках",
    },
    # Блок 2 - Простой с преимуществами
    {
        "headline": {
            "main": "БАНКРОТСТВО\nГРАЖДАН",
            "sub": "Профессиональная помощь",
        },
        "left_block": {
            "location": "По всей России",
            "cta": "Записаться на консультацию",
        },
        "right_list": {
            "items": [
                "Бесплатная первичная консультация",
                "Подготовка документов для суда",
                "Представительство в арбитражном суде",
                "Работа с арбитражным управляющим",
            ],
            "numbered": True,
        },
        "info_block": "более 500\nуспешных дел",
    },
    # Блок 3 - Этапы работы
    {
        "headline": {
            "main": "ПРОЦЕДУРА\nБАНКРОТСТВА",
            "sub": "Этапы работы с клиентом",
        },
        "left_block": {
            "location": "Москва и регионы",
            "cta": "Получить консультацию",
        },
        "right_list": {
            "items": [
                "Анализ финансовой ситуации",
                "Сбор и подготовка документов",
                "Подача заявления в суд",
                "Сопровождение до завершения",
            ],
            "numbered": True,
        },
        "info_block": "опыт работы\nболее 10 лет",
    },
    # Блок 4 - Для кого услуга
    {
        "headline": {
            "main": "БАНКРОТСТВО\nФИЗЛИЦ",
            "sub": "Кому подходит процедура?",
        },
        "left_block": {
            "location": "Консультация бесплатно",
            "cta": "Узнать подробнее",
        },
        "right_list": {
            "items": [
                "Долг превышает 500 000 рублей",
                "Нет возможности платить по кредитам",
                "Есть просрочки более 3 месяцев",
                "Доходов не хватает на платежи",
            ],
            "numbered": False,
        },
        "info_block": "индивидуальный\nподход к каждому",
    },
    # Блок 5 - Полный комплекс
    {
        "headline": {
            "main": "БАНКРОТСТВО\nПОД КЛЮЧ",
            "sub": "Полное сопровождение",
        },
        "left_block": {
            "location": "Вся Россия",
            "cta": "Оставить заявку",
        },
        "right_list": {
            "items": [
                "Консультация арбитражного управляющего",
                "Подготовка полного пакета документов",
                "Представительство в суде",
                "Сопровождение до завершения дела",
            ],
            "numbered": True,
        },
        "info_block": "фиксированная\nстоимость услуг",
    },
]

# Дисклеймеры (ОБЯЗАТЕЛЬНЫЕ по закону) — расширенные варианты
BANKRUPTCY_DISCLAIMERS_2024 = [
    "Услуги оказываются в соответствии с 127-ФЗ",
    "Результат зависит от индивидуальных обстоятельств",
    "Не является публичной офертой",
    "Требуется консультация специалиста",
    "Услуги носят информационно-консультационный характер",
    "Необходима индивидуальная консультация юриста",
    "Условия и стоимость определяются индивидуально",
]

# С 01.09.2025 - с предупреждением (7 вариантов)
BANKRUPTCY_DISCLAIMERS_2025 = [
    "ВНИМАНИЕ! Банкротство имеет правовые последствия. Консультация обязательна",
    "ПРЕДУПРЕЖДЕНИЕ: Процедура банкротства влечёт ограничения. Услуги платные",
    "ВНИМАНИЕ! Банкротство — серьёзная процедура с последствиями. Консультируйтесь",
    "ВАЖНО! Банкротство влечёт юридические последствия. Необходима консультация",
    "ПРЕДУПРЕЖДЕНИЕ: Перед началом процедуры банкротства получите консультацию специалиста",
    "ВНИМАНИЕ! Решение о банкротстве требует тщательного анализа. Услуги оказываются платно",
    "ВАЖНО! Банкротство накладывает ограничения. Проконсультируйтесь с юристом",
]

# С 01.01.2026 - полный дисклеймер с последствиями и бесплатными вариантами (7 вариантов)
BANKRUPTCY_DISCLAIMERS_2026 = [
    "ВНИМАНИЕ! Банкротство влечёт ограничения: запрет на кредиты 5 лет, руководящие должности 3 года. Бесплатная процедура доступна через МФЦ при долге до 1 млн руб.",
    "ПРЕДУПРЕЖДЕНИЕ: Последствия банкротства: ограничение выезда, контроль расходов, запрет на кредиты. Льготное банкротство через МФЦ — бесплатно при соответствии условиям",
    "ВНИМАНИЕ! Риски банкротства: реализация имущества, ограничения на 3-5 лет. Бесплатное внесудебное банкротство возможно через МФЦ",
    "ВАЖНО! Банкротство: ограничение на кредиты, запрет занимать руководящие должности. Бесплатный вариант — внесудебное банкротство через МФЦ при долге до 1 млн руб.",
    "ПРЕДУПРЕЖДЕНИЕ: Последствия процедуры: контроль финансов, ограничения по должностям. Бесплатная процедура через МФЦ доступна при соблюдении условий 127-ФЗ",
    "ВНИМАНИЕ! При банкротстве возможна реализация имущества, действуют ограничения 3-5 лет. Льготное банкротство через МФЦ — при долге до 1 млн руб. бесплатно",
    "ВАЖНО! Банкротство влечёт правовые последствия и ограничения. Внесудебное банкротство через МФЦ бесплатно при соответствии условиям закона",
]

# Сценарии для генерации фонов — 20 вариантов
BANKRUPTCY_SCENARIOS = [
    # === Офисные интерьеры ===
    {
        "name": "office_professional",
        "prompt": "professional law office interior, modern desk with legal documents, scales of justice, dark blue navy color scheme, soft professional lighting, business atmosphere, no people, clean empty space, 8k quality",
    },
    {
        "name": "office_modern",
        "prompt": "modern minimalist law office, glass and steel furniture, sleek design, dark blue and gray color scheme, professional ambient lighting, empty desk, no people, corporate atmosphere, 8k",
    },
    {
        "name": "office_classic",
        "prompt": "classic executive law office, leather armchair, wooden desk, legal books on shelves, brass lamp, warm lighting, dark wood and navy blue tones, prestigious atmosphere, no people, 8k",
    },
    {
        "name": "office_consulting",
        "prompt": "consulting room interior, comfortable seating area, professional decor, soft lighting, blue and beige color scheme, trust-inspiring atmosphere, no people, clean space, 8k quality",
    },
    # === Судебная тематика ===
    {
        "name": "courthouse_formal",
        "prompt": "formal courthouse interior background, marble columns, legal books, dark wood furniture, professional navy blue burgundy colors, elegant lighting, authoritative atmosphere, no people, 8k",
    },
    {
        "name": "courthouse_hall",
        "prompt": "grand courthouse hallway, marble floors and columns, high ceilings, classical architecture, dark blue and gold accents, dramatic lighting, majestic legal atmosphere, no people, 8k",
    },
    {
        "name": "courtroom_empty",
        "prompt": "empty courtroom interior, judges bench, wooden panels, scales of justice symbol, dark mahogany wood, navy blue and burgundy, official atmosphere, no people, professional lighting, 8k",
    },
    # === Документы и деловая атмосфера ===
    {
        "name": "documents_desk",
        "prompt": "professional desk with legal documents and folders, pen and glasses, dark wood surface, soft ambient lighting, business law office atmosphere, navy blue accents, no people, 8k quality",
    },
    {
        "name": "documents_stack",
        "prompt": "stack of legal documents on mahogany desk, official stamps and seals visible, professional lighting, dark blue background gradient, business atmosphere, no people, 8k",
    },
    {
        "name": "signing_table",
        "prompt": "elegant signing table with documents and pen, professional business setting, dark wood surface, soft spotlight, navy blue and gold colors, official atmosphere, no people, 8k quality",
    },
    # === Библиотека и книги ===
    {
        "name": "library_law",
        "prompt": "elegant law library background, legal volumes on wooden shelves, brass lamp, warm professional lighting, dark mahogany and navy blue, classic authoritative style, no people, 8k",
    },
    {
        "name": "library_classic",
        "prompt": "classic library with floor to ceiling bookshelves, legal reference books, wooden ladder, warm ambient lighting, dark rich colors, scholarly atmosphere, no people, 8k",
    },
    {
        "name": "books_closeup",
        "prompt": "closeup of legal books and law volumes, leather-bound covers with gold lettering, wooden shelf background, warm lighting, professional atmosphere, no people, 8k quality",
    },
    # === Абстрактные и минималистичные ===
    {
        "name": "abstract_legal",
        "prompt": "abstract professional legal background, geometric dark blue patterns, subtle document icons, elegant gradient navy to dark blue, minimalist corporate design, clean empty space, no people, 8k",
    },
    {
        "name": "minimal_blue",
        "prompt": "minimal professional background, solid dark navy blue gradient, subtle geometric patterns, corporate legal style, clean modern design, empty space for text, no distractions, 8k",
    },
    {
        "name": "gradient_professional",
        "prompt": "smooth professional gradient background, dark navy blue to black, subtle texture, elegant corporate design, clean minimalist style, perfect for text overlay, 8k quality",
    },
    {
        "name": "abstract_geometric",
        "prompt": "abstract geometric background, dark blue triangles and lines, modern corporate design, subtle legal symbols, professional atmosphere, clean composition, 8k",
    },
    # === Символы права и финансов ===
    {
        "name": "scales_justice",
        "prompt": "scales of justice on pedestal, dark dramatic background, golden scales, navy blue and black gradient, symbolic legal imagery, professional lighting, no people, 8k quality",
    },
    {
        "name": "gavel_desk",
        "prompt": "judges gavel on wooden sound block, professional desk surface, dark moody lighting, navy blue background, legal authority symbol, dramatic composition, no people, 8k",
    },
    {
        "name": "financial_abstract",
        "prompt": "abstract financial background, subtle graphs and charts, dark blue corporate colors, professional business atmosphere, clean modern design, no text, no people, 8k quality",
    },
]

# =============================================================================
# Стили фона для дисклеймера (разные варианты)
# =============================================================================

DISCLAIMER_BG_STYLES = [
    {
        "name": "standard",
        "description": "Стандартный полупрозрачный",
        "type": "solid",
        "alpha": 160,
        "height_multiplier": 1.0,
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
        "name": "opaque_navy",
        "description": "Непрозрачный тёмно-синий",
        "type": "solid",
        "alpha": 255,
        "height_multiplier": 1.0,
        "color": (10, 15, 35),
    },
    {
        "name": "semi_transparent",
        "description": "Полупрозрачный средний",
        "type": "solid",
        "alpha": 130,
        "height_multiplier": 1.0,
        "color": (0, 0, 0),
    },
    {
        "name": "sparse",
        "description": "Разряженный (очень прозрачный)",
        "type": "solid",
        "alpha": 80,
        "height_multiplier": 1.0,
        "color": (0, 0, 0),
    },
    {
        "name": "tall_transparent",
        "description": "Вытянутый полупрозрачный (2x высота)",
        "type": "solid",
        "alpha": 140,
        "height_multiplier": 2.0,
        "color": (0, 0, 0),
    },
    {
        "name": "very_tall_sparse",
        "description": "Очень вытянутый разряженный (3x высота)",
        "type": "solid",
        "alpha": 90,
        "height_multiplier": 3.0,
        "color": (0, 0, 0),
    },
    {
        "name": "tall_opaque",
        "description": "Вытянутый непрозрачный (2.5x высота)",
        "type": "solid",
        "alpha": 230,
        "height_multiplier": 2.5,
        "color": (0, 0, 10),
    },
    {
        "name": "compressed",
        "description": "Сжатый (0.7x высота)",
        "type": "solid",
        "alpha": 190,
        "height_multiplier": 0.7,
        "color": (0, 0, 0),
    },
    {
        "name": "gradient_top_fade",
        "description": "Градиент с затуханием вверх",
        "type": "gradient",
        "alpha_bottom": 210,
        "alpha_top": 0,
        "height_multiplier": 2.0,
        "color": (0, 0, 0),
    },
    {
        "name": "gradient_tall_fade",
        "description": "Высокий градиент с плавным затуханием",
        "type": "gradient",
        "alpha_bottom": 190,
        "alpha_top": 0,
        "height_multiplier": 3.0,
        "color": (0, 0, 10),
    },
    {
        "name": "gradient_navy",
        "description": "Градиент с тёмно-синим оттенком",
        "type": "gradient",
        "alpha_bottom": 200,
        "alpha_top": 0,
        "height_multiplier": 2.0,
        "color": (10, 15, 35),
    },
    {
        "name": "full_width_banner",
        "description": "Баннер на всю ширину",
        "type": "solid",
        "alpha": 240,
        "height_multiplier": 1.8,
        "color": (10, 10, 20),
    },
]


def get_random_disclaimer_bg_style() -> Dict:
    """Возвращает случайный стиль фона для дисклеймера."""
    return random.choice(DISCLAIMER_BG_STYLES)


def get_disclaimer_bg_style_by_name(name: str):
    """Возвращает стиль фона для дисклеймера по имени."""
    for style in DISCLAIMER_BG_STYLES:
        if style['name'] == name:
            return style
    return None


# =============================================================================
# Стили для банкротства (более строгие, деловые цвета)
# =============================================================================

BANKRUPTCY_STYLES = [
    {
        "name": "navy_gold",
        "headline_color": (212, 175, 55),  # Золотой
        "text_color": (255, 255, 255),
        "accent_color": (212, 175, 55),
        "shadow_color": (0, 0, 30),
        "shadow_opacity": 200
    },
    {
        "name": "white_clean",
        "headline_color": (255, 255, 255),
        "text_color": (230, 230, 230),
        "accent_color": (200, 200, 200),
        "shadow_color": (0, 0, 0),
        "shadow_opacity": 220
    },
    {
        "name": "silver_professional",
        "headline_color": (192, 192, 210),
        "text_color": (240, 240, 245),
        "accent_color": (150, 150, 170),
        "shadow_color": (10, 10, 30),
        "shadow_opacity": 200
    },
    {
        "name": "cream_classic",
        "headline_color": (255, 248, 220),
        "text_color": (250, 250, 245),
        "accent_color": (220, 210, 180),
        "shadow_color": (30, 25, 15),
        "shadow_opacity": 180
    },
]


def get_appropriate_disclaimer() -> str:
    """Возвращает дисклеймер соответствующий текущей дате."""
    today = date.today()
    
    if today >= date(2026, 1, 1):
        return random.choice(BANKRUPTCY_DISCLAIMERS_2026)
    elif today >= date(2025, 9, 1):
        return random.choice(BANKRUPTCY_DISCLAIMERS_2025)
    else:
        return random.choice(BANKRUPTCY_DISCLAIMERS_2024)


def generate_phone() -> str:
    """Генерирует случайный российский номер телефона."""
    return f"+7 ({random.randint(900, 999)}) {random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(10, 99)}"


# =============================================================================
# Banner Overlay для банкротства
# =============================================================================

class BankruptcyBannerOverlay:
    """
    Наложение текста на баннеры о банкротстве.
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
        self.style = style or BANKRUPTCY_STYLES[0]
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
        """
        img_width, img_height = image.size
        
        height_mult = bg_style.get('height_multiplier', 1.0)
        color = bg_style.get('color', (0, 0, 0))
        bg_type = bg_style.get('type', 'solid')
        
        base_height = img_height - disc_y + 10
        actual_height = int(base_height * height_mult)
        adjusted_y = max(0, img_height - actual_height)
        
        disc_bg = Image.new('RGBA', image.size, (0, 0, 0, 0))
        disc_draw = ImageDraw.Draw(disc_bg)
        
        if bg_type == 'solid':
            alpha = bg_style.get('alpha', 160)
            disc_draw.rectangle(
                [0, adjusted_y, img_width, img_height],
                fill=(*color, alpha)
            )
        
        elif bg_type == 'gradient':
            alpha_bottom = bg_style.get('alpha_bottom', 210)
            alpha_top = bg_style.get('alpha_top', 0)
            
            gradient_height = img_height - adjusted_y
            for i in range(gradient_height):
                progress = i / max(1, gradient_height - 1)
                current_alpha = int(alpha_top + (alpha_bottom - alpha_top) * progress)
                y_pos = adjusted_y + i
                disc_draw.line(
                    [(0, y_pos), (img_width, y_pos)],
                    fill=(*color, current_alpha)
                )
        
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
        headline = headline or random.choice(BANKRUPTCY_HEADLINES)
        description = description or random.choice(BANKRUPTCY_DESCRIPTIONS)
        phone = phone or generate_phone()
        disclaimer = disclaimer or get_appropriate_disclaimer()
        
        # Валидация
        if self.validate:
            result = TextValidator.validate(headline, description, disclaimer)
            
            if result["violations"]:
                print("⚠️  НАРУШЕНИЯ ЗАКОНОДАТЕЛЬСТВА:")
                for v in result["violations"]:
                    print(f"   - {v}")
                raise ValueError("Текст содержит запрещённые формулировки!")
            
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
            "headline": max(28, int(60 * scale)),
            "text": max(16, int(32 * scale)),
            "phone": max(20, int(42 * scale)),
            "disclaimer": max(11, int(14 * scale)),  # Мелкий для дисклеймера
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
        
        # ===== HEADLINE =====
        hl_x = safe_left
        hl_y = safe_top
        max_w = int(img_width * 0.5)
        
        renderer.draw_text_with_shadow(
            draw, (hl_x, hl_y), headline,
            renderer.headline_font,
            self.style['headline_color'],
            shadow_offset=3,
            align="left",
            max_width=max_w,
            anchor="la",
        )
        
        # Декоративная линия
        line_y = hl_y + font_sizes["headline"] + int(img_height * 0.015)
        renderer.draw_decorative_line(
            draw, (hl_x, line_y),
            min(int(img_width * 0.15), max_w),
            self.style['accent_color'],
            thickness=3
        )
        
        # ===== DESCRIPTION =====
        desc_y = int(img_height * 0.38)
        desc_max_w = int(img_width * 0.45)
        
        renderer.draw_text_with_shadow(
            draw, (safe_left, desc_y), description,
            renderer.text_font,
            self.style['text_color'],
            shadow_offset=2,
            align="left",
            max_width=desc_max_w,
            anchor="la",
        )
        
        # ===== PHONE =====
        ph_y = int(img_height * 0.58)
        
        renderer.draw_text_with_shadow(
            draw, (safe_left, ph_y), phone,
            renderer.phone_font,
            self.style['headline_color'],
            shadow_offset=2,
            align="left",
            anchor="la",
        )
        
        # ===== DISCLAIMER (важно - крупнее и заметнее для банкротства) =====
        disc_y = safe_bottom - font_sizes["disclaimer"] * 3  # Место для 2-3 строк
        disc_max_w = int(img_width * 0.9)  # Почти вся ширина
        
        # Выбираем стиль фона для дисклеймера (случайный или заданный)
        bg_style = self.disclaimer_bg_style or get_random_disclaimer_bg_style()
        
        # Применяем фон с выбранным стилем
        image = self._draw_disclaimer_background(image, disc_y, bg_style)
        draw = ImageDraw.Draw(image)
        
        # Для вытянутых фонов центрируем текст
        height_mult = bg_style.get('height_multiplier', 1.0)
        if height_mult >= 2.0:
            disc_text_y = int(img_height - (img_height - disc_y + 10) * 0.35)
        else:
            disc_text_y = disc_y
        
        renderer.draw_text_with_shadow(
            draw, (img_width // 2, disc_text_y), disclaimer,
            renderer.disclaimer_font,
            (255, 255, 255),  # Белый для контраста
            shadow_offset=1,
            align="center",
            max_width=disc_max_w,
            anchor="ma",
        )
        
        return image
    
    def apply_structured(
        self,
        image: Image.Image,
        content: Dict[str, Any] = None,
        phone: str = None,
        disclaimer: str = None,
    ) -> Image.Image:
        """
        Применяет структурированный контент с маркированными списками.
        
        Формат content:
        {
            "headline": {"main": "...", "sub": "..."},
            "left_block": {"location": "...", "cta": "..."},
            "right_list": {"items": [...], "numbered": True/False},
            "info_block": "..."
        }
        """
        # Выбираем случайный структурированный контент если не передан
        content = content or random.choice(STRUCTURED_CONTENT)
        phone = phone or generate_phone()
        disclaimer = disclaimer or get_appropriate_disclaimer()
        
        # Валидация
        if self.validate:
            # Собираем весь текст для проверки
            all_text = content.get("headline", {}).get("main", "")
            all_text += " " + content.get("headline", {}).get("sub", "")
            if content.get("right_list"):
                all_text += " " + " ".join(content["right_list"].get("items", []))
            all_text += " " + disclaimer
            
            result = TextValidator.validate(
                content.get("headline", {}).get("main", ""),
                all_text,
                disclaimer
            )
            
            if result["violations"]:
                print("⚠️  НАРУШЕНИЯ ЗАКОНОДАТЕЛЬСТВА:")
                for v in result["violations"]:
                    print(f"   - {v}")
                raise ValueError("Текст содержит запрещённые формулировки!")
        
        # Конвертация в RGBA
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        img_width, img_height = image.size
        
        # Размеры шрифтов (масштабируемые)
        scale = min(img_width, img_height) / self.REF_WIDTH
        font_sizes = {
            "main_headline": max(36, int(70 * scale)),
            "sub_headline": max(20, int(36 * scale)),
            "list_title": max(16, int(24 * scale)),
            "list_item": max(14, int(20 * scale)),
            "list_number": max(40, int(80 * scale)),
            "location": max(18, int(28 * scale)),
            "cta": max(16, int(22 * scale)),
            "phone": max(22, int(48 * scale)),
            "info_block": max(14, int(20 * scale)),
            "disclaimer": max(11, int(14 * scale)),
        }
        
        renderer = TextRenderer(
            self.style,
            headline_size=font_sizes["main_headline"],
            text_size=font_sizes["list_item"],
            phone_size=font_sizes["phone"],
            disclaimer_size=font_sizes["disclaimer"],
        )
        
        draw = ImageDraw.Draw(image)
        
        # Создаём дополнительные шрифты
        fm = FontManager()
        sub_headline_font = fm.get_font(font_sizes["sub_headline"], bold=True)
        list_title_font = fm.get_font(font_sizes["list_title"], bold=True)
        list_item_font = fm.get_font(font_sizes["list_item"])
        list_number_font = fm.get_font(font_sizes["list_number"], bold=True)
        location_font = fm.get_font(font_sizes["location"], bold=True)
        cta_font = fm.get_font(font_sizes["cta"], bold=True)
        info_font = fm.get_font(font_sizes["info_block"])
        
        # Границы
        margin = int(min(img_width, img_height) * 0.05)
        safe_left = margin
        safe_right = img_width - margin
        safe_top = margin
        safe_bottom = img_height - margin
        
        # ===== Полупрозрачный оверлей для правой части (списки) =====
        right_overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
        right_draw = ImageDraw.Draw(right_overlay)
        
        # Зелёная полоса справа (как на примере unicredo)
        green_x = int(img_width * 0.58)
        right_draw.rectangle(
            [green_x, 0, img_width, img_height],
            fill=(34, 139, 34, 200)  # Зелёный полупрозрачный
        )
        image = Image.alpha_composite(image, right_overlay)
        draw = ImageDraw.Draw(image)
        
        # ===== ГЛАВНЫЙ ЗАГОЛОВОК (слева) =====
        headline_data = content.get("headline", {})
        main_text = headline_data.get("main", "БАНКРОТСТВО\nФИЗИЧЕСКИХ ЛИЦ")
        sub_text = headline_data.get("sub", "")
        
        # Цвет заголовка - зелёный на тёмном фоне
        headline_color = (34, 139, 34)  # Зелёный
        
        hl_x = safe_left
        hl_y = safe_top + int(img_height * 0.05)
        
        # Рисуем главный заголовок
        renderer.draw_text_with_shadow(
            draw, (hl_x, hl_y), main_text,
            renderer.headline_font,
            headline_color,
            shadow_offset=2,
            align="left",
            max_width=int(img_width * 0.5),
            anchor="la",
        )
        
        # Подзаголовок
        if sub_text:
            sub_y = hl_y + font_sizes["main_headline"] * main_text.count('\n') + font_sizes["main_headline"] + 10
            renderer.draw_text_with_shadow(
                draw, (hl_x, sub_y), sub_text,
                sub_headline_font,
                headline_color,
                shadow_offset=1,
                align="left",
                anchor="la",
            )
        
        # ===== ЛЕВЫЙ БЛОК (локация + CTA) =====
        left_block = content.get("left_block", {})
        cta_bottom_y = int(img_height * 0.45)  # По умолчанию, если нет CTA
        
        if left_block:
            location_text = left_block.get("location", "")
            cta_text = left_block.get("cta", "")
            
            loc_y = int(img_height * 0.45)
            
            if location_text:
                renderer.draw_text_with_shadow(
                    draw, (hl_x, loc_y), location_text,
                    location_font,
                    (30, 30, 30),
                    shadow_offset=1,
                    align="left",
                    anchor="la",
                )
            
            # Кнопка CTA
            if cta_text:
                cta_y = loc_y + font_sizes["location"] * (location_text.count('\n') + 1) + 30
                
                # Рисуем фон кнопки
                cta_bbox = draw.textbbox((0, 0), cta_text, font=cta_font)
                btn_width = cta_bbox[2] - cta_bbox[0] + 40
                btn_height = cta_bbox[3] - cta_bbox[1] + 20
                
                # Скруглённый прямоугольник (эмуляция)
                btn_color = (34, 139, 34)  # Зелёный
                draw.rounded_rectangle(
                    [hl_x, cta_y, hl_x + btn_width, cta_y + btn_height],
                    radius=10,
                    fill=btn_color
                )
                
                # Текст кнопки
                draw.text(
                    (hl_x + 20, cta_y + 10),
                    cta_text,
                    font=cta_font,
                    fill=(255, 255, 255)
                )
                
                # Запоминаем нижнюю границу кнопки CTA
                cta_bottom_y = cta_y + btn_height
        
        # ===== ПРАВЫЙ СПИСОК (нумерованный или маркированный) =====
        right_list = content.get("right_list", {})
        
        if right_list and right_list.get("items"):
            items = right_list["items"]
            numbered = right_list.get("numbered", True)
            
            list_x = green_x + int(img_width * 0.03)
            list_y = safe_top + int(img_height * 0.08)
            
            for idx, item in enumerate(items, 1):
                # Номер или маркер
                if numbered:
                    # Большой номер
                    number_text = str(idx)
                    number_color = (200, 200, 200, 100)  # Полупрозрачный серый
                    
                    # Рисуем большой номер
                    draw.text(
                        (list_x, list_y - 10),
                        number_text,
                        font=list_number_font,
                        fill=(200, 200, 200)
                    )
                    
                    item_x = list_x + font_sizes["list_number"] + 10
                else:
                    # Маркер (точка)
                    bullet_size = 8
                    bullet_y = list_y + font_sizes["list_item"] // 2
                    draw.ellipse(
                        [list_x, bullet_y - bullet_size//2, 
                         list_x + bullet_size, bullet_y + bullet_size//2],
                        fill=(255, 255, 255)
                    )
                    item_x = list_x + 20
                
                # Текст пункта
                max_item_width = safe_right - item_x - margin
                
                # Переносим длинные строки
                lines = self._wrap_text(item, list_item_font, max_item_width, draw)
                
                for line in lines:
                    draw.text(
                        (item_x, list_y),
                        line,
                        font=list_item_font,
                        fill=(255, 255, 255)
                    )
                    list_y += font_sizes["list_item"] + 5
                
                list_y += 20  # Отступ между пунктами
        
        # ===== ИНФОРМАЦИОННЫЙ БЛОК (справа внизу) =====
        info_text = content.get("info_block", "")
        
        if info_text:
            info_x = green_x + int(img_width * 0.05)
            info_y = int(img_height * 0.70)
            
            # Фон для инфо-блока
            info_lines = info_text.split('\n')
            info_bbox = draw.textbbox((0, 0), info_text, font=info_font)
            info_width = info_bbox[2] - info_bbox[0] + 30
            info_height = info_bbox[3] - info_bbox[1] + 20
            
            draw.rounded_rectangle(
                [info_x - 10, info_y - 10, info_x + info_width, info_y + info_height],
                radius=5,
                fill=(0, 60, 0, 180)
            )
            
            draw.text(
                (info_x, info_y),
                info_text,
                font=info_font,
                fill=(255, 255, 255)
            )
        
        # ===== ТЕЛЕФОН =====
        # Располагаем ниже кнопки CTA с отступом в 1.5 размера шрифта телефона
        ph_y = cta_bottom_y + int(font_sizes["phone"] * 1.5)
        
        renderer.draw_text_with_shadow(
            draw, (safe_left, ph_y), phone,
            renderer.phone_font,
            self.style['headline_color'],
            shadow_offset=2,
            align="left",
            anchor="la",
        )
        
        # ===== DISCLAIMER =====
        disc_y = safe_bottom - font_sizes["disclaimer"] * 3
        disc_max_w = int(img_width * 0.9)
        
        bg_style = self.disclaimer_bg_style or get_random_disclaimer_bg_style()
        image = self._draw_disclaimer_background(image, disc_y, bg_style)
        draw = ImageDraw.Draw(image)
        
        height_mult = bg_style.get('height_multiplier', 1.0)
        if height_mult >= 2.0:
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
    
    def _wrap_text(self, text: str, font, max_width: int, draw: ImageDraw.Draw) -> List[str]:
        """Разбивает текст на строки по ширине."""
        words = text.replace('\n', ' ').split(' ')
        lines = []
        current_line = ""
        
        for word in words:
            test_line = current_line + " " + word if current_line else word
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
            
            if width <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
        
        return lines
    
    def apply_bullet_list(
        self,
        image: Image.Image,
        bullet_list: Dict[str, Any] = None,
        headline: str = None,
        phone: str = None,
        disclaimer: str = None,
        position: str = "right",
    ) -> Image.Image:
        """
        Применяет баннер с маркированным списком.
        
        Args:
            bullet_list: {"title": "...", "items": [...], "position": "left"/"right"}
            position: где разместить список - "left" или "right"
        """
        bullet_list = bullet_list or random.choice(BULLET_LISTS)
        headline = headline or random.choice(BANKRUPTCY_HEADLINES)
        phone = phone or generate_phone()
        disclaimer = disclaimer or get_appropriate_disclaimer()
        position = bullet_list.get("position", position)
        
        # Валидация
        if self.validate:
            all_text = headline + " " + bullet_list.get("title", "")
            all_text += " " + " ".join(bullet_list.get("items", []))
            all_text += " " + disclaimer
            
            result = TextValidator.validate(headline, all_text, disclaimer)
            
            if result["violations"]:
                raise ValueError("Текст содержит запрещённые формулировки!")
        
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        
        img_width, img_height = image.size
        
        scale = min(img_width, img_height) / self.REF_WIDTH
        font_sizes = {
            "headline": max(32, int(65 * scale)),
            "list_title": max(18, int(28 * scale)),
            "list_item": max(14, int(22 * scale)),
            "phone": max(22, int(46 * scale)),
            "disclaimer": max(11, int(14 * scale)),
        }
        
        renderer = TextRenderer(
            self.style,
            headline_size=font_sizes["headline"],
            text_size=font_sizes["list_item"],
            phone_size=font_sizes["phone"],
            disclaimer_size=font_sizes["disclaimer"],
        )
        
        fm = FontManager()
        list_title_font = fm.get_font(font_sizes["list_title"], bold=True)
        list_item_font = fm.get_font(font_sizes["list_item"])
        
        draw = ImageDraw.Draw(image)
        
        margin = int(min(img_width, img_height) * 0.05)
        safe_left = margin
        safe_right = img_width - margin
        safe_top = margin
        safe_bottom = img_height - margin
        
        # Определяем позиции в зависимости от position
        if position == "right":
            headline_x = safe_left
            headline_max_w = int(img_width * 0.5)
            list_x = int(img_width * 0.55)
            list_max_w = safe_right - list_x
        else:
            headline_x = int(img_width * 0.5)
            headline_max_w = safe_right - headline_x
            list_x = safe_left
            list_max_w = int(img_width * 0.45)
        
        # ===== ЗАГОЛОВОК =====
        hl_y = safe_top
        renderer.draw_text_with_shadow(
            draw, (headline_x, hl_y), headline,
            renderer.headline_font,
            self.style['headline_color'],
            shadow_offset=3,
            align="left",
            max_width=headline_max_w,
            anchor="la",
        )
        
        # ===== МАРКИРОВАННЫЙ СПИСОК =====
        list_title = bullet_list.get("title", "")
        items = bullet_list.get("items", [])
        
        list_y = safe_top + int(img_height * 0.05)
        
        if list_title:
            draw.text(
                (list_x, list_y),
                list_title,
                font=list_title_font,
                fill=self.style['headline_color']
            )
            list_y += font_sizes["list_title"] + 20
        
        bullet_char = "•"
        for item in items:
            bullet_text = f"{bullet_char} {item}"
            
            lines = self._wrap_text(bullet_text, list_item_font, list_max_w, draw)
            
            for i, line in enumerate(lines):
                if i > 0:
                    line = "   " + line  # Отступ для продолжения
                draw.text(
                    (list_x, list_y),
                    line,
                    font=list_item_font,
                    fill=self.style['text_color']
                )
                list_y += font_sizes["list_item"] + 3
            
            list_y += 10  # Отступ между пунктами
        
        # ===== ТЕЛЕФОН =====
        ph_y = int(img_height * 0.55)
        ph_x = headline_x if position == "right" else safe_left
        
        renderer.draw_text_with_shadow(
            draw, (ph_x, ph_y), phone,
            renderer.phone_font,
            self.style['headline_color'],
            shadow_offset=2,
            align="left",
            anchor="la",
        )
        
        # ===== DISCLAIMER =====
        disc_y = safe_bottom - font_sizes["disclaimer"] * 3
        disc_max_w = int(img_width * 0.9)
        
        bg_style = self.disclaimer_bg_style or get_random_disclaimer_bg_style()
        image = self._draw_disclaimer_background(image, disc_y, bg_style)
        draw = ImageDraw.Draw(image)
        
        height_mult = bg_style.get('height_multiplier', 1.0)
        if height_mult >= 2.0:
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


# Хелперы для получения контента
def get_random_bullet_list() -> Dict[str, Any]:
    """Возвращает случайный маркированный список."""
    return random.choice(BULLET_LISTS)


def get_random_extended_headline() -> Dict[str, Any]:
    """Возвращает случайный расширенный заголовок."""
    return random.choice(EXTENDED_HEADLINES)


def get_random_structured_content() -> Dict[str, Any]:
    """Возвращает случайный структурированный контент."""
    return random.choice(STRUCTURED_CONTENT)


def get_random_cta() -> str:
    """Возвращает случайный призыв к действию."""
    return random.choice(CTA_BUTTONS)


def get_random_info_block() -> Dict[str, Any]:
    """Возвращает случайный информационный блок."""
    return random.choice(INFO_BLOCKS)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Генератор баннеров о банкротстве (с проверкой законодательства)"
    )
    
    # Input
    parser.add_argument("--image", type=str, help="Путь к изображению-фону")
    parser.add_argument("--input-dir", type=str, help="Папка с изображениями")
    
    # Output
    parser.add_argument("--output", type=str, default="output/bankruptcy",
                        help="Путь для сохранения")
    
    # Текст
    parser.add_argument("--headline", type=str, help="Заголовок")
    parser.add_argument("--description", type=str, help="Описание")
    parser.add_argument("--phone", type=str, help="Телефон")
    parser.add_argument("--disclaimer", type=str, help="Дисклеймер")
    
    # Стиль
    parser.add_argument("--style", type=str, 
                        choices=[s['name'] for s in BANKRUPTCY_STYLES],
                        help="Стиль оформления")
    parser.add_argument("--layout", type=str,
                        choices=[l['name'] for l in LAYOUTS],
                        help="Лейаут")
    
    # Валидация
    parser.add_argument("--no-validate", action="store_true",
                        help="Отключить проверку на соответствие закону")
    parser.add_argument("--validate-text", type=str,
                        help="Проверить текст на запрещённые формулировки")
    
    # Утилиты
    parser.add_argument("--list-headlines", action="store_true",
                        help="Показать доступные заголовки")
    parser.add_argument("--list-descriptions", action="store_true",
                        help="Показать доступные описания")
    parser.add_argument("--list-disclaimers", action="store_true",
                        help="Показать дисклеймеры по датам")
    parser.add_argument("--list-forbidden", action="store_true",
                        help="Показать запрещённые формулировки")
    
    args = parser.parse_args()
    
    # Утилиты
    if args.validate_text:
        violations = TextValidator.check_forbidden(args.validate_text)
        if violations:
            print("❌ НАЙДЕНЫ НАРУШЕНИЯ:")
            for v in violations:
                print(f"   {v}")
        else:
            print("✅ Текст соответствует требованиям")
        return
    
    if args.list_headlines:
        print("\n=== Заголовки (законопослушные) ===")
        for h in BANKRUPTCY_HEADLINES:
            print(f"  • {h}")
        return
    
    if args.list_descriptions:
        print("\n=== Описания (без обещаний списания) ===")
        for d in BANKRUPTCY_DESCRIPTIONS:
            print(f"  • {d}")
        return
    
    if args.list_disclaimers:
        print("\n=== Дисклеймеры по датам ===")
        print("\n[До 01.09.2025]:")
        for d in BANKRUPTCY_DISCLAIMERS_2024:
            print(f"  • {d}")
        print("\n[С 01.09.2025]:")
        for d in BANKRUPTCY_DISCLAIMERS_2025:
            print(f"  • {d}")
        print("\n[С 01.01.2026]:")
        for d in BANKRUPTCY_DISCLAIMERS_2026:
            print(f"  • {d}")
        return
    
    if args.list_forbidden:
        print("\n=== ЗАПРЕЩЁННЫЕ формулировки (ст. 5 38-ФЗ) ===")
        forbidden_examples = [
            "спишем долги", "списание долгов", "избавим от долгов",
            "решим проблему с долгами", "через суд", "без суда",
            "гарантированно", "100%", "навсегда",
            "не платите", "можно не платить",
            "банкротство компаний", "банкротство юридических лиц",
        ]
        for f in forbidden_examples:
            print(f"  ❌ {f}")
        return
    
    # Проверка входных данных
    if not args.image and not args.input_dir:
        parser.error("Укажите --image или --input-dir")
    
    # Получаем стиль
    style = None
    if args.style:
        for s in BANKRUPTCY_STYLES:
            if s['name'] == args.style:
                style = s
                break
    
    layout = get_layout_by_name(args.layout) if args.layout else LAYOUTS[0]
    
    # Создаём оверлей
    overlay = BankruptcyBannerOverlay(
        layout=layout,
        style=style,
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
        
        output_path = output_dir / f"{image_path.stem}_bankruptcy.png"
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
                output_path = output_dir / f"{img_path.stem}_bankruptcy.png"
                result.save(output_path, quality=95)
                print(f"✅ Создано: {output_path}")
            except ValueError as e:
                print(f"❌ Пропущено: {e}")
        
        print(f"\n✅ Готово! Результаты в: {output_dir}")


if __name__ == "__main__":
    main()
