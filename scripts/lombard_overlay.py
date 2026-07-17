#!/usr/bin/env python3
"""
Lombard Ad Banner Overlay (Ломбарды)

Генерация рекламных баннеров услуг ломбардов
с учётом требований ст. 28 ФЗ-38 «О рекламе» и ФЗ-196 «О ломбардах».

ОБЯЗАТЕЛЬНЫЕ ЭЛЕМЕНТЫ:
- Наименование юридического лица (ООО/АО + слово "Ломбард" в названии)
- Источник раскрытия информации (сайт, адрес, телефон)
- Режим работы (8:00-23:00, не круглосуточно!)

ЗАПРЕЩЕНО:
- Круглосуточная работа (24 часа) - только 8:00-23:00
- Привлечение инвестиций/вкладов
- Гарантированная оценка без оговорок ("лучшая", "самая высокая")
- Отсутствие ПСК при указании процентных ставок
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
COMPANIES_JSON_PATH = Path(__file__).parent / "lombard_companies.json"
# Путь к JSON с шаблонами дисклеймеров (подстановка {company_name}, {ogrn}, {inn}, {address}, {contacts})
DISCLAIMER_TEMPLATES_PATH = Path(__file__).parent / "lombard_disclaimer_templates.json"

# Кэш загруженных шаблонов дисклеймеров
_disclaimer_templates_cache: Optional[List[Dict]] = None

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


def find_safe_qr_position_for_lombard(
    img_width: int,
    img_height: int,
    qr_size: int,
    disclaimer_y: int = None,
    disclaimer_height: int = None,
) -> Tuple[int, int]:
    """
    Находит безопасную позицию для QR-кода в нижних углах баннера.
    QR размещается выше дисклеймера, чтобы не закрывать его.
    """
    margin = 20
    safety_margin = 25
    
    if disclaimer_y is None:
        edge_margin = int(min(img_width, img_height) * 0.06)
        safe_bottom = img_height - edge_margin
        disclaimer_y = safe_bottom - int(img_height * 0.05)
        disclaimer_height = int(img_height * 0.06)
    
    qr_bottom_max = disclaimer_y - safety_margin
    safe_top = max(margin, qr_bottom_max - qr_size)
    
    corner_candidates = [
        (margin, safe_top),
        (img_width - qr_size - margin, safe_top),
    ]
    
    qr_x, qr_y = random.choice(corner_candidates)
    qr_y = min(qr_y, qr_bottom_max - qr_size)
    
    qr_x = max(margin, min(qr_x, img_width - qr_size - margin))
    qr_y = max(margin, min(qr_y, qr_bottom_max - qr_size))
    
    return (qr_x, qr_y)

# =============================================================================
# Legal Compliance / Соответствие ст. 28 ФЗ-38 и ФЗ-196
# =============================================================================

# ЗАПРЕЩЁННЫЕ формулировки
FORBIDDEN_PHRASES = [
    r"круглосуточн[оая]",
    r"24\s*час[аов]?",
    r"вложи\s+деньг",
    r"принимаем\s+сбережен",
    r"инвестиц",
    r"вклад[ы]?",
    r"лучшая\s+оценк",
    r"сам[ая]?\s+высок[ая]?\s+цен[а]?",
    r"гарантированн[ая]?\s+оценк",
    r"0\s*%",
    r"низк[ая]?\s+ставк",
]


class LombardValidator:
    """Валидатор текстов на соответствие ст. 28 ФЗ-38 и ФЗ-196."""

    @staticmethod
    def check_forbidden(text: str) -> List[str]:
        """Проверяет текст на запрещённые формулировки."""
        text_lower = text.lower()
        violations = []
        for pattern in FORBIDDEN_PHRASES:
            if re.search(pattern, text_lower):
                match = re.search(pattern, text_lower)
                matched_text = match.group()
                
                # Исключение: "0%" разрешен в дисклеймерах, если указан ПСК (Полная стоимость кредита)
                # и есть полные условия займа (срок, сумма, ставка)
                # Проверяем по паттерну, так как matched_text может быть "0 %" или "0%"
                if pattern == r"0\s*%":
                    has_psk = bool(re.search(r"пск|полная\s+стоимость\s+кредит", text_lower))
                    has_conditions = bool(re.search(r"(срок|сумм[аы]|ставк[аы]|годовых)", text_lower))
                    # Если есть ПСК и условия, то "0%" легален в контексте дисклеймера
                    if has_psk and has_conditions:
                        continue  # Пропускаем это нарушение
                
                violations.append(f"Запрещено: '{matched_text}'")
        return violations

    @staticmethod
    def check_legal_entity(text: str) -> bool:
        """Проверяет наличие юрлица с обязательным словом 'Ломбард'."""
        has_org = bool(re.search(r"(ооо|ао|пао|зао|нао)\s+[\"«]?[а-яё\s\-]+[\"»]?", text.lower()))
        has_lombard = "ломбард" in text.lower()
        return has_org and has_lombard

    @staticmethod
    def check_source_info(text: str) -> bool:
        """Проверяет наличие источника информации."""
        has_site = bool(re.search(r"www\.|\.ru|\.рф|сайт|подробн", text.lower()))
        has_phone = bool(re.search(r"\+7|8\s*\(\d{3}\)|телефон|тел\.", text.lower()))
        has_address = "адрес" in text.lower()
        return has_site or has_phone or has_address

    @staticmethod
    def check_working_hours(text: str) -> bool:
        """Проверяет, что режим работы в пределах 8:00-23:00 (не круглосуточно)."""
        text_lower = text.lower()
        if "круглосуточн" in text_lower or "24 час" in text_lower:
            return False
        # Проверяем наличие времени в допустимом диапазоне
        time_pattern = r"(\d{1,2}):\d{2}"
        matches = re.findall(time_pattern, text)
        if matches:
            for match in matches:
                hour = int(match)
                if hour < 8 or hour > 23:
                    return False
        return True

    @staticmethod
    def validate(headline: str, description: str, disclaimer: str, legal_entity: str = "", source_info: str = "") -> Dict[str, Any]:
        full_text = f"{headline} {description} {disclaimer} {legal_entity} {source_info}"
        return {
            "valid": len(LombardValidator.check_forbidden(full_text)) == 0,
            "violations": LombardValidator.check_forbidden(full_text),
            "has_legal_entity": LombardValidator.check_legal_entity(full_text) or bool(legal_entity and "ломбард" in legal_entity.lower()),
            "has_source_info": LombardValidator.check_source_info(full_text) or bool(source_info),
            "has_valid_working_hours": LombardValidator.check_working_hours(full_text),
        }

# =============================================================================
# КОНТЕНТ ДЛЯ БАННЕРОВ КАТЕГОРИИ "ЛОМБАРДЫ"
# =============================================================================

# -----------------------------------------------------------------------------
# 1. ЗАГОЛОВКИ (HEADLINES)
# -----------------------------------------------------------------------------
LOMBARD_HEADLINES = [
    "Ломбард",
    "ЛОМБАРД\nденьги под залог",
    "Ваш Ломбард\nВаш залог спокойствия",
    "Скупка\nЛомбард",
    "Деньги под залог техники",
    "Займы под залог золота",
    "Нужны деньги? Оценка за 5 минут",
    "Финансовая помощь рядом",
    "Займы под залог ювелирных изделий",
    "Мгновенная оценка и выдача",
    "АВТОЛОМБАРД",
    "Деньги сразу наличными или на карту",
    "Ломбард: честная оценка",
    "Займ под залог автомобиля (ПТС)",
    "Деньги до зарплаты под залог",
    "Срочный выкуп и залог",
    "Автоломбард\nСрочный выкуп и залог",
    "Высокая оценка вашего золота",
    "Деньги под залог цифровой техники",
    "Ваши активы — ваши деньги",
    "Займы без кредитной истории",
    "Простое получение займа",
    "Надежное хранение залогов",
    "Деньги под залог шуб и меха",
    "Экспресс-займы под залог",
    "Рефинансирование займов в ломбарде",
    "Быстрая оценка и выдача средств",
    "Займы под залог драгоценностей",
    "Деньги под залог часов",
    "Профессиональная оценка изделий",
    "Займы под залог инструмента",
]

# -----------------------------------------------------------------------------
# 2. ОПИСАНИЯ (DESCRIPTIONS)
# -----------------------------------------------------------------------------
LOMBARD_DESCRIPTIONS = [
    "Высокая оценка. Минимум документов. Нужен только паспорт.",
    "Бережное хранение ваших вещей. Страхование залога за наш счёт.",
    "Без справок о доходах и поручителей. Оформление за 15 минут.",
    "Принимаем золото, серебро, цифровую технику и строительный инструмент.",
    "Прозрачные условия. Никаких скрытых комиссий и штрафов.",
    "Льготные условия для пенсионеров и студентов (18+). Быстро приедем куда угодно, оценим залог и переведем деньги!",
    "Возможность частичного погашения займа в любое время.",
    "Продление (пролонгация) договора займа без посещения офиса.",
    "Оценка онлайн по фото через WhatsApp или Telegram.",
    "Работаем строго по закону «О ломбардах». Достойная оценка золота и серебра!",
    "Профессиональные товароведы-оценщики. Реальный процент, реальная цена!",
    "Гарантия сохранности вашего имущества.",
    "Индивидуальный подход к оценке изделий с бриллиантами. Достойно оценим ваши вещи!",
    "Удобное расположение рядом с метро. Никаких скрытых комиссий и штрафов.",
    "Оплата процентов онлайн через личный кабинет.",
    "Принимаем сломанные изделия и зубное золото.",
    "Оцениваем технику до 80% от рыночной стоимости.",
    "Специальные тарифы для крупных сумм.",
    "Выкупаем залоги из других ломбардов.",
    "Бесплатная экспертная оценка ваших изделий.",
    "Оценка за 5 минут. Выдача средств в день обращения.",
    "Принимаем золото, серебро, платину, палладий.",
    "Займы под залог мобильных телефонов, ноутбуков, планшетов.",
    "Профессиональная оценка антиквариата и коллекционных предметов.",
    "Страхование залога включено в стоимость услуги.",
    "Возможность досрочного погашения без штрафов.",
    "Конфиденциальность и безопасность хранения.",
    "Опыт работы более 10 лет на рынке. Работаем строго по закону «О ломбардах».",
    "Сеть филиалов по всему городу. Оформление за 15 минут.",
    "Работаем с физическими лицами от 18 лет.",
]

# -----------------------------------------------------------------------------
# 3. ДИСКЛЕЙМЕРЫ (DISCLAIMERS)
# Подробные дисклеймеры с условиями займов, процентными ставками, ПСК
# Разнообразие по типам залогов: золото, шубы, техника, авто, спецтехника
# -----------------------------------------------------------------------------
LOMBARD_DISCLAIMERS = [
    # ========== БАЗОВЫЕ / КОРОТКИЕ ФОРМАТЫ (с реальными данными) ==========
    "ОЦЕНИВАЙТЕ СВОИ ФИНАНСОВЫЕ ВОЗМОЖНОСТИ И РИСКИ. ООО \"100 ЛОМБАРДОВ\", ОГРН 1164205075572, ИНН 4205333865. Займы предоставляются под залог движимого имущества. Режим работы: с 9:00 до 20:00.",
    "АО \"1М-ЛОМБАРД\", ОГРН 1092308001488, ИНН 2308154938. Юр.адрес: г. Краснодар, пр-кт Чекистов, д.28, пом.9. Подробности на сайте. Не является публичной офертой. Работаем с 8:00 до 22:00.",
    "ООО \"21 ВЕК\", ОГРН 1025901609117. Услуги по предоставлению краткосрочных займов и хранению вещей. Режим работы: пн-вс с 10:00 до 21:00. Тел.: +7 (342) 213-12-99.",
    "Общество с ограниченной ответственностью ЛОМБАРД \"100 ПРОЦЕНТОВ\", ОГРН 1167456065072, ИНН 7456030903. Режим работы: с 9:00 до 20:00. Email: lombard.100protsentov@yandex.ru",
    "ООО \"АВАНГАРД - ЛОМБАРД\", ОГРН 1102225008115. Займы под залог движимого имущества. Подробная информация на сайте. Режим работы: с 8:00 до 23:00. Тел.: +7 (905) 928-93-06",

    # ========== ПОДРОБНЫЕ С ПРЕДУПРЕЖДЕНИЕМ И РЕАЛЬНЫМИ АДРЕСАМИ ==========
    "ОЦЕНИВАЙТЕ СВОИ ФИНАНСОВЫЕ ВОЗМОЖНОСТИ И РИСКИ. ООО \"48+\", ОГРН 1194827010509, ИНН 4824098070. Юридический адрес: г. Липецк, пр-кт Имени 60-Летия СССР, д.33, пом.5. Займы предоставляются под залог движимого имущества. Тел.: +7 (910) 739-22-00. Режим работы: с 9:00 до 21:00.",
    "ООО ЛОМБАРД \"777\", ОГРН 1152310004880, ИНН 2310185980. Адрес: г. Краснодар, ул. Им. Гоголя, д.76. Услуги по предоставлению займов и хранению имущества. Информация не является офертой. Тел.: +7 (918) 442-74-74.",
    "ВНИМАНИЕ! ОЦЕНИВАЙТЕ СВОИ ФИНАНСОВЫЕ ВОЗМОЖНОСТИ. АО \"1М-ЛОМБАРД\" (ОГРН 1092308001488). Займы предоставляются на условиях платности, возвратности, срочности. Режим работы: с 9:00 до 21:00. Контакты: +7 (960) 482-98-38, o.firsova@mylom.ru.",

    # ========== ЗОЛОТО И ЮВЕЛИРНЫЕ ИЗДЕЛИЯ (с реальными компаниями) ==========
    "ОЦЕНИВАЙТЕ СВОИ ФИНАНСОВЫЕ ВОЗМОЖНОСТИ И РИСКИ. Займы предоставляются под залог ювелирных изделий из золота 585, 750 пробы. Сумма займа — от 5 000 до 500 000 рублей. Процентная ставка — от 0,15% до 0,4% в день (от 54,75% до 146% годовых). ПСК от 54,75% до 146% годовых. ООО \"999\", ОГРН 1141447005039, г. Якутск. Режим работы: с 9:00 до 20:00. Тел.: +7 (964) 429-20-12.",
    "Займ под залог золота и ювелирных изделий. Сумма займа от 1 000 до 600 000 рублей на срок от 1 до 365 дней. При займе до 5 000 рублей процентная ставка 0,35% в день (127,75% годовых). ПСК от 65,7% до 127,75% годовых. Документ для оформления — паспорт. ООО ЛОМБАРД \"999\", ОГРН 1146670026953, ИНН 6670428138, г. Екатеринбург. Режим работы: с 8:00 до 22:00. Тел.: +7 (343) 201-04-09.",
    "Займы под залог ювелирных изделий из золота, серебра, платины. Принимаем изделия с бриллиантами. Сумма займа от 10 000 до 500 000 рублей, срок от 15 до 365 дней. Процентная ставка от 0,18% до 0,35% в день. ООО \"14 КАРАТ\", ОГРН 1203700019357, г. Иваново. Режим работы: с 9:00 до 21:00. Тел.: +7 (996) 919-26-16.",

    # ========== ШУБЫ И МЕХ (с разными компаниями) ==========
    "Займы под залог шуб и меховых изделий из натурального меха (норка, соболь, лиса). Сумма займа от 10 000 до 300 000 рублей, срок от 30 до 180 дней. Процентная ставка 0,25% в день (91,25% годовых). ПСК 91,25% годовых. ООО \"АВЕНЮ\", ОГРН 1227500006470, г. Чита. Режим работы: с 9:00 до 20:00. Тел.: +7 (924) 471-21-11.",
    "ОЦЕНИВАЙТЕ СВОИ ФИНАНСОВЫЕ ВОЗМОЖНОСТИ. Займы под залог шуб из натурального меха. Принимаем шубы из норки, соболя, чернобурки. Сумма займа от 15 000 до 500 000 рублей. Процентная ставка от 0,2% до 0,3% в день. ООО \"АВАНГАРД\", ОГРН 1177456054775, г. Челябинск. Режим работы: с 8:00 до 22:00.",

    # ========== ТЕХНИКА (ЦИФРОВАЯ, БЫТОВАЯ) ==========
    "ОЦЕНИВАЙТЕ СВОИ ФИНАНСОВЫЕ ВОЗМОЖНОСТИ И РИСКИ. Займы под залог цифровой техники (смартфоны, планшеты, ноутбуки). Сумма займа от 1 000 до 100 000 рублей, срок от 7 до 90 дней. Процентная ставка от 0,3% до 0,5% в день. ПСК от 109,5% до 182,5% годовых. ООО \"100/500\", ОГРН 1125543051215, г. Омск. Режим работы: с 9:00 до 21:00. Тел.: +7 (913) 686-08-42.",
    "Займы под залог бытовой техники и электроники. Принимаем телевизоры, холодильники, стиральные машины. Сумма займа от 2 000 до 150 000 рублей, срок от 15 до 120 дней. Процентная ставка 0,35% в день (127,75% годовых). ООО \"АВАНС\", ОГРН 1124345013330, г. Киров. Режим работы: с 8:00 до 22:00. Сайт: http://ломбард43.рф",
    "Займы под залог мобильных телефонов и планшетов. Оцениваем технику до 80% от рыночной стоимости. Сумма займа от 500 до 50 000 рублей. Процентная ставка 0,4% в день (146% годовых). ООО \"999\", ОГРН 1155476061102, г. Новосибирск. Режим работы: с 9:00 до 20:00. Тел.: +7 (913) 948-20-23.",

    # ========== АВТОМОБИЛИ (ПТС) - РАЗНЫЕ УСЛОВИЯ ==========
    "ОЦЕНИВАЙТЕ СВОИ ФИНАНСОВЫЕ ВОЗМОЖНОСТИ И РИСКИ. Займы под залог ПТС (транспортного средства). Сумма займа от 50 000 до 1 000 000 рублей, сроком от 10 дней до 12 месяцев. Процентная ставка от 0,15% до 0,23% в день (от 54% до 84% годовых). ПСК от 54% до 84% годовых. ООО \"АВТО ЛОМБАРД\", ОГРН 1165029053936, г. Мытищи. Режим работы: с 8:00 до 22:00. Сайт: http://www.automobile-lombard.ru",
    "Займ под залог ПТС: срок от 3 до 12 месяцев, ставка 0,21% в день (76,65% годовых), сумма от 50 000 до 500 000 рублей. Автомобиль остается в пользовании. ООО \"АВТО ЛОМБАРД «АТЛАНТАВТО»\", ОГРН 1207700168972, г. Москва. Режим работы: с 9:00 до 21:00. Тел.: +7 (495) 968-27-76.",
    "Займы под залог автомобиля (ПТС остается у заемщика). Сумма займа от 20 000 до 2 000 000 рублей, срок от 30 дней до 12 месяцев. Процентная ставка от 0,18% до 0,25% в день. ООО \"АВТО ЛОМБАРД «ПЛАН Б»\", ОГРН 1167746143212, г. Москва. Режим работы: с 8:00 до 23:00. Сайт: https://www.autolombard-moskva.ru/",

    # ========== УНИВЕРСАЛЬНЫЕ (РАЗНЫЕ ТИПЫ ЗАЛОГОВ) ==========
    "Займы предоставляются на сумму от 500 до 500 000 рублей, по ставке от 0% до 365,0% годовых. Наличие паспорта и регистрации на территории РФ обязательно. Займы под залог: золота, техники, шуб. ООО \"999\", ОГРН 1162651074960, г. Кисловодск. Режим работы: с 9:00 до 21:00. Тел.: +7 (928) 373-07-07.",
    "Займ под залог движимого имущества предоставляется гражданам РФ, ставка от 0,3% до 1% в день, на срок от 15 до 30 календарных дней, на сумму от 1 рубля до 1 млн рублей. ПСК от 109,5% до 365% годовых. ООО \"АВАНГАРД\", ОГРН 1212200005676, г. Барнаул. Режим работы: с 8:00 до 22:00. Тел.: +7 (962) 822-65-15.",
    "Займы под залог различных видов имущества: золото, серебро, шубы, техника, часы. Сумма займа от 1 000 до 1 000 000 рублей, срок от 7 до 365 дней. Процентная ставка от 0,2% до 0,4% в день. ООО ЛОМБАРД \"24 КАРАТА\", ОГРН 1182468024815, г. Лесосибирск. Режим работы: с 9:00 до 20:00. Тел.: +7 (913) 006-80-11.",

    # ========== С АКЦИЯМИ И СПЕЦИАЛЬНЫМИ УСЛОВИЯМИ ==========
    "АКЦИЯ: Займы предоставляются ООО \"999\" и ООО ЛОМБАРД \"999\". Акция для впервые обратившихся клиентов. Обеспечение: предмет залога оценочной стоимостью не менее суммы займа. ООО \"999\", ОГРН 5177746003925, г. Москва. Режим работы: с 8:00 до 22:00. Тел.: +7 (926) 021-49-99.",
    "СПЕЦИАЛЬНОЕ ПРЕДЛОЖЕНИЕ: При оформлении залога в выходной день первые 3 дня проценты не начисляются. Займ предоставляется под залог ювелирных изделий, техники, шуб. Сумма займа от 100 до 600 000 рублей. ООО ЛОМБАРД \"999.9\", ОГРН 1177746100674, г. Москва. Режим работы: с 9:00 до 21:00. Тел.: +7 (926) 307-99-08.",
    "АКЦИЯ \"ДЕНЬ РОЖДЕНИЯ\": Специальные условия для именинников. Займы под залог золота, техники. ООО \"9999 ЛОМБАРД\", ОГРН 1092801001358, г. Благовещенск. Режим работы: с 9:00 до 20:00. Тел.: +7 (914) 538-91-70.",

    # ========== С ЛЬГОТНЫМИ УСЛОВИЯМИ ДЛЯ ПЕНСИОНЕРОВ ==========
    "Льготные условия для пенсионеров: займ «Забота» срок 35 дней, ставка 0,95% в день, сумма от 500 до 30 000 рублей; требуется пенсионное удостоверение. ООО \"АВТО ЛОМБАРД 71\", ОГРН 1190327015119, г. Улан-Удэ. Режим работы: с 8:00 до 22:00. Тел.: +7 (301) 243-34-45.",
    "Специальная программа для пенсионеров: сниженная процентная ставка, увеличенный срок займа. Займы под залог ювелирных изделий и техники. ООО \"АВАНГАРД\", ОГРН 1241600030242, г. Нурлат. Режим работы: с 9:00 до 21:00. Тел.: +7 (987) 297-32-10.",

    # ========== С ПОДРОБНЫМИ УСЛОВИЯМИ ПО СУММАМ ==========
    "Займы под залог движимого имущества. Сумма займа от 1 000 до 1 000 000 рублей. Процентная ставка: при сумме до 5 000 рублей — 0,35% в день, от 5 000 до 10 000 рублей — 0,32%, от 10 000 до 50 000 рублей — 0,25%, от 50 000 до 100 000 рублей — 0,2%, от 100 000 до 1 000 000 рублей — 0,18%. ПСК от 65,7% до 127,75% годовых. ООО \"АВАНС ЛОМБАРД\", ОГРН 1165958092618, г. Пермь. Режим работы: с 9:00 до 20:00. Тел.: +7 (902) 471-36-33.",

    # ========== РЕГИОНАЛЬНЫЕ (С УКАЗАНИЕМ РЕГИОНА) ==========
    "ООО \"СТАРЫЙ\", ОГРН 1023102367639, Белгородская обл., г. Старый Оскол. Займы под залог движимого имущества. Режим работы: с 9:00 до 20:00. Тел.: +7 (472) 544-22-50. Email: starylombard@yandex.ru",
    "ООО ЛОМБАРД \"22 РЕГИОН\", ОГРН 1122208001332, Алтайский край, г. Новоалтайск. Сайт: www.lombard22rus.ru. Займы предоставляются под залог ювелирных изделий, техники. Режим работы: с 8:00 до 22:00. Тел.: +7 (952) 001-41-41.",
    "ООО \"ПЕНЗА-АВТО-ЛОМБАРДЪ\", ОГРН 1095837003217, Пензенская обл., г. Пенза. Займы под залог транспортных средств и другого имущества. Режим работы: с 9:00 до 21:00.",

    # ========== С ПОДРОБНОЙ ЮРИДИЧЕСКОЙ ИНФОРМАЦИЕЙ ==========
    "ООО \"ФИНАНСОВЫЕ УСЛУГИ\", ОГРН 1187746981784, ИНН 7743284490. Юридический адрес: г. Москва, пер. 2-Й Лихачёвский, д.1, стр.11, эт.3 П XIII к.10 оф.20. Займы предоставляются под залог движимого имущества. Сумма займа от 1 000 до 1 000 000 рублей, срок от 7 до 365 дней, процентная ставка от 0,18% до 0,4% в день. Подробная информация на сайте. Режим работы: с 9:00 до 21:00. Тел.: +7 (925) 856-39-29. Не является публичной офертой.",
    "ООО \"А-ЭКСПРЕСС\", ОГРН 1185074000308, ИНН 5036169610. Адрес: Московская обл., г. Подольск, ул. Рабочая, д.36, пом.3. Займы под залог автомобилей и другого имущества. Режим работы: с 8:00 до 23:00. Тел.: +7 (910) 478-47-79. Email: i.zubkov@lkautoexpress.ru",

    # ========== АВТОЛОМБАРДЫ (СПЕЦИАЛИЗИРОВАННЫЕ) ==========
    "ООО \"АВТО ЛОМБАРД ГАРАНТ\", ОГРН 1236100032167, г. Ростов-На-Дону. Специализированный автоломбард. Займы под залог ПТС. Сумма до 2 000 000 рублей. Быстрая оценка. Режим работы: с 9:00 до 21:00. Тел.: +7 (938) 111-73-73.",
    "ООО \"АВТО ЛОМБАРД ВАДИО\", ОГРН 1157847012564, г. Санкт-Петербург. Профессиональная оценка автомобилей. Займы под залог ПТС без удержания автомобиля. Сайт: www.vadio.ru. Режим работы: с 9:00 до 21:00. Тел.: +7 (812) 980-41-41.",
    "ООО \"ААА ЛОМБАРД КАЗАНЬ\", ОГРН 1195543012642. Специализация: займы под залог автомобилей. Сайт: https://autolombardkazan.ru/. Быстрое оформление. Режим работы: с 8:00 до 22:00. Тел.: +7 (995) 133-64-62.",
    "ООО \"ААА ЛОМБАРД МОСКВА\", ОГРН 1185543014260. Займы под залог автомобилей в Москве. Сайт: займподптсвмоскве.рф. Сумма от 50 000 до 5 000 000 рублей. Режим работы: с 9:00 до 21:00. Тел.: +7 (965) 311-22-88.",

    # ========== С УСЛОВИЯМИ ДЛЯ РАЗНЫХ ТИПОВ ЗАЛОГОВ В ОДНОМ ==========
    "Займы под залог: 1) Золота и ювелирных изделий (сумма от 5 000 до 500 000 руб., ставка 0,2% в день); 2) Шуб из натурального меха (от 10 000 до 300 000 руб., ставка 0,25% в день); 3) Цифровой техники (от 1 000 до 100 000 руб., ставка 0,35% в день); 4) Автомобилей по ПТС (от 50 000 до 1 000 000 руб., ставка 0,21% в день). ООО \"АВТО ЛОМБАРД ЛИДЕР\", ОГРН 1233800024017, г. Иркутск. Режим работы: с 8:00 до 23:00. Тел.: +7 (908) 640-90-32.",

    # ========== СТАНДАРТНЫЕ (ДЛЯ МАССОВОГО ИСПОЛЬЗОВАНИЯ) ==========
    "ООО \"АВТО ЛОМБАРД\", ОГРН 1231400000149, г. Нерюнгри. Займы под залог движимого имущества. Режим работы: с 9:00 до 20:00. Тел.: +7 (914) 242-21-65. Email: avto-lombard14@yandex.ru",
    "ООО \"АВТО ЛОМБАРД\", ОГРН 1236300029536, г. Тольятти. Займы под залог автомобилей и другого имущества. Сайт: https://zalogavto24.ru. Режим работы: с 8:00 до 22:00. Тел.: +7 (987) 437-19-11.",
    "ООО \"АВТО ЛОМБАРД ИНВЕСТ\", ОГРН 1231600050384, г. Казань. Займы под залог различных видов имущества. Режим работы: с 9:00 до 21:00. Тел.: +7 (962) 559-70-07.",

    # ========== ДЛИННЫЕ И ПОДРОБНЫЕ (ПОЛНЫЕ УСЛОВИЯ) ==========
    "ВНИМАНИЕ! ОЦЕНИВАЙТЕ СВОИ ФИНАНСОВЫЕ ВОЗМОЖНОСТИ И РИСКИ. ООО \"А7 ЗАЙМ\", ОГРН 1091902000651, ИНН 1902022460, юридический адрес: г. Абакан, пр-кт Ленина, д.218М, стр.1, оф.203. Займы предоставляются под залог движимого имущества гражданам РФ от 18 лет. Сумма займа: от 1 000 до 1 000 000 рублей. Срок займа: от 7 до 365 дней. Процентная ставка: от 0,15% до 0,4% в день в зависимости от суммы и типа залога. Полная стоимость займа (ПСК): от 54,75% до 146% годовых. Требуемые документы: паспорт гражданина РФ. Автомобиль остается у заемщика при займе под залог ПТС. Льготный период погашения: 30 дней. Режим работы: пн-вс с 9:00 до 21:00. Контакты: тел. +7 (390) 226-40-80, сайт a7zaim.ru, email: karak7@list.ru. Информация носит ознакомительный характер и не является публичной офертой.",
]

# -----------------------------------------------------------------------------
# 4. ШАБЛОНЫ НАИМЕНОВАНИЙ ЮРЛИЦ
# -----------------------------------------------------------------------------
LEGAL_ENTITY_TEMPLATES = [
    "ООО «Ломбард «Удача»»",
    "ООО «Городской Ломбард»",
    "АО «Авто-Ломбард Премиум»",
    "ООО «Ювелирный Ломбард»",
    "ООО «Ломбард «Капитал»»",
    "АО «Сеть ломбардов «585»»",
    "ООО «Ломбард «Финансовая помощь»»",
    "ООО «Ломбард «Золотой телец»»",
]

# -----------------------------------------------------------------------------
# 5. ШАБЛОНЫ ИСТОЧНИКОВ ИНФОРМАЦИИ
# -----------------------------------------------------------------------------
SOURCE_INFO_TEMPLATES = [
    "Подробная информация на сайте www.example.ru и по тел. +7 (495) 123-45-67",
    "Ознакомиться с правилами: www.example.ru, тел. 8-800-123-45-67",
    "Информация об условиях на сайте www.example.ru. Телефон: +7 (495) 123-45-67",
    "Полные условия и раскрытие информации: www.example.ru, 8-800-123-45-67",
    "Сайт www.example.ru. Тел. +7 (495) 123-45-67. Режим работы: с 9:00 до 21:00",
]

# -----------------------------------------------------------------------------
# 6. СТИЛИ ОФОРМЛЕНИЯ (ближе к финансовым - navy, gold, corporate)
# -----------------------------------------------------------------------------
LOMBARD_STYLES = [
    {"name": "navy_gold", "headline_color": (212, 175, 55), "text_color": (255, 250, 240), "accent_color": (255, 215, 0), "shadow_color": (30, 20, 0), "shadow_opacity": 200},
    {"name": "corporate_blue", "headline_color": (70, 130, 180), "text_color": (240, 248, 255), "accent_color": (100, 149, 237), "shadow_color": (25, 25, 112), "shadow_opacity": 180},
    {"name": "professional_dark", "headline_color": (255, 215, 0), "text_color": (255, 255, 255), "accent_color": (184, 134, 11), "shadow_color": (0, 0, 0), "shadow_opacity": 200},
    {"name": "elegant_gold", "headline_color": (218, 165, 32), "text_color": (255, 250, 240), "accent_color": (255, 215, 0), "shadow_color": (139, 69, 19), "shadow_opacity": 190},
]

# -----------------------------------------------------------------------------
# 7. СТИЛИ ФОНА ДИСКЛЕЙМЕРА
# -----------------------------------------------------------------------------
DISCLAIMER_BG_STYLES = [
    {"name": "standard", "type": "solid", "alpha": 150, "height_multiplier": 1.0, "color": (0, 0, 0), "description": "Стандартный полупрозрачный"},
    {"name": "opaque", "type": "solid", "alpha": 255, "height_multiplier": 1.0, "color": (0, 0, 0), "description": "Непрозрачный чёрный"},
    {"name": "gradient_soft", "type": "gradient", "alpha_bottom": 150, "alpha_top": 30, "height_multiplier": 1.5, "color": (0, 0, 0), "description": "Мягкий градиент"},
    {"name": "full_width_banner", "type": "solid", "alpha": 230, "height_multiplier": 1.2, "color": (15, 15, 25), "description": "Широкий баннер"},
]

# =============================================================================
# СЦЕНАРИИ ГЕНЕРАЦИИ ФОНОВ
# =============================================================================

# Сценарии БЕЗ людей (офисы, витрины, золото, техника)
LOMBARD_SCENARIOS_NO_PEOPLE = [
    {
        "name": "office_lombard",
        "prompt": "professional pawnshop office interior, modern counter with jewelry display cases, gold items on velvet, security cameras visible, clean organized space, warm professional lighting, business atmosphere, no people, 8k quality, corporate finance",
        "has_person": False,
    },
    {
        "name": "jewelry_display",
        "prompt": "luxury jewelry display case interior, gold rings and necklaces arranged on black velvet, professional lighting, elegant showcase, pawnshop atmosphere, no people, high quality, 8k",
        "has_person": False,
    },
    {
        "name": "tech_items",
        "prompt": "modern electronics display, smartphones, laptops, tablets arranged on clean surface, pawnshop counter, professional assessment area, soft lighting, no people, 8k quality",
        "has_person": False,
    },
    {
        "name": "gold_evaluation",
        "prompt": "professional gold evaluation desk, scales, magnifying glass, gold items on white surface, clean organized workspace, pawnshop office, natural lighting, no people, 8k",
        "has_person": False,
    },
    {
        "name": "vault_interior",
        "prompt": "secure pawnshop vault interior, safety deposit boxes, organized storage, professional security atmosphere, dim lighting, no people, 8k quality",
        "has_person": False,
    },
    {
        "name": "reception_area",
        "prompt": "modern pawnshop reception area, comfortable waiting chairs, information desk, professional signage, warm lighting, clean space, no people, 8k quality",
        "has_person": False,
    },
    {
        "name": "assessment_room",
        "prompt": "professional assessment room, evaluation tools, jewelry loupe, scales, organized workspace, pawnshop office, natural window lighting, no people, 8k quality",
        "has_person": False,
    },
    # Объект в нижнем углу (не у самого края), остальное — градиент/абстракция, без людей
    {
        "name": "car_lower_right_gradient",
        "prompt": "single realistic car, sedan, in lower right corner of frame, not touching edge, small margin from border, rest of image soft vertical gradient background, neutral grey to light grey, minimal abstract background, no people, photorealistic car, clean product shot, 8k, no text, no distortion",
        "has_person": False,
    },
    {
        "name": "car_lower_left_gradient",
        "prompt": "single realistic car, sedan, in lower left corner of frame, not touching edge, small margin from border, rest of image soft gradient background, beige to grey, minimal abstract, no people, photorealistic automobile, clean composition, 8k, no text, no distortion",
        "has_person": False,
    },
    {
        "name": "fridge_lower_corner_gradient",
        "prompt": "one realistic refrigerator, white or silver, placed in lower right corner, not at edge, margin from border, rest of frame soft gradient background blue-grey to white, abstract minimal background, no people, product photography style, sharp appliance, 8k, no distortion",
        "has_person": False,
    },
    {
        "name": "stove_lower_corner_gradient",
        "prompt": "single realistic kitchen stove, electric or gas, in lower left corner, not touching edge, rest of image soft gradient background grey to white, minimal abstract, no people, photorealistic appliance, clean shot, 8k, no distortion",
        "has_person": False,
    },
    {
        "name": "computer_tower_lower_corner_gradient",
        "prompt": "one realistic desktop computer tower, black or grey PC case, in lower right corner, small margin from edge, rest of frame soft gradient background dark grey to light, abstract minimal, no people, product shot, sharp details, 8k, no distortion",
        "has_person": False,
    },
    {
        "name": "wristwatch_lower_corner_gradient",
        "prompt": "single realistic wristwatch, metal bracelet or leather strap, in lower left corner, not at edge, rest of image soft gradient background neutral tone, minimal abstract, no people, product photography, sharp watch, 8k, no distortion",
        "has_person": False,
    },
    {
        "name": "rings_emerald_diamond_lower_corner_gradient",
        "prompt": "luxury detailed rings with emeralds and diamonds, gold or platinum setting, in lower right corner, not at edge, margin from border, rest of image soft gradient background neutral tone, minimal abstract, no people, jewelry product photography, sharp gemstones, 8k, no distortion",
        "has_person": False,
    },
    {
        "name": "rings_sapphire_diamond_lower_corner_gradient",
        "prompt": "expensive detailed rings with sapphires and diamonds, white gold or platinum, in lower left corner, not at edge, rest of image soft gradient background neutral tone, minimal abstract, no people, jewelry product shot, sharp precious stones, 8k, no distortion",
        "has_person": False,
    },
    {
        "name": "necklace_precious_stones_lower_corner_gradient",
        "prompt": "luxury necklace with precious stones, diamonds and colored gems, elegant chain, in lower right corner, not at edge, margin from border, rest of frame soft gradient background neutral tone, minimal abstract, no people, jewelry product photography, sharp details, 8k, no distortion",
        "has_person": False,
    },
    {
        "name": "laptop_lower_corner_gradient",
        "prompt": "one realistic laptop computer, closed or slightly open, in lower right corner, margin from border, rest soft gradient background light grey to white, abstract minimal, no people, clean product shot, 8k, no distortion",
        "has_person": False,
    },
    {
        "name": "car_lower_right_abstract",
        "prompt": "single realistic car in lower right corner, not at edge, rest 65 percent of image abstract soft shapes, blurred color fields, corporate style, no people, photorealistic car only, 8k, no text",
        "has_person": False,
    },
    {
        "name": "tv_or_monitor_lower_corner_gradient",
        "prompt": "one realistic flat screen TV or monitor, black bezel, in lower left corner, not touching edge, rest soft gradient background, minimal abstract, no people, product shot, 8k, no distortion",
        "has_person": False,
    },
]

# Сценарии С людьми (консультанты, оценщики)
LOMBARD_SCENARIOS_WITH_PEOPLE = [
    {
        "name": "consultant_right",
        "prompt": "professional pawnshop consultant in business attire, friendly smile, standing on right side, modern office background, jewelry display visible, person on right, space for text on left, professional portrait, 8k",
        "has_person": True,
        "person_position": "right",
    },
    {
        "name": "appraiser_left",
        "prompt": "experienced appraiser examining jewelry with loupe, professional woman in white coat, standing on left side, evaluation desk background, person on left, clean space on right, high quality, 8k",
        "has_person": True,
        "person_position": "left",
    },
    {
        "name": "manager_center",
        "prompt": "pawnshop manager at desk, confident businessman in suit, office interior, documents and jewelry visible, person in center lower half, space at top for text, corporate style, 8k",
        "has_person": True,
        "person_position": "center",
    },
    {
        "name": "consultant_desk",
        "prompt": "professional consultant sitting at desk, helping customer, modern pawnshop office, jewelry display cases in background, person on right, space on left, warm lighting, 8k quality",
        "has_person": True,
        "person_position": "right",
    },
    {
        "name": "appraiser_work",
        "prompt": "jewelry appraiser at work, examining gold item with magnifying glass, professional woman, evaluation tools on desk, person on left, office background, space on right, 8k",
        "has_person": True,
        "person_position": "left",
    },
    {
        "name": "manager_portrait",
        "prompt": "senior pawnshop manager, distinguished businessman in elegant suit, standing portrait, prestigious office interior, warm lighting, person on right, space for text on left, authoritative style, 8k",
        "has_person": True,
        "person_position": "right",
    },
    {
        "name": "consultant_helping",
        "prompt": "friendly consultant helping customer, professional woman in business attire, modern pawnshop interior, person in center, space around for text, professional atmosphere, 8k quality",
        "has_person": True,
        "person_position": "center",
    },
]

LOMBARD_SCENARIOS = LOMBARD_SCENARIOS_NO_PEOPLE + LOMBARD_SCENARIOS_WITH_PEOPLE

# =============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================================================================

def load_companies() -> Dict:
    """Загружает реальные компании из JSON."""
    if COMPANIES_JSON_PATH.exists():
        try:
            with open(COMPANIES_JSON_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def get_random_company() -> Optional[Dict]:
    """Возвращает случайную компанию из JSON."""
    companies = load_companies()
    if companies:
        name = random.choice(list(companies.keys()))
        company_data = companies[name]
        return {
            "name": name,
            "website": company_data.get("website", ""),
            "phone": company_data.get("phone", ""),
            "address": company_data.get("address", ""),
            "short_name": company_data.get("short_name", ""),
            "ogrn": company_data.get("ogrn", ""),
            "inn": company_data.get("inn", ""),
        }
    return None


def load_disclaimer_templates() -> List[Dict]:
    """Загружает шаблоны дисклеймеров из JSON (ключ 'disclaimers')."""
    global _disclaimer_templates_cache
    if _disclaimer_templates_cache is not None:
        return _disclaimer_templates_cache
    if not DISCLAIMER_TEMPLATES_PATH.exists():
        _disclaimer_templates_cache = []
        return []
    try:
        with open(DISCLAIMER_TEMPLATES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _disclaimer_templates_cache = data.get("disclaimers", data.get("discclaimers", []))
        return _disclaimer_templates_cache
    except Exception:
        _disclaimer_templates_cache = []
        return []


def format_disclaimer_template(template_str: str, company: Dict) -> str:
    """
    Подставляет в шаблон дисклеймера данные компании.
    Плейсхолдеры: {company_name}, {ogrn}, {inn}, {address}, {contacts}.
    """
    company_name = company.get("short_name") or company.get("name", "")
    address = company.get("address", "")
    ogrn = company.get("ogrn") or "—"
    inn = company.get("inn") or "—"
    phone = company.get("phone", "")
    website = (company.get("website") or "").replace("https://", "").replace("http://", "").rstrip("/")
    parts = []
    if phone:
        parts.append(f"тел. {phone}")
    if website:
        parts.append(f"сайт {website}")
    contacts = ", ".join(parts) if parts else "Подробности на сайте."
    return template_str.format(
        company_name=company_name,
        ogrn=ogrn,
        inn=inn,
        address=address,
        contacts=contacts,
    )


def get_random_disclaimer(company: Optional[Dict] = None, use_templates: bool = True) -> str:
    """
    Возвращает случайный дисклеймер.
    Если передан company и загружены шаблоны из JSON — подставляются данные компании.
    Иначе — случайный из статического списка LOMBARD_DISCLAIMERS.
    """
    if use_templates and company:
        templates = load_disclaimer_templates()
        if templates:
            block = random.choice(templates)
            template = block.get("template", "")
            variations = block.get("variations", [])
            choices = [template] + variations
            text = random.choice(choices)
            return format_disclaimer_template(text, company)
    return random.choice(LOMBARD_DISCLAIMERS)


def format_source_info(website: str, phone: str, address: str = "") -> str:
    """Форматирует источник информации для баннера."""
    site_clean = website.replace("https://", "").replace("http://", "").rstrip("/")
    if address:
        return f"Подробная информация на сайте {site_clean}, по тел. {phone}, адрес: {address}"
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
    """Возвращает случайный набор контента."""
    company = None
    if use_real_companies:
        company = get_random_company()
    
    if company:
        le = legal_entity or company["name"]
        ph = phone or company["phone"]
        web = website or company.get("website", "")
        addr = company.get("address", "")
        si = source_info or format_source_info(web, ph, addr)
    else:
        le = legal_entity or random.choice(LEGAL_ENTITY_TEMPLATES)
        ph = phone or generate_phone()
        web = website or "www.example.ru"
        si = source_info or random.choice(SOURCE_INFO_TEMPLATES).replace("www.example.ru", web)
    
    return {
        "headline": random.choice(LOMBARD_HEADLINES),
        "description": random.choice(LOMBARD_DESCRIPTIONS),
        "disclaimer": get_random_disclaimer(company=company),
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


class LombardBannerOverlay:
    """Наложение текста на баннер ломбарда."""

    REF_WIDTH = 1024
    REF_HEIGHT = 1024

    def __init__(self, layout=None, style=None, disclaimer_bg_style=None, validate=True):
        self.layout = layout or LAYOUTS[0]
        self.style = style or LOMBARD_STYLES[0]
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
            v = LombardValidator.validate(headline, description, disclaimer, legal_entity, source_info)
            if v["violations"]:
                raise ValueError(f"Нарушение ст. 28 ФЗ-38 / ФЗ-196: {v['violations']}")

        full_desc = description or random.choice(LOMBARD_DESCRIPTIONS)
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
            "disclaimer": max(11, int(14 * scale)),
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
            draw, (safe_left, safe_top), headline or random.choice(LOMBARD_HEADLINES),
            renderer.headline_font, self.style['headline_color'],
            shadow_offset=3, align="left", max_width=max_w, anchor="la",
        )
        line_y = safe_top + font_sizes["headline"] + int(img_height * 0.015)
        renderer.draw_decorative_line(draw, (safe_left, line_y), min(int(img_width * 0.15), max_w), self.style['accent_color'], thickness=3)

        # DESCRIPTION (включая legal_entity и source_info)
        desc_y = int(img_height * 0.35)
        desc_max_w = int(img_width * 0.5)
        desc_height = renderer.draw_text_with_shadow(
            draw, (safe_left, desc_y), full_desc, renderer.text_font, self.style['text_color'],
            shadow_offset=2, align="left", max_width=desc_max_w, anchor="la",
        )

        # PHONE - размещаем ниже описания с отступом
        phone_text = phone or generate_phone()
        phone_spacing = int(font_sizes["text"] * 1.8)
        ph_y = desc_y + desc_height + phone_spacing
        
        max_phone_y = safe_bottom - font_sizes["disclaimer"] * 5 - font_sizes["phone"]
        ph_y = min(ph_y, max_phone_y)
        
        phone_bbox = renderer.phone_font.getbbox(phone_text)
        phone_width = phone_bbox[2] - phone_bbox[0]
        
        renderer.draw_text_with_shadow(
            draw, (safe_left, ph_y), phone_text,
            renderer.phone_font, self.style['headline_color'],
            shadow_offset=2, align="left", anchor="la",
        )
        
        phone_info = {
            "x": safe_left,
            "y": ph_y,
            "width": phone_width,
            "height": font_sizes["phone"],
            "text": phone_text,
        }

        # DISCLAIMER
        disc_y = safe_bottom - font_sizes["disclaimer"] * 4
        disc_max_w = int(img_width * 0.9)
        bg_style = self.disclaimer_bg_style or get_random_disclaimer_bg_style()
        image = self._draw_disclaimer_background(image, disc_y, bg_style)
        draw = ImageDraw.Draw(image)
        disc_text_y = disc_y + int(font_sizes["disclaimer"] * 0.5)
        renderer.draw_text_with_shadow(
            draw, (img_width // 2, disc_text_y), disclaimer or random.choice(LOMBARD_DISCLAIMERS),
            renderer.disclaimer_font, (255, 255, 255),
            shadow_offset=1, align="center", max_width=disc_max_w, anchor="ma",
        )
        
        # Накладываем логотипы после телефона (если включено и телефон в формате +7)
        if add_phone_logos and phone_info["text"].startswith("+7"):
            logo_height = int(font_sizes["phone"] * 1.5)
            n_logos = random.randint(0, 2)
            
            if n_logos > 0:
                logos = _load_contact_logos(favicons_dir or str(LOGO_FOR_QR_DIR), logo_height, n_logos)
                
                if logos:
                    logo_x = phone_info["x"] + phone_info["width"] + int(font_sizes["phone"] * 0.3)
                    logo_y = phone_info["y"] + int((phone_info["height"] - logo_height) / 2)
                    
                    logo_spacing = max(4, logo_height // 6)
                    cursor_x = logo_x
                    
                    for logo_im in logos:
                        lw, lh = logo_im.size
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
    parser = argparse.ArgumentParser(description="Lombard Banner Overlay")
    parser.add_argument("--image", type=str, required=True)
    parser.add_argument("--output", type=str, default="output/lombard")
    args = parser.parse_args()
