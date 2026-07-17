# Использование реальных компаний в баннерах доверительного управления

## Изменения

Все скрипты теперь используют реальные данные управляющих компаний из файла `trust_management_companies.json`.

### Файл данных: `trust_management_companies.json`

Содержит 36 реальных управляющих компаний с:
- Наименованием (юрлицо)
- Сайтом
- Телефоном

### Обновлённые функции

#### `trust_management_overlay.py`
- `load_companies()` — загружает компании из JSON
- `get_random_company()` — возвращает случайную компанию
- `get_random_content(use_real_companies=True)` — использует реальные компании по умолчанию
- `format_source_info(website, phone)` — форматирует источник информации

#### `generate_trust_management_banners.py`
- По умолчанию использует реальные компании
- `--no-real-companies` — флаг для отключения (использовать шаблоны)

#### `trust_management_dual_composition.py`
- Использует реальные компании для текста
- QR-коды генерируются с сайтами реальных компаний
- `get_company_qr_url()` — возвращает URL для QR из данных компании

## Примеры использования

```bash
# Генерация с реальными компаниями (по умолчанию)
python scripts/generate_trust_management_banners.py --all-scenarios --format horizontal --count 5

# Без реальных компаний (шаблоны)
python scripts/generate_trust_management_banners.py --all-scenarios --format horizontal --count 5 --no-real-companies

# Dual composition с QR реальных компаний
python scripts/trust_management_dual_composition.py --input-dir path/to/images --format horizontal --count 20 --qr-chance 60
```

## Структура данных компании

```json
{
    "название компании": {
        "website": "https://example.ru/",
        "phone": "+7 (495) 123-45-67"
    }
}
```

## Что на баннерах

- **Наименование юрлица**: Реальное название из JSON
- **Телефон**: Реальный телефон компании
- **Источник информации**: Форматированный текст с сайтом и телефоном
- **QR-код**: Ссылка на реальный сайт компании
