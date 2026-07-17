# Интеграция баннеров банкротства с QR-кодами

## Анализ существующих скриптов

### 1. Генерация баннеров банкротства

**Файл:** `generate_bankruptcy_banners.py`

**Найденные возможности:**
- ✅ **ЕСТЬ** массовая генерация: метод `generate_mass_random()` поддерживает 100, 500, 1000, 2000+ баннеров
- ✅ **ЕСТЬ** структурированные баннеры: методы `generate_structured_banner()` и `generate_bullet_banner()`
- ✅ **ЕСТЬ** метод `generate_mass_structured()` для массовой генерации структурированных баннеров

**Вывод:** Скрипт банкротства уже поддерживает потоковую генерацию любых объёмов.

### 2. Генерация QR-кодов

**Файл:** `/mldata/custom-qr-generator/qr_generator/domain_processor.py`

**Найденные возможности:**
- ✅ Загрузка доменов из CSV (`traditional_healers_domains.csv`)
- ✅ Работа с фавиконами из `/mldata/LLD_favicons_full_png`
- ✅ Генерация QR с разными стилями
- ✅ Пакетная генерация для всех доменов

**Файл:** `/mldata/custom-qr-generator/qr_generator/artistic.py`

**Найденные возможности:**
- ✅ QR на прозрачном фоне (`generate_transparent()`)
- ✅ Артистичные QR с blend modes
- ✅ Halftone стиль
- ✅ Кастомные цветные QR

**Вывод:** Все необходимые компоненты для QR-генерации уже существуют.

## Решение: Новый интегратор-скрипт

### Созданный файл: `generate_bankruptcy_with_qr.py`

**Принцип работы:**
1. **НЕ ЛОМАЕТ** существующие скрипты - использует их как библиотеки
2. **Объединяет** функциональность через композицию классов
3. **Добавляет** логику наложения QR с избежанием текста

### Ключевые компоненты:

#### 1. `QRPlacementStrategy`
- Определяет безопасные зоны для размещения QR
- Избегает текстовых областей (заголовки, описания, дисклеймеры)
- Автоматически находит оптимальную позицию

#### 2. `BankruptcyQRPipeline`
- Использует `BankruptcyBannerPipeline` для генерации баннеров
- Использует `DomainProcessor` для работы с доменами
- Генерирует разнообразные QR (простые, артистичные, кастомные)
- Накладывает QR только на часть баннеров (настраиваемый процент)

#### 3. Метод `generate_qr_variety()`
Поддерживает 4 типа QR:
- **simple** - простой QR на белом фоне с логотипом
- **artistic_white** - артистичный QR с градиентом на белом
- **artistic_transparent** - QR на прозрачном фоне
- **custom_color** - кастомный цветной QR

## Использование

### Массовая генерация 2000 баннеров с QR

```bash
python scripts/generate_bankruptcy_with_qr.py \
    --mass-generate 2000 \
    --qr-percentage 50 \
    --output output/bankruptcy_with_qr/ \
    --quantize 4bit \
    --steps 30
```

**Параметры:**
- `--mass-generate 2000` - генерировать 2000 баннеров
- `--qr-percentage 50` - 50% баннеров будут с QR-кодами
- `--quantize 4bit` - экономия VRAM
- `--steps 30` - быстрая генерация

### Быстрая тестовая генерация 100 баннеров

```bash
python scripts/generate_bankruptcy_with_qr.py \
    --mass-generate 100 \
    --qr-percentage 30 \
    --output output/bankruptcy_test_qr/ \
    --quantize 8bit \
    --steps 25
```

### Генерация одного тестового баннера

```bash
python scripts/generate_bankruptcy_with_qr.py \
    --qr-type artistic_transparent \
    --output output/test/
```

## Особенности реализации

### 1. Избежание наложения QR на текст

**Механизм:**
- Определены текстовые зоны (левая верхняя, левая средняя, нижняя, правая верхняя)
- QR размещается в безопасных зонах (углы, края)
- Автоматическая проверка пересечений перед размещением

**Безопасные зоны:**
- Правый верхний угол (70-95% по X, 2-25% по Y)
- Правый нижний угол (70-95% по X, 65-93% по Y)
- Центр правой части (75-95% по X, 40-60% по Y)

### 2. Разнообразие QR-кодов

**Типы:**
1. **Простой** - классический QR с логотипом на белом
2. **Артистичный белый** - градиентный QR на белом фоне
3. **Артистичный прозрачный** - QR на прозрачном фоне с логотипом
4. **Кастомный цветной** - цветные QR (зелёный, синий, коричневый, чёрный)

**Распределение:** Случайный выбор типа для каждого QR

### 3. Частичное наложение QR

**Логика:**
- По умолчанию QR добавляется на 50% баннеров
- Настраивается через `--qr-percentage`
- Каждый баннер независимо решает добавлять ли QR

**Преимущества:**
- Разнообразие выходных данных
- Часть баннеров без QR для сравнения
- Гибкая настройка соотношения

## Структура выходных данных

### Файлы:
- `bankruptcy_qr_00001_scenario_name_simple_123456789.png` - сгенерированные баннеры
- `generation_stats.json` - метаданные и статистика

### Метаданные в JSON:
```json
{
  "id": 0,
  "filename": "bankruptcy_qr_00001_...",
  "scenario": "office_professional",
  "banner_type": "structured",
  "has_qr": true,
  "qr_type": "artistic_transparent",
  "domain": "newnorma.ru",
  "generation_time_sec": 28.5
}
```

## Интеграция с существующими скриптами

### Использует (НЕ изменяет):
- ✅ `BankruptcyBannerPipeline` из `generate_bankruptcy_banners.py`
- ✅ `BankruptcyBannerOverlay` из `bankruptcy_overlay.py`
- ✅ `DomainProcessor` из `qr_generator/domain_processor.py`
- ✅ `QRGenerator` из `qr_generator/core.py`
- ✅ `ArtisticQRGenerator` из `qr_generator/artistic.py`

### Не требует изменений:
- ❌ Не изменяет `generate_bankruptcy_banners.py`
- ❌ Не изменяет `bankruptcy_overlay.py`
- ❌ Не изменяет QR генераторы

## Пути решения для других задач

### Добавление новых типов QR

**Файл:** `generate_bankruptcy_with_qr.py`, метод `generate_qr_variety()`

**Добавить новый тип:**
```python
elif qr_type == "new_type":
    # Ваша логика генерации
    return qr_image
```

### Изменение стратегии размещения QR

**Файл:** `generate_bankruptcy_with_qr.py`, класс `QRPlacementStrategy`

**Изменить зоны:**
- Модифицировать `TEXT_ZONES` для новых текстовых областей
- Добавить новые зоны в `safe_zones`

### Интеграция с другими темами

**Шаблон:**
1. Создать новый скрипт `generate_[theme]_with_qr.py`
2. Заменить `BankruptcyBannerPipeline` на соответствующий пайплайн
3. Использовать тот же `QRPlacementStrategy` (или адаптировать)

## Производительность

**Оценка времени:**
- Генерация баннера: ~25-35 секунд
- Добавление QR: ~0.1-0.5 секунды
- **Итого:** ~30 секунд/баннер

**Для 2000 баннеров:**
- Время: ~17 часов
- С квантизацией 4bit: ~15 часов
- С уменьшенными шагами (25): ~12 часов

## Рекомендации

1. **Для тестирования:** Используйте `--mass-generate 10 --qr-percentage 100`
2. **Для продакшена:** Используйте `--mass-generate 2000 --qr-percentage 50 --quantize 4bit`
3. **Для быстрой генерации:** Уменьшите `--steps` до 25-30

## Зависимости

### Требуемые пакеты:

```bash
pip install qrcode[pil]>=7.4.2 Pillow>=10.0.0
```

### Быстрая установка:

```bash
# Автоматическая установка через скрипт
bash scripts/install_qr_dependencies.sh

# Или вручную
pip install qrcode[pil] Pillow
```

### Проверка установки:

```bash
python3 -c "import qrcode; import PIL; print('OK')"
```

### Если возникают проблемы:

1. **Ошибка "No module named 'qrcode'"**:
   ```bash
   pip install qrcode[pil]>=7.4.2
   ```

2. **Ошибка импорта из qr_generator**:
   - Убедитесь, что `/mldata/custom-qr-generator` существует
   - Проверьте структуру: `/mldata/custom-qr-generator/qr_generator/`

3. **Проблемы с виртуальным окружением**:
   ```bash
   # Активируйте venv если используете
   source venv/bin/activate
   pip install qrcode[pil] Pillow
   ```
