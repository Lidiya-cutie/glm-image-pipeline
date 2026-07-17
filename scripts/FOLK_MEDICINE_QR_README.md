# Генерация баннеров народной медицины с QR-кодами

## Описание

Скрипт `generate_folk_medicine_with_qr.py` объединяет:
1. Генерацию баннеров народной медицины
2. Генерацию QR-кодов с логотипами из `/mldata/logo_for_qr.rar`
3. Умное наложение QR с избежанием текста

## Установка зависимостей

```bash
pip install qrcode[pil]>=7.4.2 Pillow>=10.0.0
```

## Использование

### Массовая генерация 2000 баннеров

```bash
python3 scripts/generate_folk_medicine_with_qr.py \
    --mass-generate 2000 \
    --qr-percentage 50 \
    --output output/folk_medicine_with_qr/ \
    --quantize 4bit \
    --steps 30
```

### Быстрая тестовая генерация 100 баннеров

```bash
python3 scripts/generate_folk_medicine_with_qr.py \
    --mass-generate 100 \
    --qr-percentage 30 \
    --output output/folk_medicine_test_qr/
```

### Один тестовый баннер

```bash
python3 scripts/generate_folk_medicine_with_qr.py \
    --qr-type artistic_transparent \
    --output output/test/
```

## Параметры

### Основные
- `--mass-generate N` - генерировать N баннеров
- `--qr-percentage X` - процент баннеров с QR (0-100, по умолчанию 50)
- `--qr-type TYPE` - тип QR: `simple`, `artistic_white`, `artistic_transparent`, `custom_color`, `random`

### Логотипы
- `--logo-archive PATH` - путь к архиву с логотипами (по умолчанию `/mldata/logo_for_qr.rar`)
- `--logo-dir PATH` - директория для распаковки (по умолчанию `/mldata/logo_for_qr_extracted`)

### Генерация
- `--width`, `--height` - размер изображения (по умолчанию 1024)
- `--steps` - количество шагов генерации (по умолчанию 50)
- `--cfg-scale` - guidance scale (по умолчанию 7.5)
- `--quantize` - квантизация: `4bit` или `8bit`
- `--device` - устройство: `cuda`, `cpu`
- `--output` - папка для сохранения

## Типы QR-кодов

1. **simple** - простой QR на белом фоне с логотипом
2. **artistic_white** - артистичный QR с градиентом на белом
3. **artistic_transparent** - QR на прозрачном фоне с логотипом
4. **custom_color** - кастомный цветной QR (зелёный, синий, коричневый, фиолетовый, оранжевый)

## Автоматическая распаковка архива

Скрипт автоматически распаковывает `/mldata/logo_for_qr.rar` при первом запуске.
Поддерживаются методы:
- `unrar` (если установлен)
- `python-rarfile` (если установлен: `pip install rarfile`)
- `7z` (если установлен)

Если автоматическая распаковка не работает, распакуйте архив вручную:
```bash
unrar x /mldata/logo_for_qr.rar /mldata/logo_for_qr_extracted/
```

## Выходные данные

### Файлы
- `folk_medicine_qr_00001_scenario_name_123456789.png` - сгенерированные баннеры
- `generation_stats.json` - метаданные и статистика

### Метаданные
```json
{
  "id": 0,
  "filename": "folk_medicine_qr_00001_...",
  "scenario": "herbs_jars",
  "has_qr": true,
  "qr_type": "artistic_transparent",
  "logo_path": "/mldata/logo_for_qr_extracted/logo1.png",
  "url": "https://newnorma.ru",
  "generation_time_sec": 28.5
}
```

## Производительность

- Генерация баннера: ~25-35 секунд
- Добавление QR: ~0.1-0.5 секунды
- **Итого:** ~30 секунд/баннер

**Для 2000 баннеров:** ~17 часов (с квантизацией 4bit: ~15 часов)

## Особенности

- ✅ QR избегают наложения на текст (автоматическое позиционирование)
- ✅ Разнообразие типов QR (4 типа, случайный выбор)
- ✅ Логотипы из архива (автоматическая распаковка)
- ✅ Частичное наложение QR (настраиваемый процент)
- ✅ Массовая генерация любых объёмов
