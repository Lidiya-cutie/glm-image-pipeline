# Генерация чистых фонов доверительного управления

## Два способа генерации чистых фонов БЕЗ текста

### 1. Отдельный скрипт: `generate_trust_management_clean_backgrounds.py`

Специализированный скрипт для генерации только фонов:

```bash
# Список всех сценариев
python scripts/generate_trust_management_clean_backgrounds.py --list-scenarios

# Генерация 10 случайных фонов (квадрат 1024x1024)
python scripts/generate_trust_management_clean_backgrounds.py --count 10

# Генерация горизонтальных фонов (1200x700)
python scripts/generate_trust_management_clean_backgrounds.py --count 10 --format horizontal

# Генерация вертикальных фонов (800x1200)
python scripts/generate_trust_management_clean_backgrounds.py --count 10 --format vertical

# Только фоны БЕЗ людей
python scripts/generate_trust_management_clean_backgrounds.py --count 10 --without-people

# Только фоны С людьми
python scripts/generate_trust_management_clean_backgrounds.py --count 10 --with-people

# Конкретный сценарий
python scripts/generate_trust_management_clean_backgrounds.py --scenario-name office_financial --count 5

# Кастомные размеры
python scripts/generate_trust_management_clean_backgrounds.py --count 5 --width 1920 --height 1080
```

### 2. Опция в основном скрипте: `--backgrounds-only`

Используйте флаг `--backgrounds-only` в основном скрипте:

```bash
# Генерация 5 чистых фонов (все сценарии)
python scripts/generate_trust_management_banners.py --all-scenarios --format horizontal --count 5 --backgrounds-only

# Только фоны без людей
python scripts/generate_trust_management_banners.py --without-people --format vertical --count 10 --backgrounds-only

# Только фоны с людьми
python scripts/generate_trust_management_banners.py --with-people --format square --count 7 --backgrounds-only
```

## Разница между скриптами

| Параметр | `generate_trust_management_clean_backgrounds.py` | `generate_trust_management_banners.py --backgrounds-only` |
|----------|--------------------------------------------------|----------------------------------------------------------|
| Назначение | Только чистые фоны | Универсальный (фоны или баннеры) |
| Имя файлов | `trust_clean_*.png` | `trust_bg_*.png` |
| Опции | Больше настроек для фонов | Интеграция с основным пайплайном |

## Использование для dual composition

Сгенерированные чистые фоны можно использовать в `trust_management_dual_composition.py`:

```bash
# 1. Генерируем чистые фоны
python scripts/generate_trust_management_clean_backgrounds.py --count 20 --format horizontal --output output/trust_bg/

# 2. Используем их в dual composition
python scripts/trust_management_dual_composition.py --input-dir output/trust_bg/ --format horizontal --count 10 --qr-chance 60
```

## Форматы

- `square`: 1024×1024
- `horizontal`: 1200×700
- `vertical`: 800×1200

## Сценарии

### Без людей (7)
- office_financial
- trading_desk_abstract
- portfolio_documents
- bank_vault_abstract
- charts_wall
- library_finance
- gradient_financial

### С людьми (7)
- portfolio_manager_right
- advisor_portrait_left
- manager_desk
- investor_consultation
- wealth_manager_left
- analyst_desk
- executive_portrait_right
