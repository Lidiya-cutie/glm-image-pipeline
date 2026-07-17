# QR-коды и логотипы в баннерах доверительного управления

## Исправления

### 1. Позиционирование QR-кода

QR-код теперь размещается в **нижних углах баннера**, но **выше дисклеймера**, чтобы не закрывать текст дисклеймера.

- Позиции: левый нижний или правый нижний угол (случайный выбор)
- Размещение: выше дисклеймера с отступом 15px
- Размер: ~12% от меньшей стороны изображения (макс. 120px)

### 2. Логотипы после телефона

Добавлена функция наложения логотипов после телефона в формате `+7`.

**Условия:**
- Телефон должен начинаться с `+7`
- Параметр `--add-phone-logos` должен быть включен
- Логотипы загружаются из `/mldata/logo_for_qr_extracted`

**Параметры:**
- Количество: случайно 0-2 логотипа
- Размер: по высоте текста телефона
- Позиция: справа от телефона с отступом

## Использование

### С QR-кодами

```bash
# 50% баннеров с QR (по умолчанию)
python scripts/generate_trust_management_banners.py --all-scenarios --format horizontal --count 5

# Все баннеры с QR
python scripts/generate_trust_management_banners.py --all-scenarios --format horizontal --count 5 --qr-chance 100

# Без QR-кодов
python scripts/generate_trust_management_banners.py --all-scenarios --format horizontal --count 5 --qr-chance 0
```

### С логотипами после телефона

```bash
# С логотипами (если телефон в формате +7)
python scripts/generate_trust_management_banners.py --all-scenarios --format horizontal --count 5 --add-phone-logos

# С логотипами и кастомной директорией
python scripts/generate_trust_management_banners.py --all-scenarios --format horizontal --count 5 --add-phone-logos --favicons-dir /path/to/logos
```

### Комбинация

```bash
# QR + логотипы
python scripts/generate_trust_management_banners.py --all-scenarios --format horizontal --count 10 --qr-chance 60 --add-phone-logos
```

## Технические детали

### QR-код
- Функция: `find_safe_qr_position_for_trust_management()`
- Учитывает позицию дисклеймера
- Размещается в нижних углах выше дисклеймера

### Логотипы
- Функция: `_load_contact_logos()` в `trust_management_overlay.py`
- Размер: высота = высота текста телефона
- Количество: случайно 0-2
- Позиция: справа от телефона, выравнивание по центру
