# Категория Bankruptcy (Банкротство физлиц)

Полная документация по всем скриптам и компонентам генерации рекламных баннеров о банкротстве физических лиц в соответствии с законодательством РФ (38-ФЗ, 127-ФЗ).

---

## 📁 Структура файлов

| Файл | Назначение |
|------|------------|
| `bankruptcy_overlay.py` | **Ядро** — класс `BankruptcyBannerOverlay`, валидатор `TextValidator`, все данные (заголовки, описания, сценарии, стили, дисклеймеры) |
| `generate_bankruptcy_banners.py` | **Основной пайплайн** — `BankruptcyBannerPipeline`, генерация баннеров (фоны без персон) |
| `generate_bankruptcy_banner_2.py` | **Расширенный пайплайн** — то же + сценарии с персонами (юристы), дополнительные фоны |
| `generate_bankruptcy_with_qr.py` | **Интеграция с QR** — `BankruptcyQRPipeline`, наложение QR-кодов на баннеры |
| `bankruptcy_config.json` | Конфигурация (сценарии, заголовки, дисклеймеры, стили) |
| `BANKRUPTCY_QR_INTEGRATION.md` | Документация по интеграции QR-кодов |
| `install_qr_dependencies.sh` | Установка зависимостей для QR (`qrcode`, `Pillow`) |

---

## 📋 Зависимости между скриптами

```
bankruptcy_overlay.py          ← данные и overlay
        ↑
        ├── generate_bankruptcy_banners.py   (BankruptcyBannerPipeline)
        ├── generate_bankruptcy_banner_2.py  (BankruptcyBannerPipeline + персоны)
        └── generate_bankruptcy_with_qr.py   (BankruptcyQRPipeline → использует banners)
```

---

## 🔧 Скрипты по назначению

### 1. `bankruptcy_overlay.py` — наложение текста на готовое изображение

**Использование:**
```bash
# Наложить баннер на одно изображение
python scripts/bankruptcy_overlay.py --image bg.png --output output/bankruptcy/

# Пакетная обработка папки
python scripts/bankruptcy_overlay.py --batch-dir path/to/images/ --output output/bankruptcy/

# Утилиты
python scripts/bankruptcy_overlay.py --list-headlines
python scripts/bankruptcy_overlay.py --list-descriptions
python scripts/bankruptcy_overlay.py --list-scenarios
python scripts/bankruptcy_overlay.py --list-styles
python scripts/bankruptcy_overlay.py --validate-text "Спишем ваши долги"
```

**Экспортирует:** `BankruptcyBannerOverlay`, `TextValidator`, `BANKRUPTCY_*` константы.

---

### 2. `generate_bankruptcy_banners.py` — полный пайплайн (генерация фона + текст)

**Режимы:**
- Один баннер / все сценарии
- Структурированные баннеры (маркированные списки, CTA)
- Массовая генерация (100–2000+ баннеров)

**Примеры:**
```bash
# Один баннер
python scripts/generate_bankruptcy_banners.py --scenario office_professional

# Все сценарии
python scripts/generate_bankruptcy_banners.py --all-scenarios --output output/bankruptcy/

# Структурированный баннер
python scripts/generate_bankruptcy_banners.py --structured --output output/bankruptcy_structured/

# Массовая генерация 500 структурированных
python scripts/generate_bankruptcy_banners.py --mass-structured 500 --banner-type mixed --output output/bankruptcy_mass/

# Массовая генерация 2000 случайных баннеров
python scripts/generate_bankruptcy_banners.py --mass-generate 2000 --output output/bankruptcy_mass/ --quantize 4bit --steps 30

# Утилиты
python scripts/generate_bankruptcy_banners.py --validate "Спишем ваши долги"
python scripts/generate_bankruptcy_banners.py --show-stats
python scripts/generate_bankruptcy_banners.py --list-headlines
python scripts/generate_bankruptcy_banners.py --list-bullet-lists
python scripts/generate_bankruptcy_banners.py --list-structured
```

---

### 3. `generate_bankruptcy_banner_2.py` — расширенный пайплайн (с персонами)

**Дополнительно к `generate_bankruptcy_banners.py`:**
- Сценарии с персонами: `lawyer_portrait_right`, `lawyer_portrait_left`, `lawyer_desk`
- Дополнительные фоны: `courthouse_grand`, `office_modern_glass`, `abstract_gold_patterns`, `library_antique`, `justice_symbols_marble`
- Флаги: `--with-person`, `--person-side`, `--person-scenario`, `--mixed-scenarios`, `--person-ratio`, `--balanced`

**Примеры:**
```bash
# Баннер с персоной (юрист)
python scripts/generate_bankruptcy_banner_2.py --with-person --person-side left

# Конкретный сценарий с персоной
python scripts/generate_bankruptcy_banner_2.py --person-scenario lawyer_portrait_right

# Массовая генерация только с персонами
python scripts/generate_bankruptcy_banner_2.py --mass-structured 100 --banner-type mixed --with-person --balanced --output output/bankruptcy_persons/

# Смешанная генерация (30% персоны, 70% фоны)
python scripts/generate_bankruptcy_banner_2.py --mass-structured 100 --mixed-scenarios --person-ratio 0.3 --balanced --output output/bankruptcy_mixed/

# Список сценариев с персонами
python scripts/generate_bankruptcy_banner_2.py --list-person-scenarios
```

---

### 4. `generate_bankruptcy_with_qr.py` — баннеры с QR-кодами

**Зависимости:** `custom-qr-generator` (`/mldata/custom-qr-generator`), `qrcode`, `Pillow`

**Установка зависимостей:**
```bash
bash scripts/install_qr_dependencies.sh
# или
pip install qrcode[pil]>=7.4.2 Pillow>=10.0.0
```

**Примеры:**
```bash
# Массовая генерация 2000 баннеров, 50% с QR
python scripts/generate_bankruptcy_with_qr.py --mass-generate 2000 --qr-percentage 50 --output output/bankruptcy_with_qr/ --quantize 4bit --steps 30

# Быстрый тест 100 баннеров
python scripts/generate_bankruptcy_with_qr.py --mass-generate 100 --qr-percentage 30 --output output/bankruptcy_test_qr/

# Один тестовый баннер с QR
python scripts/generate_bankruptcy_with_qr.py --qr-type artistic_transparent --output output/test/
```

**Типы QR:** `simple`, `artistic_white`, `artistic_transparent`, `custom_color`

Подробнее: `BANKRUPTCY_QR_INTEGRATION.md`

---

## ⚖️ Требования законодательства (38-ФЗ)

### ✅ Обязательно
- Слово **«банкротство»** или **«банкротство физлиц»** в явном виде
- С **01.09.2025:** предупредительная надпись
- С **01.01.2026:** предупреждение о последствиях + льготные варианты (МФЦ)

### ❌ Запрещено (проверяется `TextValidator`)
- «спишем долги», «списание долгов», «избавим от долгов»
- «гарантированно», «100%», «навсегда»
- Обещания освобождения от обязательств
- Банкротство юрлиц (только физлица)

---

## 📂 Конфигурация

**`configs/bankruptcy_config.json`** содержит:
- `scenarios` — промпты для генерации фонов
- `headlines` — заголовки (все с «банкротство»)
- `descriptions` — описания услуг
- `disclaimers` — дисклеймеры по периодам (2024, 2025, 2026)
- `styles` — цветовые схемы (navy_gold, white_clean, silver_professional, cream_classic)
- `forbidden_phrases` — запрещённые формулировки
- `generation` — параметры SD (width, height, steps, guidance_scale)

---

## 📊 Контент (из `bankruptcy_overlay.py`)

| Тип | Количество |
|-----|------------|
| Сценарии фонов | ~20 |
| Заголовки | ~20 |
| Описания | ~20 |
| Дисклеймеры 2024 | 4 |
| Дисклеймеры 2025 | 3 |
| Дисклеймеры 2026 | 3 |
| Стили | 4+ |
| Маркированные списки | 10 |
| Структурированные блоки | 5 |
| CTA-кнопки | 8 |

---

## 📁 Выходные данные

**Имена файлов:**
- `bankruptcy_00001_office_professional_navy_gold_12345.png` — обычные баннеры
- `bankruptcy_qr_00001_office_professional_simple_12345.png` — баннеры с QR

**Метаданные (при `--save-metadata`):**
- `generation_stats.json` — статистика и метаданные
- `structured_stats.json` — статистика структурированных баннеров

---

## 🔗 Связанные файлы

- **Логи:** `logs/bankruptcy_*.log`, `logs/mass_*.log`
- **Документация QR:** `scripts/BANKRUPTCY_QR_INTEGRATION.md`
- **Текстовый overlay:** `scripts/text_overlay.py` (используется в bankruptcy_overlay)

---

## 🚀 Быстрый старт

```bash
# 1. Один тестовый баннер
python scripts/generate_bankruptcy_banners.py --scenario office_professional --output output/bankruptcy/

# 2. 10 баннеров для проверки
python scripts/generate_bankruptcy_banners.py --mass-generate 10 --output output/bankruptcy_test/ --steps 25

# 3. С QR-кодами (после установки зависимостей)
bash scripts/install_qr_dependencies.sh
python scripts/generate_bankruptcy_with_qr.py --mass-generate 10 --qr-percentage 100 --output output/bankruptcy_qr_test/
```
