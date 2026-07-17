# Баннеры доверительного управления (ст. 28 ФЗ-38)

Скрипты для генерации рекламных баннеров в категории **«Доверительное управление ценными бумагами / активами»** с учётом требований ст. 28 ФЗ-38 «О рекламе».

## Созданные файлы

| Файл | Назначение |
|------|------------|
| `trust_management_overlay.py` | Валидатор, 15+ формулировок текста, стили |
| `generate_trust_management_banners.py` | Генерация фонов и баннеров (7 без людей + 7 с людьми) |
| `trust_management_dual_composition.py` | Композиция из 2 изображений + текст + QR (как folk_dual_composition) |

## Форматы баннеров

- **Квадратный:** 1024×1024
- **Горизонтальный:** 1200×700
- **Вертикальный:** 800×1200

## Сценарии фонов

### Без людей (7)
- office_financial, trading_desk_abstract, portfolio_documents  
- bank_vault_abstract, charts_wall, library_finance, gradient_financial  

### С людьми (7)
- portfolio_manager_right, advisor_portrait_left, manager_desk  
- investor_consultation, wealth_manager_left, analyst_desk, executive_portrait_right  

## Тексты (15+ формулировок)

Все тексты соответствуют чек-листу:
- ✅ Наименование юрлица
- ✅ Источник информации (сайт, телефон)
- ✅ Предупреждение о рисках
- ❌ Без гарантий доходности
- ❌ Без обещаний стабильности

## Примеры запуска

```bash
# Генерация одного баннера
python scripts/generate_trust_management_banners.py --scenario office_financial

# Все сценарии, горизонтальный формат
python scripts/generate_trust_management_banners.py --all-scenarios --format horizontal --count 5

# Только с людьми
python scripts/generate_trust_management_banners.py --with-people --output output/trust_mgmt_people

# Dual composition (из папки с фонами) + текст + QR
python scripts/trust_management_dual_composition.py --input-dir path/to/backgrounds --output output/trust_dual --format horizontal --count 20 --qr-chance 60 --qr-url https://yoursite.ru/trust
```

## Валидация текста

```bash
python scripts/trust_management_overlay.py --validate "Гарантируем 20% годовых"
# → Нарушения: Запрещено: 'гарантируем 20%'
```
