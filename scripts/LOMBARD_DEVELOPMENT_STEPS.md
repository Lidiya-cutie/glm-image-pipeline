# Полный список шагов разработки пайплайна «Ломбарды»

Хронологический и тематический список всех этапов и внесённых изменений от начала разработки пайплайна по категории «Ломбарды» до текущего состояния.

---

## 1. Базовая инфраструктура и законодательство

### 1.1 Модуль оверлея и валидации
- **Файл:** `lombard_overlay.py`
- Введён модуль генерации рекламных баннеров ломбардов с учётом ст. 28 ФЗ-38 «О рекламе» и ФЗ-196 «О ломбардах».
- Описаны обязательные элементы: наименование юрлица со словом «Ломбард», источник информации (сайт, адрес, телефон), режим работы 8:00–23:00.
- Описаны запреты: круглосуточная работа, привлечение инвестиций/вкладов, гарантированная оценка без оговорок, отсутствие ПСК при указании ставок.

### 1.2 Валидатор текстов
- **Файл:** `lombard_overlay.py`
- Класс `LombardValidator`: проверка на запрещённые формулировки (`FORBIDDEN_PHRASES`), проверка наличия слова «Ломбард» в наименовании, проверка режима работы в пределах 8:00–23:00.
- Исключение для паттерна «0 %» в дисклеймерах при наличии ПСК и полных условий займа.

### 1.3 Статические тексты
- **Файл:** `lombard_overlay.py`
- Константы: `LOMBARD_HEADLINES`, `LOMBARD_DESCRIPTIONS`, `LOMBARD_DISCLAIMERS` (25+ формулировок), `LEGAL_ENTITY_TEMPLATES`, `SOURCE_INFO_TEMPLATES`.
- Все формулировки соответствуют чек-листу (наименование с «Ломбард», источник, режим 8:00–23:00, без запрещённых формулировок).

### 1.4 Стили оформления и фона дисклеймера
- **Файл:** `lombard_overlay.py`
- `LOMBARD_STYLES`: 4 стиля (navy_gold, corporate_blue, professional_dark, elegant_gold).
- `DISCLAIMER_BG_STYLES`: стили фона блока дисклеймера (имя, цвет, прозрачность и т.д.).

---

## 2. Данные компаний

### 2.1 Исходные данные (CSV)
- **Файл:** `lombard_comp.csv`
- Исходный CSV с данными 90+ ломбардов: полное наименование, сайт, телефон, адрес, короткое название.

### 2.2 Конвертация CSV → JSON
- **Файл:** `convert_lombard_csv_to_json.py`
- Скрипт конвертации CSV в JSON с группировкой филиалов по компании.
- Выход: `lombard_companies.json` (ключ — полное наименование, поля: website, phone, address, short_name).

### 2.3 Загрузка и использование компаний в оверлее
- **Файл:** `lombard_overlay.py`
- Константа `COMPANIES_JSON_PATH`, функция `load_companies()`, кэширование.
- Функция `get_random_company()` для случайного выбора компании при генерации контента.
- Форматирование источника информации: `format_source_info(website, phone, address)`.

---

## 3. Сценарии фонов (первая версия)

### 3.1 Сценарии без людей (интерьеры)
- **Файл:** `lombard_overlay.py`
- Список `LOMBARD_SCENARIOS_NO_PEOPLE` (7 сценариев):
  - `office_lombard` — офис ломбарда с витринами
  - `jewelry_display` — витрина с ювелирными изделиями
  - `tech_items` — выставка техники
  - `gold_evaluation` — стол оценки золота
  - `vault_interior` — хранилище
  - `reception_area` — зона приёма
  - `assessment_room` — комната оценки
- У каждого: `name`, `prompt`, `has_person: False`.

### 3.2 Сценарии с людьми
- **Файл:** `lombard_overlay.py`
- Список `LOMBARD_SCENARIOS_WITH_PEOPLE` (7 сценариев): consultant_right, appraiser_left, manager_center, consultant_desk, appraiser_work, manager_portrait, consultant_helping.
- У каждого: `name`, `prompt`, `has_person: True`, `person_position` (left/right/center).
- Объединение: `LOMBARD_SCENARIOS = LOMBARD_SCENARIOS_NO_PEOPLE + LOMBARD_SCENARIOS_WITH_PEOPLE`.

### 3.3 Привязка layout к сценарию
- **Файл:** `lombard_overlay.py`
- Функция `get_layout_for_scenario(scenario)`: для сценариев без людей — случайный layout из `LAYOUTS`, для сценариев с людьми — выбор по `person_position` (используется `text_overlay.LAYOUTS`).

---

## 4. Генерация баннеров

### 4.1 Пайплайн генерации
- **Файл:** `generate_lombard_banners.py`
- Класс `LombardBannerPipeline`: загрузка диффузионной модели, генерация фона по сценарию (prompt, neg_prompt, различие для сценариев с людьми), наложение текста через `LombardBannerOverlay`.
- Форматы: `BANNER_FORMATS` — square 1024×1024, horizontal 1200×700, vertical 800×1200.
- Поддержка квантизации (4bit/8bit), опция валидации.

### 4.2 Пакетная генерация
- **Файл:** `generate_lombard_banners.py`
- `generate_batch()`: перебор сценариев и вариаций, генерация фона, формирование контента (`get_random_content`), наложение текста и дисклеймера, опционально QR и логотипы после телефона.
- Режим `backgrounds_only`: только фоны без текста.
- Использование реальных компаний по умолчанию; флаг `no_real_companies` для шаблонов.

### 4.3 CLI (первая версия)
- **Файл:** `generate_lombard_banners.py`
- Аргументы: `--scenario`, `--all-scenarios`, `--with-people`, `--without-people`, `--format`, `--count`, `--output`, `--steps`, `--seed`, `--quantize`, `--list-scenarios`, `--show-requirements`, `--no-real-companies`, `--qr-chance`, `--backgrounds-only`, `--add-phone-logos`, `--favicons-dir`, `--width`/`--height`.

---

## 5. QR-коды и позиционирование

### 5.1 Безопасная позиция QR
- **Файл:** `lombard_overlay.py`
- Функция `find_safe_qr_position_for_lombard()`: размещение QR в нижних углах выше дисклеймера, с отступами и учётом высоты дисклеймера.

### 5.2 Интеграция QR в оверлей
- **Файл:** `lombard_overlay.py`
- В `LombardBannerOverlay`: опциональная вставка QR-изображения с использованием безопасной позиции (выше дисклеймера).

---

## 6. Логотипы после телефона

### 6.1 Загрузка логотипов
- **Файл:** `lombard_overlay.py`
- Константа `LOGO_FOR_QR_DIR`, функция `_load_contact_logos(favicons_dir, logo_height, count)` — загрузка и масштабирование PNG/JPG из директории.

### 6.2 Отрисовка логотипов в баннере
- **Файл:** `lombard_overlay.py`
- В `LombardBannerOverlay`: опция `add_phone_logos`, отрисовка логотипов после блока с телефоном (из `favicons_dir`).

---

## 7. Дисклеймеры из JSON (шаблоны)

### 7.1 Файл шаблонов дисклеймеров
- **Файл:** `lombard_disclaimer_templates.json`
- Структура: массив `disclaimers`, каждый элемент — объект с полями `template` и `variations` (массив вариантов текста).
- Плейсхолдеры в тексте: `{company_name}`, `{ogrn}`, `{inn}`, `{address}`, `{contacts}`.
- Несколько шаблонов с разными формулировками (ПСК, сроки, суммы, режим работы и т.д.) в соответствии с законодательством.

### 7.2 Загрузка шаблонов в оверлее
- **Файл:** `lombard_overlay.py`
- Константа `DISCLAIMER_TEMPLATES_PATH`, кэш `_disclaimer_templates_cache`.
- Функция `load_disclaimer_templates()`: чтение JSON, ключ `disclaimers` (или `discclaimers` для совместимости), возврат списка блоков.

### 7.3 Подстановка данных компании в шаблон
- **Файл:** `lombard_overlay.py`
- Функция `format_disclaimer_template(template_str, company)`: подстановка company_name (short_name/name), address, ogrn, inn, contacts (телефон + сайт).
- Формирование строки `contacts` из phone и website.

### 7.4 Случайный дисклеймер из шаблонов или статики
- **Файл:** `lombard_overlay.py`
- Функция `get_random_disclaimer(company=None, use_templates=True)`: при наличии компании и загруженных шаблонов — выбор случайного блока, затем случайного варианта (template или variations), подстановка данных компании; иначе — случайный из `LOMBARD_DISCLAIMERS`.

### 7.5 Использование в контенте и в dual
- **Файл:** `lombard_overlay.py`
- В `get_random_content()`: вызов `get_random_disclaimer(company=company)` при формировании контента; контент возвращает поле `disclaimer`.
- **Файл:** `generate_lombard_banners.py`
- Контент с дисклеймером передаётся в оверлей при генерации баннеров.
- **Файл:** `lombard_dual_composition.py`
- При формировании контента для dual: `disclaimer = content.get("disclaimer") or get_random_disclaimer(company=company)` — использование дисклеймера из контента или случайного из шаблонов по компании.

---

## 8. Сценарии «объект в углу + градиент/абстракция» (без людей)

### 8.1 Требования к промптам
- Объект (автомобиль или техника) в нижнем левом или нижнем правом углу, не у самого края (margin from border).
- Остальная часть кадра (~65%) — простой градиент или абстрактный фон.
- Реалистичность объекта, без галлюцинаций (чёткие формулировки: photorealistic, product shot, no distortion, no text).

### 8.2 Добавление сценариев в LOMBARD_SCENARIOS_NO_PEOPLE
- **Файл:** `lombard_overlay.py`
- Добавлены сценарии (все `has_person: False`):
  - `car_lower_right_gradient` — автомобиль, нижний правый угол, градиент
  - `car_lower_left_gradient` — автомобиль, нижний левый угол, градиент
  - `car_lower_right_abstract` — автомобиль, нижний правый угол, абстрактный фон
  - `fridge_lower_corner_gradient` — холодильник
  - `stove_lower_corner_gradient` — плита
  - `computer_tower_lower_corner_gradient` — системный блок ПК
  - `wristwatch_lower_corner_gradient` — наручные часы
  - `laptop_lower_corner_gradient` — ноутбук
  - `tv_or_monitor_lower_corner_gradient` — ТВ/монитор
- В промптах явно указаны: corner, not at edge, margin, rest gradient/abstract, no people, 8k, no distortion.

---

## 9. Ювелирные сценарии (кольца, ожерелье)

### 9.1 Добавление сценариев по аналогии с часами
- **Файл:** `lombard_overlay.py`
- В `LOMBARD_SCENARIOS_NO_PEOPLE` добавлены:
  - `rings_emerald_diamond_lower_corner_gradient` — дорогие кольца с изумрудами и бриллиантами, золото/платина, нижний правый угол, нейтральный градиент.
  - `rings_sapphire_diamond_lower_corner_gradient` — кольца с сапфирами и бриллиантами, белое золото/платина, нижний левый угол.
  - `necklace_precious_stones_lower_corner_gradient` — ожерелье с драгоценными камнями, нижний правый угол, нейтральный градиент.
- Стиль промптов: как у `wristwatch_lower_corner_gradient` (jewelry product photography, sharp, no distortion).

---

## 10. CLI: выбор нескольких сценариев по имени

### 10.1 Аргумент --scenarios
- **Файл:** `generate_lombard_banners.py`
- Добавлен аргумент `--scenarios` (строка): несколько имён сценариев через запятую, например `rings_emerald_diamond_lower_corner_gradient,necklace_precious_stones_lower_corner_gradient`.

### 10.2 Логика выбора сценариев
- **Файл:** `generate_lombard_banners.py`
- При указании `--scenarios`: разбор строки по запятым, фильтрация `LOMBARD_SCENARIOS` по множеству имён, проверка на отсутствующие имена с выводом ошибки при missing.

---

## 11. Генерация чистых фонов (отдельный скрипт)

### 11.1 Скрипт generate_lombard_clean_backgrounds.py
- Генерация только фонов без текста, дисклеймера и QR.
- Поддержка `--scenario-name`, `--list-scenarios`, `--with-people` / `--without-people` / все сценарии, форматы, count, steps, cfg.
- Использует те же сценарии из `lombard_overlay` (в т.ч. все новые «угол + градиент» и ювелирные).

---

## 12. Dual composition (композиция из двух фонов)

### 12.1 Скрипт lombard_dual_composition.py
- Композиция из двух фоновых изображений (из директории), наложение заголовка, описания, дисклеймера, опционально QR.
- Разнообразные варианты размещения текста (left_aligned, right_aligned, center_top, center_middle, diagonal_left, diagonal_right, split_horizontal, split_vertical).
- Использование реальных компаний, `get_random_disclaimer(company=company)` для текста дисклеймера.
- Безопасное позиционирование QR выше дисклеймера (учёт disclaimer_y, disclaimer_height).
- Параметры: `--input-dir`, `--output`, `--format`, `--count`, `--qr-chance`, `--qr-url` и др.

---

## 13. Документация

### 13.1 README ломбардов (первая версия)
- **Файл:** `LOMBARD_README.md`
- Описание категории, созданных файлов, форматов, сценариев (7 без людей + 7 с людьми), требований законодательства, примеров текстов, стилей, примеров запуска, валидации, использования реальных компаний, структуры JSON компаний, особенностей реализации, чек-листа, ссылок на ФЗ-38 и ФЗ-196.

### 13.2 Обновление README после всех изменений
- **Файл:** `LOMBARD_README.md`
- **Таблица файлов:** добавлен `lombard_disclaimer_templates.json`; уточнены назначения `lombard_overlay.py` (загрузка дисклеймеров и компаний) и `generate_lombard_banners.py` (19 сценариев без людей + 7 с людьми).
- **Сценарии:** разбивка «Без людей» на «Интерьеры (7)» и «Объект в углу + градиент (12)» с полным перечислением имён (авто, техника, часы, кольца, ожерелье и т.д.).
- **Примеры запуска:** добавлены примеры с `--scenarios` для проверки только сценариев с кольцами и ожерельем; пример с `--backgrounds-only` и `--scenarios`; уточнён выбор сценариев (--scenario, --scenarios, --all-scenarios, --with-people, --without-people).
- **Раздел «Использование реальных компаний»:** переименован в «Использование реальных компаний и дисклеймеров», добавлено описание загрузки дисклеймеров из JSON и подстановки данных компании.
- **Особенности реализации:** добавлен пункт про дисклеймеры из JSON; уточнён пункт про промпты (интерьеры + сценарии «объект в углу»); нумерация пунктов 1–8 (промпты, дисклеймеры, QR, логотипы, масштабирование текста, размещение текста, шрифты, dual composition).

---

## 14. Итоговая сводка по файлам и возможностям

| Компонент | Файлы | Краткое описание |
|-----------|--------|------------------|
| Оверлей и валидация | `lombard_overlay.py` | Валидатор, тексты, стили, 26 сценариев, загрузка компаний и дисклеймеров, QR-позиция, логотипы |
| Генерация баннеров | `generate_lombard_banners.py` | Пайплайн: фон + текст + дисклеймер + QR/логотипы; --scenario, --scenarios, --all-scenarios, --backgrounds-only |
| Чистые фоны | `generate_lombard_clean_backgrounds.py` | Только генерация фонов по сценариям без текста |
| Dual composition | `lombard_dual_composition.py` | Два фона + текст + дисклеймер + QR, несколько вариантов layout |
| Компании | `lombard_companies.json`, `lombard_comp.csv`, `convert_lombard_csv_to_json.py` | Данные ломбардов, конвертация CSV→JSON |
| Дисклеймеры | `lombard_disclaimer_templates.json` | Шаблоны с подстановками {company_name}, {ogrn}, {inn}, {address}, {contacts} |
| Документация | `LOMBARD_README.md`, `LOMBARD_DEVELOPMENT_STEPS.md` | Описание использования и полный список шагов разработки |

---

*Документ составлен по анализу кодовой базы и внесённых в чате изменений. При появлении новых правок их следует добавлять в соответствующий раздел и при необходимости в итоговую сводку.*
