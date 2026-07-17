# Баннеры ломбардов (ст. 28 ФЗ-38 и ФЗ-196)

Скрипты для генерации рекламных баннеров в категории **«Ломбарды»** с учётом требований ст. 28 ФЗ-38 «О рекламе» и ФЗ-196 «О ломбардах».

## Созданные файлы

| Файл | Назначение |
|------|------------|
| `lombard_overlay.py` | Валидатор, тексты, стили, сценарии фонов, загрузка дисклеймеров и компаний |
| `generate_lombard_banners.py` | Генерация фонов и баннеров (19 сценариев без людей + 7 с людьми) |
| `generate_lombard_clean_backgrounds.py` | Генерация чистых фонов без текста |
| `lombard_dual_composition.py` | Композиция из 2 изображений + текст + QR с разнообразными вариантами размещения |
| `lombard_companies.json` | Данные реальных ломбардов (названия, сайты, телефоны, адреса) |
| `lombard_disclaimer_templates.json` | Шаблоны дисклеймеров с подстановками {company_name}, {ogrn}, {inn}, {address}, {contacts} и вариантами формулировок |
| `lombard_comp.csv` | Исходный CSV файл с данными ломбардов (90+ компаний) |
| `convert_lombard_csv_to_json.py` | Скрипт для конвертации CSV в JSON |

## Форматы баннеров

- **Квадратный:** 1024×1024
- **Горизонтальный:** 1200×700
- **Вертикальный:** 800×1200

## Сценарии фонов

### Без людей (19)

**Интерьеры ломбарда (7):**
- `office_lombard` — профессиональный офис ломбарда с витринами
- `jewelry_display` — витрина с ювелирными изделиями
- `tech_items` — выставка цифровой техники
- `gold_evaluation` — стол для оценки золота
- `vault_interior` — внутреннее помещение хранилища
- `reception_area` — зона приёма клиентов
- `assessment_room` — комната для оценки предметов

**Объект в углу + градиент/абстракция (12):** объект в нижнем углу (не у края), остальная часть кадра — мягкий градиент или абстрактный фон.
- `car_lower_right_gradient` — автомобиль, нижний правый угол
- `car_lower_left_gradient` — автомобиль, нижний левый угол
- `car_lower_right_abstract` — автомобиль, нижний правый угол, абстрактный фон
- `fridge_lower_corner_gradient` — холодильник
- `stove_lower_corner_gradient` — плита
- `computer_tower_lower_corner_gradient` — системный блок ПК
- `wristwatch_lower_corner_gradient` — наручные часы
- `laptop_lower_corner_gradient` — ноутбук
- `tv_or_monitor_lower_corner_gradient` — ТВ/монитор
- `rings_emerald_diamond_lower_corner_gradient` — кольца с изумрудами и бриллиантами
- `rings_sapphire_diamond_lower_corner_gradient` — кольца с сапфирами и бриллиантами
- `necklace_precious_stones_lower_corner_gradient` — ожерелье с драгоценными камнями

### С людьми (7)
- `consultant_right` — консультант справа
- `appraiser_left` — оценщик слева
- `manager_center` — менеджер в центре
- `consultant_desk` — консультант за столом
- `appraiser_work` — оценщик за работой
- `manager_portrait` — портрет менеджера
- `consultant_helping` — консультант помогает клиенту

## Требования законодательства

### ✅ ОБЯЗАТЕЛЬНЫЕ ЭЛЕМЕНТЫ

1. **Наименование юридического лица** с обязательным словом **"Ломбард"**
   - ✅ Правильно: `ООО «Ломбард «Удача»»`
   - ❌ Неправильно: `ООО «Удача»` (без слова "Ломбард")

2. **Источник информации** (сайт, телефон, адрес)

3. **Режим работы** в пределах **8:00-23:00** (не круглосуточно!)
   - ✅ Правильно: "Режим работы: с 9:00 до 21:00"
   - ❌ Неправильно: "Круглосуточно" или "24 часа"

### ❌ ЗАПРЕЩЕНО

1. **Круглосуточная работа** (24 часа)
   - Согласно ст. 6 ФЗ-196, ломбарды могут работать только с 8:00 до 23:00

2. **Привлечение инвестиций/вкладов**
   - Ломбардам запрещено привлекать денежные средства физлиц

3. **Гарантированная оценка без оговорок**
   - Нельзя: "Лучшая оценка", "Самая высокая цена"

4. **Отсутствие ПСК** при указании процентных ставок
   - Если указана ставка, обязательно указывать Полную стоимость кредита (ПСК)

## Тексты (25+ формулировок)

Все тексты соответствуют чек-листу:
- ✅ Наименование юрлица с обязательным словом "Ломбард"
- ✅ Источник информации (сайт, телефон)
- ✅ Режим работы в пределах 8:00-23:00
- ❌ Без круглосуточной работы
- ❌ Без привлечения инвестиций
- ❌ Без гарантированных оценок

### Примеры заголовков:
- "Деньги под залог техники"
- "Займы под залог золота"
- "Нужны деньги? Оценка за 5 минут"
- "Мгновенная оценка и выдача"
- "Займы без кредитной истории"

### Примеры описаний:
- "Высокая оценка. Минимум документов. Нужен только паспорт."
- "Бережное хранение ваших вещей. Страхование залога за наш счёт."
- "Без справок о доходах и поручителей. Оформление за 15 минут."

## Стили оформления

4 стиля в финансовой/корпоративной тематике:
- `navy_gold` — тёмно-синий с золотым акцентом
- `corporate_blue` — корпоративный синий
- `professional_dark` — профессиональный тёмный
- `elegant_gold` — элегантное золото

## Примеры запуска

### Генерация баннеров с текстом

```bash
# Один баннер конкретного сценария
python scripts/generate_lombard_banners.py --scenario office_lombard

# Несколько сценариев по имени (через запятую), например только кольца и ожерелье
python scripts/generate_lombard_banners.py --scenarios "rings_emerald_diamond_lower_corner_gradient,rings_sapphire_diamond_lower_corner_gradient,necklace_precious_stones_lower_corner_gradient" --format horizontal --count 2 --output output/lombard_rings_test

# Все сценарии, горизонтальный формат
python scripts/generate_lombard_banners.py --all-scenarios --format horizontal --count 10

# Только сценарии с людьми
python scripts/generate_lombard_banners.py --with-people --output output/lombard_people

# Только сценарии без людей
python scripts/generate_lombard_banners.py --without-people --format vertical --count 5

# С QR-кодами (вероятность 70%)
python scripts/generate_lombard_banners.py --all-scenarios --qr-chance 70

# С логотипами после телефона
python scripts/generate_lombard_banners.py --all-scenarios --add-phone-logos --favicons-dir /mldata/logo_for_qr_extracted

# Dual composition (композиция из 2 фонов + текст + QR с разнообразными вариантами размещения)
python scripts/lombard_dual_composition.py --input-dir path/to/backgrounds --output output/lombard_dual --format horizontal --count 20 --qr-chance 60
```

### Генерация только фонов (без текста)

```bash
# Через основной скрипт (только фоны, без текста и дисклеймера)
python scripts/generate_lombard_banners.py --backgrounds-only --format square --all-scenarios

# Только сценарии с кольцами/ожерельем
python scripts/generate_lombard_banners.py --backgrounds-only --scenarios "rings_emerald_diamond_lower_corner_gradient,rings_sapphire_diamond_lower_corner_gradient,necklace_precious_stones_lower_corner_gradient" --format horizontal --count 1 --output output/lombard_rings_test

# Через отдельный скрипт для чистых фонов
python scripts/generate_lombard_clean_backgrounds.py --format horizontal --with-people --count 10

# Вертикальный формат, без людей
python scripts/generate_lombard_clean_backgrounds.py --format vertical --without-people --count 5
```

### Dual Composition (композиция из 2 фонов)

```bash
# Композиция из двух фоновых изображений с разнообразным размещением текста
python scripts/lombard_dual_composition.py --input-dir path/to/backgrounds --output output/lombard_dual --format horizontal --count 20

# С QR-кодами (вероятность 60%)
python scripts/lombard_dual_composition.py --input-dir path/to/backgrounds --output output/lombard_dual --format horizontal --count 20 --qr-chance 60

# Вертикальный формат
python scripts/lombard_dual_composition.py --input-dir path/to/backgrounds --output output/lombard_dual --format vertical --count 10

# С указанием конкретного URL для QR
python scripts/lombard_dual_composition.py --input-dir path/to/backgrounds --output output/lombard_dual --qr-url https://example.ru/lombard
```

### Список сценариев и опции

```bash
# Показать все доступные сценарии (без людей / с людьми)
python scripts/generate_lombard_banners.py --list-scenarios

# Показать требования законодательства
python scripts/generate_lombard_banners.py --show-requirements
```

**Выбор сценариев:** `--scenario NAME` (один), `--scenarios "name1,name2,..."` (несколько), `--all-scenarios`, `--with-people`, `--without-people`.

## Валидация текста

Валидатор автоматически проверяет:
- Наличие слова "Ломбард" в названии юрлица
- Отсутствие запрещённых формулировок (круглосуточно, инвестиции, гарантии)
- Режим работы в пределах 8:00-23:00

При нарушении выбрасывается исключение с описанием проблемы.

## Использование реальных компаний и дисклеймеров

По умолчанию используются данные из `lombard_companies.json` (90+ реальных ломбардов). Данные автоматически конвертируются из CSV файла `lombard_comp.csv`. Текст дисклеймера подставляется из `lombard_disclaimer_templates.json`: для каждой компании выбирается случайный шаблон или вариант с подстановкой `{company_name}`, `{ogrn}`, `{inn}`, `{address}`, `{contacts}`.

Чтобы использовать шаблоны вместо реальных компаний:

```bash
python scripts/generate_lombard_banners.py --all-scenarios --no-real-companies
```

### Обновление данных компаний

Если нужно обновить данные из CSV:

```bash
python scripts/convert_lombard_csv_to_json.py
```

## Структура файла компаний

`lombard_companies.json` содержит данные в формате:

```json
{
    "ООО \"Випломбард\" Ломбард швейцарских часов VIP Lombard": {
        "website": "https://www.viplombard.ru/",
        "phone": "+7 (495) 212-12-77, +7 (925) 761-22-06",
        "address": "Санкт-Петербург,Лиговский проспект, 93",
        "short_name": "VIP Lombard"
    }
}
```

Все компании содержат:
- `website` — сайт компании
- `phone` — телефон(ы)
- `address` — адрес (используется в source_info при наличии)
- `short_name` — короткое название (для справки)

## Особенности реализации

1. **Промпты для генерации фонов** — интерьеры ломбарда (офис, витрины, оценка), а также сценарии «объект в углу + градиент/абстракция» (авто, техника, ювелирные изделия) для разнообразия без людей
2. **Дисклеймеры** — загрузка из `lombard_disclaimer_templates.json`, случайный выбор шаблона/варианта и подстановка данных компании
3. **Безопасное позиционирование QR-кодов** — выше дисклеймера, не перекрывает текст
4. **Поддержка логотипов** — опциональное добавление логотипов после телефона (`--add-phone-logos`)
5. **Масштабирование текста** — автоматическая адаптация под разные форматы
6. **Разнообразие размещения текста** (dual composition):
   - `left_aligned` — текст слева
   - `right_aligned` — текст справа
   - `center_top` — текст по центру сверху
   - `center_middle` — текст по центру в середине
   - `diagonal_left` — диагональное размещение слева
   - `diagonal_right` — диагональное размещение справа
   - `split_horizontal` — разделение по горизонтали (заголовок слева, описание справа)
   - `split_vertical` — разделение по вертикали
7. **Разнообразие шрифтов** — 5 вариантов размеров шрифтов для заголовков, текста и телефона:
   - Стандартный (1.0x)
   - Крупный заголовок (1.2x заголовок, 0.9x текст)
   - Крупный текст (0.9x заголовок, 1.1x текст)
   - Крупные заголовок и телефон (1.15x)
   - Компактный (0.85-0.95x)
8. **Dual composition** — композиция из двух фоновых изображений с умным размещением текста и автоматическим подбором цвета фона

## Чек-лист проверки макета

1. ✅ Есть ли слово "Ломбард" в названии юрлица?
2. ✅ Указан ли режим работы в пределах 8:00-23:00?
3. ✅ Нет ли упоминания круглосуточной работы?
4. ✅ Нет ли призыва к инвестициям/вкладам?
5. ✅ Если указаны процентные ставки, есть ли ПСК?

## Связанные документы

- [ФЗ-38 «О рекламе»](https://www.consultant.ru/document/cons_doc_LAW_58968/) — ст. 28 (Финансовые услуги)
- [ФЗ-196 «О ломбардах»](https://www.consultant.ru/document/cons_doc_LAW_140174/) — ст. 6 (Режим работы)
