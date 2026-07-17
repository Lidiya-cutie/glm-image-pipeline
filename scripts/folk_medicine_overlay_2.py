#!/usr/bin/env python3
"""
Folk Medicine Ad Banner Overlay (Народная медицина)

Генерация рекламных баннеров услуг народной медицины
с учетом требований российского законодательства.
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

CONTACTS_LABEL = "Наши контакты:"
FOLK_MEDICINE_DOMAINS_CONTACTS = [
    "newnorma.ru", "namasteguru.ru", "vladimirosipov-online.ru",
    "mariya-gadanie.tilda.ws", "travogor.ru", "happy4woman.ru",
    "sujokonline.ru", "velarinka.ru", "buraev.ru", "osteopatik.ru",
    "массаж-пента.рф", "clinic-amrita.ru", "tibetspb.ru", "life-plus.online", "brahmaspb.com",
    "insam.spb.ru", "ayurvedakamala.ru", "medi-cn.ru", "ayurdara.ru", "medfolk.ru",
]
LOGO_FOR_QR_DIR = Path("/mldata/logo_for_qr_extracted")

def _load_contact_logos(max_count=10):
    if not LOGO_FOR_QR_DIR.exists():
        return []
    exts = {".png", ".jpg", ".jpeg"}
    logos = [p for p in LOGO_FOR_QR_DIR.iterdir() if p.suffix.lower() in exts and p.is_file()]
    return logos[:max_count] if logos else []

# =============================================================================
# Legal Compliance
# =============================================================================

MANDATORY_DISCLAIMER_1 = "ИМЕЮТСЯ ПРОТИВОПОКАЗАНИЯ"
MANDATORY_DISCLAIMER_2 = "НЕОБХОДИМА КОНСУЛЬТАЦИЯ СПЕЦИАЛИСТА"

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
    r"иглоукалывание",
    r"акупунктура",
    r"костоправ",
]

class FolkMedicineValidator:
    @staticmethod
    def check_medical_indicators(text: str) -> List[str]:
        text_lower = text.lower()
        issues = []
        for pattern in MEDICAL_SERVICE_INDICATORS:
            if re.search(pattern, text_lower):
                match = re.search(pattern, text_lower)
                issues.append(f"Признак мед. услуги: '{match.group()}'")
        return issues

    @staticmethod
    def check_folk_medicine_context(text: str) -> bool:
        text_lower = text.lower()
        for pattern in FOLK_MEDICINE_KEYWORDS:
            if re.search(pattern, text_lower):
                return True
        return False

    @staticmethod
    def check_disclaimers(text: str) -> Dict[str, bool]:
        text_upper = text.upper()
        return {
            "has_contraindications": "ПРОТИВОПОКАЗАНИ" in text_upper,
            "has_consultation": "КОНСУЛЬТАЦИ" in text_upper and "СПЕЦИАЛИСТ" in text_upper,
        }

    @staticmethod
    def validate(headline: str, description: str, disclaimer: str) -> Dict[str, Any]:
        full_text = f"{headline} {description} {disclaimer}"
        medical_issues = FolkMedicineValidator.check_medical_indicators(full_text)
        has_folk_context = FolkMedicineValidator.check_folk_medicine_context(f"{headline} {description}")
        disclaimer_check = FolkMedicineValidator.check_disclaimers(disclaimer)
        
        warnings = []
        if not has_folk_context:
            warnings.append("Отсутствует явный контекст народной медицины")
        if not disclaimer_check["has_contraindications"]:
            warnings.append("Отсутствует дисклеймер ПРОТИВОПОКАЗАНИЯ")
        if not disclaimer_check["has_consultation"]:
            warnings.append("Отсутствует дисклеймер КОНСУЛЬТАЦИЯ СПЕЦИАЛИСТА")
        
        valid = (len(medical_issues) == 0 and 
                 disclaimer_check["has_contraindications"] and 
                 disclaimer_check["has_consultation"])
        
        return {
            "valid": valid,
            "has_folk_context": has_folk_context,
            "medical_issues": medical_issues,
            "disclaimer_check": disclaimer_check,
            "warnings": warnings,
        }

# =============================================================================
# Насыщенный тематический контент
# =============================================================================

FOLK_MEDICINE_HEADLINES = [
    "Народный целитель", "Потомственный знахарь", "Прием экстрасенса",
    "Ясновидящая помощь", "Гадание на Таро", "Шаманские практики",
    "Древние методы исцеления", "Лечение травами", "Фитотерапия",
    "Биоэнергетический массаж", "Энерготерапия и рейки", "Исцеляющие молитвы",
    "Заговоры на здоровье", "Мастер акупунктуры", "Традиционный костоправ",
    "Чтение древних рун", "Тибетские поющие чаши", "Ведический ритуал"
]

FOLK_MEDICINE_DESCRIPTIONS = [
    # Целители и знахари
    "Приём ведёт потомственный целитель в 7-м поколении",
    "Индивидуальный подход к каждому посетителю \nДревние знания и природные методы",
    "Приём ведёт потомственный целитель в 7-м поколении \nПередача тайных знаний от предков \nПроверенные временем техники диагностики",
    "Проверенные временем техники диагностики \nИсцеление не только тела, но и рода",
    "Индивидуальные обряды для вашего случая \nМудрость, накопленная веками",
    "Индивидуальный подход к каждому посетителю \nДиагностика по уникальным признакам \nПерсональный план восстановления",
    "Учёт вашей истории и особенностей \nАдаптация методов под ваши ритмы \nПостоянная поддержка на пути к здоровью",
    "Древние знания и природные методы \nСимбиоз мудрости Востока и Запада \nСила целительных трав и минералов",
    "Ритуалы, согласованные с циклами природы \nПробуждение внутреннего целителя \nПуть к гармонии через естественные законы",

    # Экстрасенсы и биоэнергетика
    "Диагностика биополя и энергетических блоков",
    "Выявление причин недомоганий на тонком уровне",
    "Работа с аурой и энергетическими центрами",
    "Диагностика биополя и энергетических блоков \nВизуализация разрывов и искажений ауры \nВыявление подсознательных программ",
    "Очистка от энергетических привязок \nВосстановление целостности светового тела \nКарта энергетического здоровья",
    "Выявление причин недомоганий на тонком уровне \nПоиск корня болезни в прошлых событиях \nРабота с кармическими узлами и долгами",
    "Связь физических симптомов с эмоциональными блоками \nДиагностика влияния окружающих людей \nРасшифровка сигналов вашего высшего «Я»",
    "Работа с аурой и энергетическими центрами \nСбалансирование семи основных чакр \nЗарядка и уплотнение энергетической оболочки",
    "Техники цветокоррекции ауры \nОткрытие каналов для потока жизненной силы \nАктивация спящих энергоцентров",

    # Гадание, Таро и Руны
    "Гадание на Таро, рунах, кофейной гуще",
    "Раскрытие прошлого, настоящего и будущего",
    "Линии судьбы расскажут о вашем пути",
    "Гадание на Таро, рунах, кофейной гуще: \nАрхетипы Таро раскроют сюжет вашей жизни \nДревние символы рун укажут верное направление",
    "Узоры на гуще расскажут о скрытых переменах \nСинтез методов для максимальной точности \nКлючи к пониманию знаков судьбы",
    "Раскрытие прошлого, настоящего и будущего: \nПонять уроки, данные вашими предками \nУвидеть истинные причины текущих ситуаций",
    "Рассмотреть вероятные ветки развития событий \nНайти точки приложения силы для изменений \nСоединить времена в единую линию смысла",
    "Линии судьбы расскажут о вашем пути \nУвидите скрытые возможности \nРаспознаете поворотные точки \nПоймёте язык сердца",
    "Откроете ресурсы для реализации \nОбретёте ясность здесь и сейчас",

    # Шаманы и духовные практики
    "Шаманские ритуалы очищения и защиты",
    "Связь с духами природы и предков",
    "Тибетские поющие чаши и благовония",
    "Шаманские ритуалы очищения и защиты \nИзгнание негативных сущностей и влияний \nСоздание сильного личного обережного поля",
    "Очищение дома и пространства от старой энергии \nБлагословение на новые начинания \nСвязь с духом-хранителем для совета",
    "Связь с духами природы и предков \nПутешествия в нижний и верхний миры за советом \nПолучение силы от тотемных животных",
    "Медитации у священных мест силы \nИспользование голоса и бубна \nРитуалы благодарения стихий",
    "Тибетские поющие чаши и благовония \nГлубокий массаж звуком на клеточном уровне \nСнятие ментальных и эмоциональных зажимов",
    "Синхронизация биоритмов с вибрациями чаш \nОчищение пространства ароматами смол и трав \nПогружение в состояние медитативного покоя",

    # Траволечение и натуропатия
    "Авторские травяные сборы по старинным рецептам",
    "Только экологически чистые травы из Алтая",
    "Фитотерапия для гармонии тела и духа",
    "Авторские травяные сборы по старинным рецептам \nУникальные комбинации, известные лишь избранным \nСекретные пропорции для усиления эффекта",
    "Сбор в определённые лунные дни и часы \nНастои, отвары, мази и обережные мешочки \nПередача рецепта только доверившемуся",
    "Только экологически чистые травы из Алтая \nСила растений, выросших в местах силы \nРучной сбор с соблюдением древних традиций",
    "Отсутствие промышленного загрязнения и химии \nЭнергетика первозданной природы в каждой травинке \nПодарок от сердца гор и чистых рек",
    "Фитотерапия для гармонии тела и духа: \nТравы для успокоения ума и ясности мысли \nРастения, укрепляющие дух и волю",
    "Сборы для очищения физического и тонкого тел \nЧайные церемонии как медитативная практика \nПуть к целостности через царство растений",

    # Массаж, костоправство и телесные практики
    "Массаж с раскрытием чакр и меридианов",
    "Восстановление энергетического баланса",
    "Рейки-сеансы для глубокой релаксации",
    "Массаж с раскрытием чакр и меридианов \nРабота с биоактивными точками для запуска энергии \nПроработка энергетических каналов (нади)",
    "Снятие блоков, мешающих свободному течению энергии \nСочетание тактильного воздействия с визуализацией \nПробуждение жизненной силы и чувства внутреннего света",
    "Восстановление энергетического баланса \nВыравнивание переизбытка или недостатка энергии \nГармонизация взаимодействия Инь и Ян",
    "Заземление и наполнение силой Земли и Неба \nТехники для самостоятельного поддержания баланса \nОщущение внутренней целостности и спокойной силы",
    "Рейки-сеансы для глубокой релаксации: \nПередача универсальной жизненной энергии \nИнициация в канал Рейки для самопомощи",
    "Традиционное костоправство и правка тела \nСтаринные методы работы с суставами и позвоночником \nВозвращение природной гибкости и легкости движений",

    # Акупунктура (иглоукалывание)
    "Древнее искусство иглоукалывания по точкам",
    "Сеансы акупунктуры \nАктивация внутренних резервов организма \nРабота с биоактивными точками для запуска энергии \nПробуждение жизненной силы",
    "Работа с тонкими серебряными иглами \nВосстановление движения энергии по меридианам \nСнятие вековых зажимов и напряжения",

    # Общие
    "Предварительная запись обязательна",
    "Опыт практики более 20 лет",
    "Положительные отзывы благодарных посетителей",
]

FOLK_MEDICINE_DISCLAIMERS = [
    "ИМЕЮТСЯ ПРОТИВОПОКАЗАНИЯ. НЕОБХОДИМА КОНСУЛЬТАЦИЯ СПЕЦИАЛИСТА. Не является медицинской услугой.",
    "ИМЕЮТСЯ ПРОТИВОПОКАЗАНИЯ. НЕОБХОДИМА КОНСУЛЬТАЦИЯ СПЕЦИАЛИСТА. Услуги народной медицины.",
    "ВНИМАНИЕ! ИМЕЮТСЯ ПРОТИВОПОКАЗАНИЯ. НЕОБХОДИМА КОНСУЛЬТАЦИЯ СПЕЦИАЛИСТА перед посещением.",
]

# =============================================================================
# Обновленные сценарии генерации фонов
# =============================================================================

FOLK_MEDICINE_SCENARIOS_NO_PEOPLE = [
    {
        "name": "acupunct_items",
        "prompt": "extreme close-up macro photography of realistic professional acupuncture needles, stainless steel shafts with copper wire-wound handles, needles arranged on a clean gray slate stone, traditional ceramic bowl with herbal tea, single white lotus flower, soft natural side lighting, shallow depth of field, sharp metallic texture, 8k resolution, photorealistic",
        "has_person": False,
    },
    {
        "name": "massage_room",
        "prompt": "serene massage room interior, light oak wood walls, glass shelves with amber oil bottles, monstera plant in ceramic pot, neatly folded white cotton towels, warm hidden LED lighting, professional spa atmosphere, 8k quality, realistic textures",
        "has_person": False,
    },
    {
        "name": "guru_cabinet",
        "prompt": "sacred meditation space interior, dark wood flooring, authentic Tibetan singing bowls on low altar, burgundy silk cushions, thangka wall art, sandalwood incense burner, soft golden lamp lighting, realistic shadows, 8k resolution",
        "has_person": False,
    },
    {
        "name": "modern_herbal_studio",
        "prompt": "modern herbalist studio interior, white brick wall background, light wooden worktable, white marble mortar and pestle, bundles of dried lavender and sage hanging on a wooden rail, neat rows of amber glass dropper bottles and clear jars with dried herbs, sun-drenched space with large window, natural sunlight with lens flare, clean minimalist aesthetic, no people, 8k resolution, professional lifestyle photography",
        "has_person": False,
    },
    {
        "name": "spiritism_symbols",
        "prompt": "mysterious séance room, wooden ouija board, large obsidian crystal ball on ebony stand, tarot cards fanned on purple velvet, black candles in brass holders, low dramatic lighting, heavy drapes, 8k resolution, cinematic atmosphere",
        "has_person": False,
    },
    {
        "name": "forest_herbs",
        "prompt": "wild forest clearing at dawn, medicinal herbs with morning dew, valerian and arnica flowers, mystical morning mist, sunlight rays through pine trees (god rays), wicker basket on mossy ground, realistic nature photography, 8k quality",
        "has_person": False,
    },
    {
        "name": "chakra_room",
        "prompt": "modern yoga studio interior, white walls, woven chakra wall hanging, meditation cushion on low platform, raw crystals on white linen (amethyst, quartz, citrine), soft diffused neutral lighting, harmonious and balanced energy, 8k resolution",
        "has_person": False,
    },
]

FOLK_MEDICINE_SCENARIOS_WITH_PEOPLE = [
    {
        "name": "acupuncturist_right",
        "prompt": "professional acupuncturist in white lab coat, focused expression, close-up of hands inserting a realistic thin silver needle into a meridian point, clean clinical studio, soft neutral lighting, person on the right, empty space on left for text, 8k resolution, photorealistic",
        "has_person": True,
        "person_position": "right",
    },
    {
        "name": "spiritual_teacher_left",
        "prompt": "elderly spiritual mentor with gray beard, seated in lotus position, ochre hand-woven robes, mudra gesture, brass bowl with incense, blurred temple background, peaceful atmosphere, person on the left, clean space on right, 8k quality",
        "has_person": True,
        "person_position": "left",
    },
    {
        "name": "clairvoyant_session",
        "prompt": "clairvoyant woman sitting at round table, face partially veiled, spreading hands over black scrying mirror, candlelit room, high contrast dramatic lighting, person in center, space on both sides for text, 16k resolution, cinematic style",
        "has_person": True,
        "person_position": "center",
    },
    {
        "name": "herbalist_lifestyle",
        "prompt": "young professional female naturopath in a beige linen apron over a white shirt, warm friendly smile, holding a terracotta pot with a fresh green aloe vera plant, standing in a bright sun-lit herbal studio, white brick walls, wooden shelves with apothecary jars and green plants in the background, soft golden hour sunlight, person on the left, clear white space on the right for text, 8k quality, realistic skin tones, sharp focus",
        "has_person": True,
        "person_position": "left",
    },
    {
        "name": "energy_healer_session",
        "prompt": "energy healer practitioner, hands hovering over relaxed patient on massage table, dim room with salt lamps, soft bioluminescent particles visualization, healing energy concept, central composition, negative space top and bottom, 16k resolution",
        "has_person": True,
        "person_position": "center",
    },
    {
        "name": "runemaster_right",
        "prompt": "Nordic seer woman with braids in woolen shawl, throwing hand-carved wooden runes onto wolf pelt, fireplace lighting, dark primal room, shelves with antlers and feathers, person on the right, atmospheric space on left, 16k quality",
        "has_person": True,
        "person_position": "right",
    },
    {
        "name": "bone_setter_center",
        "prompt": "traditional folk healer man, experienced hands manipulating client's shoulder, humble cottage interior background, herbal poultices in bowl, gritty realistic detail, tight focus on action, space at top for text, 16k resolution",
        "has_person": True,
        "person_position": "center",
    }
]

FOLK_MEDICINE_SCENARIOS = FOLK_MEDICINE_SCENARIOS_NO_PEOPLE + FOLK_MEDICINE_SCENARIOS_WITH_PEOPLE

# =============================================================================
# Оформление
# =============================================================================

DISCLAIMER_BG_STYLES = [
    {"name": "standard", "type": "solid", "alpha": 150, "height_multiplier": 1.0, "color": (0, 0, 0)},
    {"name": "opaque", "type": "solid", "alpha": 255, "height_multiplier": 1.0, "color": (0, 0, 0)},
    {"name": "gradient_soft", "type": "gradient", "alpha_bottom": 150, "alpha_top": 30, "height_multiplier": 1.5, "color": (0, 0, 0)},
    {"name": "full_width_banner", "type": "solid", "alpha": 230, "height_multiplier": 1.2, "color": (15, 15, 25)},
]

FOLK_MEDICINE_STYLES = [
    {"name": "gold", "headline_color": (212, 175, 55), "text_color": (255, 250, 240), "accent_color": (255, 215, 0), "shadow_color": (30, 20, 0), "shadow_opacity": 200},
    {"name": "mystic_purple", "headline_color": (200, 160, 255), "text_color": (240, 230, 255), "accent_color": (180, 140, 230), "shadow_color": (20, 10, 40), "shadow_opacity": 200},
    {"name": "earth_green", "headline_color": (144, 190, 109), "text_color": (240, 255, 240), "accent_color": (120, 160, 90), "shadow_color": (10, 30, 10), "shadow_opacity": 180},
]

def generate_phone():
    """Генерирует случайный российский номер телефона."""
    return f"+7 ({random.randint(900, 999)}) {random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(10, 99)}"


def get_random_disclaimer_bg_style() -> Dict:
    """Возвращает случайный стиль фона для дисклеймера."""
    return random.choice(DISCLAIMER_BG_STYLES)


def get_random_content() -> Dict[str, str]:
    """Возвращает случайный набор контента для баннера."""
    return {
        "headline": random.choice(FOLK_MEDICINE_HEADLINES),
        "description": random.choice(FOLK_MEDICINE_DESCRIPTIONS),
        "disclaimer": random.choice(FOLK_MEDICINE_DISCLAIMERS),
    }


def get_layout_for_scenario(scenario: Dict) -> Dict:
    if not scenario.get("has_person"):
        return random.choice(LAYOUTS)
    position = scenario.get("person_position", "center")
    if position == "right":
        return get_layout_by_name("classic_left") or LAYOUTS[0]
    elif position == "left":
        return get_layout_by_name("classic_right") or LAYOUTS[1]
    else:
        layouts = [get_layout_by_name("top_bottom"), get_layout_by_name("diagonal")]
        return random.choice([l for l in layouts if l]) or LAYOUTS[0]

class FolkMedicineBannerOverlay:
    REF_WIDTH = 1024
    REF_HEIGHT = 1024

    def __init__(self, layout=None, style=None, disclaimer_bg_style=None, validate=True):
        self.layout = layout or LAYOUTS[0]
        self.style = style or FOLK_MEDICINE_STYLES[0]
        self.disclaimer_bg_style = disclaimer_bg_style
        self.validate = validate

    def _draw_disclaimer_background(self, image, disc_y, bg_style):
        img_width, img_height = image.size
        h_mult = bg_style.get('height_multiplier', 1.0)
        color = bg_style.get('color', (0, 0, 0))
        bg_type = bg_style.get('type', 'solid')
        actual_h = int((img_height - disc_y + 10) * h_mult)
        adj_y = max(0, img_height - actual_h)
        bg_layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(bg_layer)
        if bg_type == 'solid':
            draw.rectangle([0, adj_y, img_width, img_height], fill=(*color, bg_style.get('alpha', 150)))
        return Image.alpha_composite(image, bg_layer)

    def apply(self, image, headline=None, description=None, phone=None, disclaimer=None):
        headline = headline or random.choice(FOLK_MEDICINE_HEADLINES)
        description = description or random.choice(FOLK_MEDICINE_DESCRIPTIONS)
        phone = phone or generate_phone()
        disclaimer = disclaimer or random.choice(FOLK_MEDICINE_DISCLAIMERS)

        if self.validate:
            FolkMedicineValidator.validate(headline, description, disclaimer)

        if image.mode != 'RGBA': image = image.convert('RGBA')
        w, h = image.size
        scale = min(w, h) / self.REF_WIDTH
        renderer = TextRenderer(self.style, headline_size=int(58 * scale), text_size=int(28 * scale), phone_size=int(40 * scale), disclaimer_size=int(13 * scale))
        draw = ImageDraw.Draw(image)
        layout_name = self.layout.get("name", "classic_left")
        
        margin = int(w * 0.06)
        tx = margin if "left" in layout_name else w // 2 if "center" in layout_name else w - margin
        align = "left" if "left" in layout_name else "center" if "center" in layout_name else "right"

        renderer.draw_text_with_shadow(draw, (tx, margin), headline, renderer.headline_font, self.style['headline_color'], align=align, max_width=int(w * 0.6))
        renderer.draw_text_with_shadow(draw, (tx, h // 2.5), description, renderer.text_font, self.style['text_color'], align=align, max_width=int(w * 0.6))
        renderer.draw_text_with_shadow(draw, (tx, h // 1.4), phone, renderer.phone_font, self.style['headline_color'], align=align)

        disc_style = self.disclaimer_bg_style or random.choice(DISCLAIMER_BG_STYLES)
        image = self._draw_disclaimer_background(image, h - 80, disc_style)
        draw = ImageDraw.Draw(image)
        renderer.draw_text_with_shadow(draw, (w // 2, h - 60), disclaimer, renderer.disclaimer_font, (255, 255, 255), align="center", max_width=int(w * 0.9))

        return image

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=str)
    parser.add_argument("--output", type=str, default="output/folk_medicine")
    args = parser.parse_args()
    if args.image:
        img = Image.open(args.image)
        overlay = FolkMedicineBannerOverlay()
        res = overlay.apply(img)
        Path(args.output).mkdir(parents=True, exist_ok=True)
        res.save(Path(args.output) / "result.png")

if __name__ == "__main__":
    main()