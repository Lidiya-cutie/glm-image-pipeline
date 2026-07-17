#!/usr/bin/env python3
"""
Trust Management Ad Banner Overlay (Доверительное управление ценными бумагами/активами)

Генерация рекламных баннеров услуг доверительного управления
с учётом требований ст. 28 ФЗ-38 «О рекламе» (финансовые услуги).

ОБЯЗАТЕЛЬНЫЕ ЭЛЕМЕНТЫ (ст. 28):
- Наименование юридического лица (ООО/АО + полное название)
- Источник раскрытия информации (сайт, адрес, телефон)
- Предупреждение о рисках инвестирования

ЗАПРЕЩЕНО:
- Гарантии доходности («гарантируем», «стабильный доход без риска»)
- Прогнозы на основе прошлых результатов без оговорки
- Неподтверждённые утверждения («лучшая стратегия»)
- Сокрытие рисков, комиссий, налогов
"""

import argparse
import sys
import re
import json
from pathlib import Path
from PIL import Image, ImageDraw
from typing import Dict, List, Optional, Tuple, Any
import random

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Путь к JSON с реальными компаниями
COMPANIES_JSON_PATH = Path(__file__).parent / "trust_management_companies.json"

from scripts.text_overlay import (
    TextRenderer,
    LAYOUTS,
    get_layout_by_name,
)

# Путь к логотипам
LOGO_FOR_QR_DIR = Path("/mldata/logo_for_qr_extracted")


def _load_contact_logos(favicons_dir: Optional[str], logo_height: int, count: int) -> List[Image.Image]:
    """Загружает до count логотипов из favicons_dir, высота = logo_height. Возвращает список RGBA-изображений."""
    out: List[Image.Image] = []
    if not favicons_dir:
        favicons_dir = str(LOGO_FOR_QR_DIR)
    d = Path(favicons_dir)
    if not d.is_dir():
        return out
    files = list(d.glob("*.png")) + list(d.glob("*.jpg")) + list(d.glob("*.jpeg"))
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


def find_safe_qr_position_for_trust_management(
    img_width: int,
    img_height: int,
    qr_size: int,
    disclaimer_y: int = None,
    disclaimer_height: int = None,
) -> Tuple[int, int]:
    """
    Находит безопасную позицию для QR-кода в нижних углах баннера.
    QR размещается выше дисклеймера, чтобы не закрывать его.
    
    Args:
        img_width: Ширина изображения
        img_height: Высота изображения
        qr_size: Размер QR-кода
        disclaimer_y: Y-позиция начала дисклеймера (если None - вычисляется автоматически)
        disclaimer_height: Высота блока дисклеймера (если None - вычисляется автоматически)
    
    Returns:
        (x, y) позиция для QR-кода
    """
    margin = 20
    safety_margin = 25  # Отступ от верхней границы дисклеймера, чтобы QR не заходил на текст
    
    # Если позиция дисклеймера не передана, вычисляем приблизительно (как в overlay: safe_bottom - font*4)
    if disclaimer_y is None:
        edge_margin = int(min(img_width, img_height) * 0.06)
        safe_bottom = img_height - edge_margin
        disclaimer_y = safe_bottom - int(img_height * 0.05)  # ~4 строки дисклеймера
        disclaimer_height = int(img_height * 0.06)
    
    # Нижний край QR не должен заходить на дисклеймер: qr_y + qr_size <= disclaimer_y - safety_margin
    qr_bottom_max = disclaimer_y - safety_margin
    safe_top = max(margin, qr_bottom_max - qr_size)  # Y верхнего края QR
    
    # Кандидаты: левый и правый нижние углы (QR целиком выше дисклеймера)
    corner_candidates = [
        (margin, safe_top),
        (img_width - qr_size - margin, safe_top),
    ]
    
    qr_x, qr_y = random.choice(corner_candidates)
    # Гарантируем: нижний край QR не ниже допустимой линии
    qr_y = min(qr_y, qr_bottom_max - qr_size)
    
    qr_x = max(margin, min(qr_x, img_width - qr_size - margin))
    qr_y = max(margin, min(qr_y, qr_bottom_max - qr_size))
    
    return (qr_x, qr_y)

# =============================================================================
# Legal Compliance / Соответствие ст. 28 ФЗ-38
# =============================================================================

# ЗАПРЕЩЁННЫЕ формулировки (ст. 28 ч. 5.1 ФЗ-38)
FORBIDDEN_PHRASES = [
    r"гарантир[уеёо]м?\s+доход",
    r"гарантир[уеёо]м?\s+\d+\s*%",
    r"гарантир[а-яё]*\s+\d+\s*%",
    r"гарантированн[аоы]?\s+доходность",
    r"стабильн[ыйая]\s+доходность?\s+без\s+риск",
    r"доходность?\s+обеспечена",
    r"100\s*%\s+доход",
    r"прибыль\s+гарантирован",
    r"в\s+прошлом\s+году\s+мы\s+заработали.*значит",
    r"результаты?\s+в\s+будущем\s+такие\s+же",
    r"получите?\s+столько\s+же\s+как\s+в\s+прошлом",
    r"лучшая\s+стратеги[яи]",
    r"сам[ао]я?\s+низкая\s+комисси[яи]",
    r"без\s+риск[оа]в?\s+вообще",
    r"риск[оа]в?\s+нет",
]


class TrustManagementValidator:
    """Валидатор текстов на соответствие ст. 28 ФЗ-38."""

    @staticmethod
    def check_forbidden(text: str) -> List[str]:
        """Проверяет текст на запрещённые формулировки."""
        text_lower = text.lower()
        violations = []
        for pattern in FORBIDDEN_PHRASES:
            if re.search(pattern, text_lower):
                match = re.search(pattern, text_lower)
                violations.append(f"Запрещено: '{match.group()}'")
        return violations

    @staticmethod
    def check_legal_entity(text: str) -> bool:
        """Проверяет наличие юрлица (ООО, АО, ПАО и т.п.)."""
        return bool(re.search(r"(ооо|ао|пао|зао|нао)\s+[\"«]?[а-яё\s\-]+[\"»]?", text.lower()))

    @staticmethod
    def check_source_info(text: str) -> bool:
        """Проверяет наличие источника информации (сайт, телефон, адрес)."""
        has_site = bool(re.search(r"www\.|\.ru|\.рф|сайт|подробн", text.lower()))
        has_phone = bool(re.search(r"\+7|8\s*\(\d{3}\)|телефон|тел\.", text.lower()))
        has_address = "адрес" in text.lower()
        return has_site or has_phone or has_address

    @staticmethod
    def check_risk_disclaimer(text: str) -> bool:
        """Проверяет наличие предупреждения о рисках."""
        keywords = ["риск", "не гарантир", "результаты прошлого", "доходность не обеспечена", "инвестиции сопряжены"]
        return any(kw in text.lower() for kw in keywords)

    @staticmethod
    def validate(headline: str, description: str, disclaimer: str, legal_entity: str = "", source_info: str = "") -> Dict[str, Any]:
        full_text = f"{headline} {description} {disclaimer} {legal_entity} {source_info}"
        return {
            "valid": len(TrustManagementValidator.check_forbidden(full_text)) == 0,
            "violations": TrustManagementValidator.check_forbidden(full_text),
            "has_legal_entity": TrustManagementValidator.check_legal_entity(full_text) or bool(legal_entity),
            "has_source_info": TrustManagementValidator.check_source_info(full_text) or bool(source_info),
            "has_risk_disclaimer": TrustManagementValidator.check_risk_disclaimer(disclaimer),
        }

# =============================================================================
# ФИНАЛЬНЫЙ НАБОР КОНТЕНТА ДЛЯ БАННЕРОВ (ДОВЕРИТЕЛЬНОЕ УПРАВЛЕНИЕ)
# СТРОГОЕ СООТВЕТСТВИЕ ФЗ №38 "О РЕКЛАМЕ" (СТ. 28)
# =============================================================================

# -----------------------------------------------------------------------------
# 1. ЗАГОЛОВКИ (HEADLINES)
# Задача: Привлечь внимание, обозначить услугу.
# -----------------------------------------------------------------------------
TRUST_MANAGEMENT_HEADLINES = [
    # Группа: Классика и статус
    "Доверительное управление активами",
    "Управление частным капиталом",
    "Профессиональное управление финансами",
    "Ваш персональный инвестиционный портфель",
    "Индивидуальное доверительное управление",
    "Управление крупным капиталом",
    "Стратегии для квалифицированных инвесторов",
    "Комплексное управление состоянием",
    "Family Office: персональные решения",
    "Премиальное инвестиционное обслуживание",
    
    # Группа: Инструменты и рынки
    "Инвестиции в российские акции",
    "Стратегии на рынке облигаций",
    "Валютная диверсификация активов",
    "Управление портфелем ценных бумаг",
    "Доступ к биржевым инструментам",
    "Индивидуальный инвестиционный счет (ИИС)",
    "Сбалансированные стратегии роста",
    "Инструменты срочного рынка",
    "Акции, облигации, фонды",
    "Ликвидные активы в управлении",

    # Группа: Действие и подход
    "Формирование инвестиционного портфеля",
    "Разработка персональной стратегии",
    "Системный подход к инвестициям",
    "Интеллектуальное управление активами",
    "Экспертный взгляд на фондовый рынок",
    "Ребалансировка и оптимизация портфеля",
    "Профессиональная поддержка инвестора",
    "Ваши активы — наша работа",
    "Инвестиции с холодной головой",
    "Взвешенные инвестиционные решения"
]

# -----------------------------------------------------------------------------
# 2. ОПИСАНИЯ (DESCRIPTIONS) - USP
# ВАЖНО: Здесь НЕТ фраз "читайте на сайте", так как они есть в Блоке 4.
# Задача: Продать ценность услуги.
# -----------------------------------------------------------------------------
TRUST_MANAGEMENT_DESCRIPTIONS = [
    # Группа: Экспертность и аналитика
    "Команда аналитиков с многолетним опытом работы на фондовых рынках.",
    "Глубокий анализ эмитентов и макроэкономических показателей.",
    "Принятие решений на основе фундаментального анализа компаний.",
    "Профессиональный отбор перспективных активов в ваш портфель.",
    "Постоянный мониторинг рыночной ситуации и своевременная реакция.",
    "Использование алгоритмических моделей для оптимизации точек входа.",
    "Экспертная оценка рисков и потенциала каждого инструмента.",
    "Работаем с информацией, недоступной частному инвестору.",
    "Опыт прохождения через различные рыночные циклы и кризисы.",
    "Сочетание человеческой экспертизы и автоматизированных систем.",

    # Группа: Индивидуальный подход
    "Разработка стратегии, полностью отвечающей вашим финансовым целям.",
    "Учет вашего риск-профиля и желаемого горизонта инвестирования.",
    "Персональный менеджер, всегда готовый ответить на ваши вопросы.",
    "Формирование портфеля под конкретные задачи: от сбережения до роста.",
    "Гибкая настройка параметров управления под ваши требования.",
    "Возможность создания стратегии с регулярными выплатами (рантье).",
    "Индивидуальное налоговое планирование и юридическая поддержка.",
    "Учитываем ваши предпочтения по валютам и отраслям экономики.",
    "Адаптация стратегии при изменении ваших жизненных обстоятельств.",
    "Личное общение с управляющим вашего портфеля.",

    # Группа: Комфорт и сервис
    "Вы занимаетесь бизнесом или отдыхом, мы управляем вашими активами.",
    "Экономия вашего времени на анализ рынка и совершение сделок.",
    "Полная прозрачность: подробные отчеты о состоянии портфеля 24/7.",
    "Отсутствие скрытых комиссий и понятная система вознаграждения.",
    "Быстрый ввод и вывод активов по вашему распоряжению.",
    "Удобный личный кабинет и мобильное приложение для контроля.",
    "Единый счет для доступа к различным классам активов.",
    "Регулярная ребалансировка портфеля без вашего участия.",
    "Автоматическое удержание и выплата налогов (налоговый агент).",
    "Премиальный сервис и приоритетное обслуживание.",

    # Группа: Надежность и технологии
    "Строгое соблюдение законодательства и нормативов Банка России.",
    "Диверсификация портфеля для снижения рыночных рисков.",
    "Использование передовых технологий для защиты ваших данных.",
    "Прозрачная структура владения активами через спецдепозитарий.",
    "Четкое следование утвержденной инвестиционной декларации.",
    "Контроль рисков на всех этапах инвестиционного процесса.",
    "Сегрегация (обособление) активов клиентов от средств компании.",
    "Регулярный аудит и контроль со стороны регулятора.",
    "Технологичное исполнение сделок по лучшим доступным ценам.",
    "Инвестиции в ликвидные инструменты крупнейших компаний."
]

# -----------------------------------------------------------------------------
# 3. ДИСКЛЕЙМЕРЫ О РИСКАХ (DISCLAIMERS)
# Текст мелким шрифтом (Legal copy).
# -----------------------------------------------------------------------------
TRUST_MANAGEMENT_DISCLAIMERS = [
    # Группа: Полные (для больших форматов)
    "Денежные средства, передаваемые в доверительное управление, не застрахованы в соответствии с ФЗ «О страховании вкладов физических лиц». Доходность не гарантирована. Стоимость активов может увеличиваться и уменьшаться. Результаты инвестирования в прошлом не определяют доходы в будущем.",
    "Не является банковским вкладом. Государство не гарантирует доходность инвестиций. Взимание комиссий (вознаграждения управляющего) уменьшает доходность вложений. Ознакомьтесь с условиями управления активами до заключения договора.",
    "Инвестиции в ценные бумаги сопряжены с риском. Стоимость паев/активов может изменяться. Результаты деятельности управляющего в прошлом не гарантируют доходов в будущем. Государство не гарантирует возврат инвестированных средств.",
    "ВНИМАНИЕ! Инвестирование на рынке ценных бумаг сопряжено с риском. Возможна потеря части инвестированных средств. Доходность не гарантирована. Прошлые показатели не являются индикатором будущих результатов.",
    "Услуга доверительного управления несет в себе рыночные риски. Инвестор самостоятельно принимает решение о соответствии услуги своим целям. Гарантии доходности отсутствуют. Результаты прошлого не определяют будущее.",

    # Группа: Компактные (для стандартных баннеров)
    "Ценные бумаги — рисковый актив. Доходность не гарантирована государством. Результаты прошлого не определяют будущее.",
    "Инвестиции сопряжены с риском потери капитала. Доходность не гарантирована. Прошлые успехи не обещают будущей прибыли.",
    "Не является вкладом. АСВ не страхует. Стоимость активов может падать. Результаты прошлого не гарантируют доход в будущем.",
    "Риск убытков. Доходность не гарантирована. Комиссии уменьшают результат. Прошлое не определяет будущее.",
    "Инвестиции — это риск. Государство доход не гарантирует. Результаты прошлого не повторяются в будущем.",
    "Стоимость активов может меняться. Гарантий доходности нет. Результаты прошлого не определяют будущие доходы.",
    "Вложения в ценные бумаги связаны с риском. Доходность не обеспечена. Прошлое не гарантирует будущее.",
    "Инвестиции не застрахованы. Доходность не гарантирована. Результаты прошлого не являются прогнозом.",
    "Возможны потери. Доходность не гарантируется. Результаты прошлого не определяют доходы в будущем.",
    "Рыночные риски. Нет гарантий дохода. Прошлые результаты не определяют будущие."
]

# -----------------------------------------------------------------------------
# 4. ИСТОЧНИК ИНФОРМАЦИИ (SOURCE INFO)
# Обязательно: Сайт + Телефон + Призыв ознакомиться.
# Ставится в самый низ или во всплывающую подсказку.
# -----------------------------------------------------------------------------
SOURCE_INFO_TEMPLATES = [
    # Группа: Максимально подробные
    "Получить информацию о лице, осуществляющем управление активами, и ознакомиться с правилами можно на сайте www.example.ru и по тел. 8-800-000-00-00",
    "Сведения об управляющей компании, полные условия и правила доверительного управления доступны на www.example.ru. Тел.: 8-800-000-00-00",
    "Место раскрытия информации и ознакомления с правилами до заключения договора: www.example.ru, телефон 8-800-000-00-00",
    "Вся необходимая информация, подлежащая раскрытию в соответствии с законодательством РФ: www.example.ru, 8-800-000-00-00",
    "Подробные условия управления, тарифы и декларация о рисках размещены на официальном сайте www.example.ru. Консультации: 8-800-000-00-00",
    "Ознакомьтесь с правилами доверительного управления до передачи денежных средств. Источник информации: www.example.ru, тел. 8-800-000-00-00",

    # Группа: Стандартные
    "Подробная информация и правила на сайте www.example.ru и по телефону 8-800-000-00-00",
    "Условия управления и раскрытие информации: www.example.ru, тел. 8-800-000-00-00",
    "Ознакомиться с правилами ДУ можно на сайте www.example.ru. Телефон: 8-800-000-00-00",
    "Информация об управляющем и правила: www.example.ru, 8-800-000-00-00",
    "Полные условия на сайте www.example.ru и по телефону горячей линии 8-800-000-00-00",
    "Официальный сайт для раскрытия информации: www.example.ru. Телефон: 8-800-000-00-00",

    # Группа: Минималистичные (но законные)
    "Правила и инфо: www.example.ru, 8-800-000-00-00",
    "Условия и риски: www.example.ru, тел. 8-800-000-00-00",
    "Раскрытие информации: www.example.ru, 8-800-000-00-00",
    "Подробнее об услуге: www.example.ru, 8-800-000-00-00",
    "Документы УК: www.example.ru, +7 (000) 000-00-00"
]

LEGAL_ENTITY_TEMPLATES = [
    "ООО УК «Альфа-Капитал»",
    "АО «Управляющая компания Альфа»",
    "ООО «Доверительный капитал»",
    "ПАО «Инвестиционный менеджмент»",
]

# # =============================================================================
# # Контент для баннеров (15+ формулировок по чек-листу ст. 28)
# # =============================================================================

# # Варианты наименований юрлица (шаблоны — заказчик подставляет своё)
# LEGAL_ENTITY_TEMPLATES = [
#     "ООО УК «Альфа-Капитал»",
#     "АО «Управляющая компания Альфа»",
#     "ООО «Доверительный капитал»",
#     "ПАО «Инвестиционный менеджмент»",
# ]

# # Заголовки (без гарантий, допустимая терминология) — 15+ вариантов
# TRUST_MANAGEMENT_HEADLINES = [
#     "Доверительное управление активами",
#     "Управление ценными бумагами",
#     "Управление капиталом",
#     "Портфельное управление",
#     "Индивидуальная инвестиционная стратегия",
#     "Управление финансовыми активами",
#     "Профессиональное управление инвестициями",
#     "Индивидуальное доверительное управление",
#     "Управление инвестиционным портфелем",
#     "Стратегии инвестирования",
#     "Доверительное управление ценными бумагами",
#     "Управление средствами клиентов",
#     "Инвестиционное консультирование",
#     "Профессиональные решения для капитала",
#     "Доверьте управление профессионалам",
#     "ИДУ — индивидуальное доверительное управление",
# ]

# # Описания (без гарантий, с оговорками) — 15+ вариантов
# TRUST_MANAGEMENT_DESCRIPTIONS = [
#     "Консультация по условиям управления. Подробная информация на сайте и по телефону.",
#     "Ознакомьтесь с правилами управления и информацией об управляющем до передачи средств.",
#     "Индивидуальный подход к формированию портфеля. Полные условия на сайте.",
#     "Опытные специалисты. Информация об управляющем и правила — на сайте.",
#     "Анализ ваших целей и горизонта инвестирования. Подробности на сайте.",
#     "Разработка стратегии с учётом ваших пожеланий. Условия и комиссии — на сайте.",
#     "Полное раскрытие информации об управляющем. Адрес сайта для ознакомления с правилами.",
#     "Консультация бесплатно. Сведения о месте ознакомления с правилами — по запросу.",
#     "Индивидуальный подход. Правила управления и иные сведения — на сайте компании.",
#     "Профессиональный менеджмент. Подробная информация об условиях — на сайте.",
#     "Работа с ценными бумагами. Полные условия доверительного управления на сайте.",
#     "Формирование портфеля под ваши цели. Ознакомление с правилами — до передачи средств.",
#     "Сопровождение инвестиций. Информация об управляющем и правила — на сайте.",
#     "Портфельные решения. Адрес для ознакомления с полными условиями — на сайте.",
#     "Стратегии с учётом рисков. Подробности и раскрытие информации — на сайте.",
# ]

# # Дисклеймеры о рисках (обязательные по ст. 28) — 15+ вариантов
# TRUST_MANAGEMENT_DISCLAIMERS = [
#     "Инвестиции в ценные бумаги сопряжены с риском. Доходность не гарантирована государством. Результаты инвестирования в прошлом не определяют доходы в будущем.",
#     "ВНИМАНИЕ! Инвестиции в ценные бумаги связаны с риском. Доходность не гарантирована. Результаты прошлого не гарантируют доходности в будущем. Подробная информация на сайте.",
#     "Инвестиции сопряжены с риском. Доходность не обеспечена. Прошлые результаты не определяют будущую доходность. Ознакомьтесь с правилами на сайте.",
#     "Риск инвестирования в ценные бумаги. Доходность не гарантирована государством. Результаты прошлого не определяют доходы в будущем. Информация на сайте.",
#     "Инвестиционная деятельность связана с риском. Доходность не гарантирована. Подробная информация об управляющем и правилах — на сайте компании.",
#     "Ценные бумаги — рисковый актив. Доходность не гарантирована. Результаты инвестирования в прошлом не определяют доходы в будущем. Условия на сайте.",
#     "ВНИМАНИЕ! Инвестиции в ценные бумаги сопряжены с риском потери средств. Доходность не гарантирована. Ознакомьтесь с полной информацией на сайте.",
#     "Инвестиции не гарантируют доход. Результаты прошлого не определяют будущую доходность. Полные условия и раскрытие информации — на сайте.",
#     "Риски инвестирования: возможна потеря части или всего капитала. Доходность не гарантирована. Результаты прошлого не определяют доходы в будущем.",
#     "Инвестиции в ценные бумаги связаны с риском. Доходность не обеспечена государством. Подробная информация на сайте и по телефону.",
#     "ВНИМАНИЕ! Инвестиционная деятельность сопряжена с риском. Доходность не гарантирована. Результаты прошлого не гарантируют будущих доходов.",
#     "Инвестиции сопряжены с риском. Доходность не гарантирована. Ознакомьтесь с правилами управления до передачи средств. Информация на сайте.",
#     "Ценные бумаги — рисковый инструмент. Доходность не гарантирована. Результаты инвестирования в прошлом не определяют доходы в будущем.",
#     "Инвестиции в рынок ценных бумаг сопряжены с риском. Доходность не гарантирована. Полная информация — на сайте компании.",
#     "Риск потери капитала при инвестировании. Доходность не гарантирована. Результаты прошлого не определяют доходы в будущем. Условия на сайте.",
# ]

# # Источник раскрытия информации (обязательный блок)
# SOURCE_INFO_TEMPLATES = [
#     "Подробная информация на сайте www.example.ru и по тел. 8-800-000-00-00",
#     "Ознакомиться с правилами управления: www.example.ru, 8-800-000-00-00",
#     "Информация об управляющем и правила на сайте www.example.ru. Тел. 8-800-000-00-00",
#     "Полные условия и раскрытие информации: www.example.ru, 8-800-000-00-00",
#     "Сайт www.example.ru. Тел. 8-800-000-00-00. Ознакомьтесь с правилами до передачи средств",
#     "Подробности на www.example.ru и по телефону 8-800-000-00-00",
# ]

TRUST_MANAGEMENT_STYLES = [
    {"name": "navy_gold", "headline_color": (212, 175, 55), "text_color": (255, 250, 240), "accent_color": (255, 215, 0), "shadow_color": (10, 15, 35), "shadow_opacity": 200},
    {"name": "silver_professional", "headline_color": (220, 220, 235), "text_color": (240, 240, 250), "accent_color": (180, 180, 200), "shadow_color": (20, 20, 40), "shadow_opacity": 180},
    {"name": "cream_classic", "headline_color": (255, 248, 220), "text_color": (250, 250, 245), "accent_color": (230, 220, 180), "shadow_color": (50, 40, 30), "shadow_opacity": 180},
    {"name": "bronze", "headline_color": (205, 150, 80), "text_color": (255, 255, 255), "accent_color": (180, 130, 70), "shadow_color": (40, 25, 10), "shadow_opacity": 180},
    {"name": "white_clean", "headline_color": (255, 255, 255), "text_color": (240, 240, 240), "accent_color": (255, 255, 255), "shadow_color": (0, 0, 0), "shadow_opacity": 200},
]

DISCLAIMER_BG_STYLES = [
    {"name": "standard", "type": "solid", "alpha": 160, "height_multiplier": 1.0, "color": (0, 0, 0)},
    {"name": "opaque_navy", "type": "solid", "alpha": 255, "height_multiplier": 1.0, "color": (10, 15, 35)},
    {"name": "semi_transparent", "type": "solid", "alpha": 130, "height_multiplier": 1.0, "color": (0, 0, 0)},
    {"name": "gradient_soft", "type": "gradient", "alpha_bottom": 150, "alpha_top": 30, "height_multiplier": 1.5, "color": (0, 0, 0)},
    {"name": "full_width_banner", "type": "solid", "alpha": 230, "height_multiplier": 1.2, "color": (15, 15, 25)},
]


def load_companies() -> Dict[str, Dict[str, str]]:
    """Загружает данные компаний из JSON."""
    if COMPANIES_JSON_PATH.exists():
        try:
            with open(COMPANIES_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки компаний: {e}")
            return {}
    return {}


def get_random_company() -> Optional[Dict[str, str]]:
    """Возвращает случайную компанию из JSON."""
    companies = load_companies()
    if companies:
        name = random.choice(list(companies.keys()))
        return {
            "name": name,
            "website": companies[name]["website"],
            "phone": companies[name]["phone"],
        }
    return None


def format_source_info(website: str, phone: str) -> str:
    """Форматирует источник информации для баннера."""
    # Убираем https:// и http:// для краткости
    site_clean = website.replace("https://", "").replace("http://", "").rstrip("/")
    return f"Подробная информация на сайте {site_clean} и по тел. {phone}"


def generate_phone() -> str:
    return f"+7 ({random.randint(900, 999)}) {random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(10, 99)}"


def get_random_disclaimer_bg_style() -> Dict:
    return random.choice(DISCLAIMER_BG_STYLES)


def get_random_content(
    legal_entity: str = None,
    source_info: str = None,
    website: str = None,
    phone: str = None,
    use_real_companies: bool = True,
) -> Dict[str, str]:
    """
    Возвращает случайный набор контента, соответствующий чек-листу ст. 28.
    
    Args:
        legal_entity: Наименование юрлица (если None - выбирается случайно)
        source_info: Источник информации (если None - генерируется)
        website: Сайт компании (если None - выбирается из реальных компаний или шаблон)
        phone: Телефон (если None - выбирается из реальных компаний или генерируется)
        use_real_companies: Использовать реальные компании из JSON (по умолчанию True)
    """
    company = None
    if use_real_companies:
        company = get_random_company()
    
    if company:
        le = legal_entity or company["name"]
        ph = phone or company["phone"]
        web = website or company["website"]
        si = source_info or format_source_info(web, ph)
    else:
        le = legal_entity or random.choice(LEGAL_ENTITY_TEMPLATES)
        ph = phone or generate_phone()
        web = website or "www.example.ru"
        si = source_info or random.choice(SOURCE_INFO_TEMPLATES).replace("www.example.ru", web)
    
    return {
        "headline": random.choice(TRUST_MANAGEMENT_HEADLINES),
        "description": random.choice(TRUST_MANAGEMENT_DESCRIPTIONS),
        "disclaimer": random.choice(TRUST_MANAGEMENT_DISCLAIMERS),
        "legal_entity": le,
        "source_info": si,
        "phone": ph,
        "website": web,
    }


def get_layout_for_scenario(scenario: Dict) -> Dict:
    if not scenario.get("has_person"):
        return random.choice(LAYOUTS)
    position = scenario.get("person_position", "center")
    if position == "right":
        return get_layout_by_name("classic_left") or LAYOUTS[0]
    elif position == "left":
        return get_layout_by_name("classic_right") or LAYOUTS[1]
    return random.choice(LAYOUTS)


class TrustManagementBannerOverlay:
    """Наложение текста на баннер доверительного управления (ст. 28 ФЗ-38)."""

    REF_WIDTH = 1024
    REF_HEIGHT = 1024

    def __init__(self, layout=None, style=None, disclaimer_bg_style=None, validate=True):
        self.layout = layout or LAYOUTS[0]
        self.style = style or TRUST_MANAGEMENT_STYLES[0]
        self.disclaimer_bg_style = disclaimer_bg_style or get_random_disclaimer_bg_style()
        self.validate = validate

    def _draw_disclaimer_background(self, image: Image.Image, disc_y: int, bg_style: Dict) -> Image.Image:
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
            disc_draw.rectangle([0, adjusted_y, img_width, img_height], fill=(*color, alpha))
        elif bg_type == 'gradient':
            alpha_bottom = bg_style.get('alpha_bottom', 210)
            alpha_top = bg_style.get('alpha_top', 0)
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
        phone: str = None,
        disclaimer: str = None,
        legal_entity: str = "",
        source_info: str = "",
        add_phone_logos: bool = False,
        favicons_dir: Optional[str] = None,
    ) -> Image.Image:
        if self.validate:
            v = TrustManagementValidator.validate(headline, description, disclaimer, legal_entity, source_info)
            if v["violations"]:
                raise ValueError(f"Нарушение ст. 28 ФЗ-38: {v['violations']}")

        full_desc = description or random.choice(TRUST_MANAGEMENT_DESCRIPTIONS)
        if legal_entity:
            full_desc = f"{legal_entity}\n{full_desc}"
        if source_info:
            full_desc = f"{full_desc}\n{source_info}"

        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        img_width, img_height = image.size
        scale = min(img_width, img_height) / self.REF_WIDTH
        font_sizes = {
            "headline": max(28, int(60 * scale)),
            "text": max(16, int(32 * scale)),
            "phone": max(20, int(42 * scale)),
            "disclaimer": max(13, int(14 * scale)),
        }
        renderer = TextRenderer(
            self.style,
            headline_size=font_sizes["headline"],
            text_size=font_sizes["text"],
            phone_size=font_sizes["phone"],
            disclaimer_size=font_sizes["disclaimer"],
        )
        draw = ImageDraw.Draw(image)
        margin = int(min(img_width, img_height) * 0.06)
        safe_left, safe_top = margin, margin
        safe_bottom = img_height - margin

        # HEADLINE
        max_w = int(img_width * 0.5)
        renderer.draw_text_with_shadow(
            draw, (safe_left, safe_top), headline or random.choice(TRUST_MANAGEMENT_HEADLINES),
            renderer.headline_font, self.style['headline_color'],
            shadow_offset=3, align="left", max_width=max_w, anchor="la",
        )
        line_y = safe_top + font_sizes["headline"] + int(img_height * 0.015)
        renderer.draw_decorative_line(draw, (safe_left, line_y), min(int(img_width * 0.15), max_w), self.style['accent_color'], thickness=3)

        # DESCRIPTION (включая legal_entity и source_info)
        desc_y = int(img_height * 0.35)
        desc_max_w = int(img_width * 0.5)
        # Вычисляем высоту описания для правильного позиционирования телефона
        desc_height = renderer.draw_text_with_shadow(
            draw, (safe_left, desc_y), full_desc, renderer.text_font, self.style['text_color'],
            shadow_offset=2, align="left", max_width=desc_max_w, anchor="la",
        )

        # PHONE - размещаем ниже описания с отступом
        phone_text = phone or generate_phone()
        phone_spacing = int(font_sizes["text"] * 2.5)  # Отступ между описанием и телефоном
        ph_y = desc_y + desc_height + phone_spacing
        
        # Убеждаемся, что телефон не заходит на дисклеймер
        max_phone_y = safe_bottom - font_sizes["disclaimer"] * 5 - font_sizes["phone"]
        ph_y = min(ph_y, max_phone_y)
        
        # Вычисляем ширину телефона для позиционирования логотипов
        phone_bbox = renderer.phone_font.getbbox(phone_text)
        phone_width = phone_bbox[2] - phone_bbox[0]
        
        renderer.draw_text_with_shadow(
            draw, (safe_left, ph_y), phone_text,
            renderer.phone_font, self.style['headline_color'],
            shadow_offset=2, align="left", anchor="la",
        )
        
        # Информация о позиции телефона для наложения логотипов
        phone_info = {
            "x": safe_left,
            "y": ph_y,
            "width": phone_width,
            "height": font_sizes["phone"],
            "text": phone_text,
        }

        # DISCLAIMER
        disc_y = safe_bottom - font_sizes["disclaimer"] * 4
        disc_max_w = int(img_width * 0.7)
        bg_style = self.disclaimer_bg_style or get_random_disclaimer_bg_style()
        image = self._draw_disclaimer_background(image, disc_y, bg_style)
        draw = ImageDraw.Draw(image)
        disc_text_y = disc_y + int(font_sizes["disclaimer"] * 0.5)
        renderer.draw_text_with_shadow(
            draw, (img_width // 2, disc_text_y), disclaimer or random.choice(TRUST_MANAGEMENT_DISCLAIMERS),
            renderer.disclaimer_font, (255, 255, 255),
            shadow_offset=1, align="center", max_width=disc_max_w, anchor="ma",
        )
        
        # Накладываем логотипы после телефона (если включено и телефон в формате +7)
        if add_phone_logos and phone_info["text"].startswith("+7"):
            logo_height = int(font_sizes["phone"] * 1.3)  # Высота логотипа = высота текста телефона
            n_logos = random.randint(0, 2)  # 0-2 логотипа
            
            if n_logos > 0:
                logos = _load_contact_logos(favicons_dir or str(LOGO_FOR_QR_DIR), logo_height, n_logos)
                
                if logos:
                    # Позиция после телефона
                    logo_x = phone_info["x"] + phone_info["width"] + int(font_sizes["phone"] * 0.3)  # Отступ после телефона
                    logo_y = phone_info["y"] + int((phone_info["height"] - logo_height) / 2)  # Выравнивание по центру
                    
                    logo_spacing = max(4, logo_height // 6)
                    cursor_x = logo_x
                    
                    for logo_im in logos:
                        lw, lh = logo_im.size
                        # Проверяем, что логотип не выходит за границы
                        if cursor_x + lw > img_width - margin:
                            break
                        image.paste(logo_im, (cursor_x, logo_y), logo_im)
                        cursor_x += lw + logo_spacing
        
        return image


def get_disclaimer_bg_style_by_name(name: str):
    for s in DISCLAIMER_BG_STYLES:
        if s["name"] == name:
            return s
    return DISCLAIMER_BG_STYLES[0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trust Management Banner Overlay")
    parser.add_argument("--image", type=str, required=True)
    parser.add_argument("--output", type=str, default="output/trust_management")
    parser.add_argument("--list-headlines", action="store_true")
    parser.add_argument("--list-disclaimers", action="store_true")
    parser.add_argument("--validate", type=str, help="Проверить текст")
    args = parser.parse_args()

    if args.validate:
        v = TrustManagementValidator.check_forbidden(args.validate)
        print("Нарушения:" if v else "OK")
        for x in v:
            print(f"  {x}")
        sys.exit(0)

    if args.list_headlines:
        for h in TRUST_MANAGEMENT_HEADLINES:
            print(f"  • {h}")
        sys.exit(0)

    if args.list_disclaimers:
        for d in TRUST_MANAGEMENT_DISCLAIMERS[:5]:
            print(f"  • {d[:80]}...")
        sys.exit(0)
