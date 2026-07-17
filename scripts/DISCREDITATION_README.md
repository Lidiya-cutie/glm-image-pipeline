# Категория «Дискредитация …» — пайплайн макетов

Алгоритм как у **табака** и с тем же ядром оверлея (`TobaccoBannerOverlay`):

1. Конфиг JSON → фон (SDXL при непустом `prompt` или нейтральный фон).
2. Заголовок, описание, дисклеймер.
3. Опционально **бейдж** (`venue_badges` / `venue_badge_text`), **крафтовое имя** (`venue_name`), **часы** (овал над дисклеймером), **адрес и телефон** под дисклеймером — те же примитивы, что у табака для лаунджей/магазинов.
4. **Без** пачек и логотипов сигарет (`product_type="discreditation"` в `tobacco_overlay.py`).

Пулы текстов поддерживают обе схемы: **плоские массивы** (как в `tobacco_config`) и **`headlines.descriptions` с `categories` / `items`** (как в `folk_medicine_config`). В примере категории и пулы пустые.

## Файлы

| Файл | Аналог |
|------|--------|
| `configs/discreditation_config.example.json` | `tobacco_config.json` / образец структуры folk |
| `scripts/discreditation_overlay.py` | сборка текста + вызов `TobaccoBannerOverlay` |
| `scripts/generate_discreditation_banners.py` | `generate_tobacco_banners.py` |
| `scripts/discreditation_composition.py` | `tobacco_composition_with_products.py` (без продуктов) |
| `tobacco_overlay.py` | ветка `product_type == "discreditation"` |

## Подготовка

```bash
cp configs/discreditation_config.example.json configs/discreditation_config.json
# Заполните prompts, headlines, descriptions, disclaimers и/или сценарии — на своей стороне.
```

## Команды

```bash
# Список сценариев (пустые prompt отмечены)
python scripts/generate_discreditation_banners.py --list-scenarios

# Все placeholder-сценарии: при пустом prompt — серый фон, SDXL не грузится
python scripts/generate_discreditation_banners.py --all-scenarios --count 1 --format horizontal

# Только фоны; при непустом prompt — SDXL
python scripts/generate_discreditation_banners.py --scenario name --backgrounds-only

# Ошибка, если prompt не задан (удобно в CI)
python scripts/generate_discreditation_banners.py --all-scenarios --require-prompt

# Без SDXL: случайный пастельный фон + оверлей
python scripts/discreditation_composition.py --count 5 --format vertical
```

## Детализация промпта для SDXL (`prompt_detail_suffix`)

Строки **`prompt`** в сценариях **не переписываются** в скриптах. При генерации фона к каждому непустому prompt **дописывается** текст из корня конфига **`prompt_detail_suffix`** (материалы ткани, нашивки, свет, ракурс, качество — в духе подробного описания референса).

- Если **`prompt_detail_suffix`** отсутствует или равен `null` — используется встроенный **`DEFAULT_PROMPT_DETAIL_SUFFIX`** в `discreditation_overlay.py`.
- Если **`""`** (пустая строка) — дописок нет, в SDXL уходит только сырой `prompt` сценария.
- Запуск без дописка: `python scripts/generate_discreditation_banners.py --no-prompt-detail-suffix ...`

## Конфиг (как `tobacco_config.json`)

- **`scenarios[]`** — только визуал и метаданные: `name`, `prompt`, `has_person`, опционально `class`, `purpose`, `venue_preset_index` или `venue_preset_name` (выбор строки из `venue_presets`). Без заголовков/описаний/дисклеймеров внутри сценария.
- **`headlines`**, **`descriptions`**, **`disclaimers`** — отдельные списки строк в корне JSON (как топ-уровневые пулы в табаке). Допустимо дублировать формат народной медицины: объект с `categories` / `items` — скрипт их «сплющит».
- **`venue_badges`** — только текст бейджа; если нет пресета с полем `venue_badge_text`, при непустом списке выбирается случайная строка.
- **`venue_presets`** — массив объектов `{ "name"?, "venue_badge_text"?, "venue_name"?, "venue_address"?, "venue_hours"?, "venue_phone"? }` (аналог выборки точек из `tobacco_stores_bars.json`). Пустой массив — без заведения. Если в сценарии не задан индекс/имя пресета — случайный пресет из списка.
- **`styles`**, **`disclaimer_bg_styles`**: как в табаке.

## Оверлей

`TobaccoBannerOverlay.apply(..., product_type="discreditation")`: часы/адрес/телефон рисуются тем же кодом, что для табака; бейдж и крафтовое имя — ветка `discreditation` в `tobacco_overlay.py`.

## Манифест для разметки

При необходимости объединяйте вывод с `scripts/generate_ad_moderation_train.py` / `export_moderation_manifest_to_csv.py` (отдельный поток с расширенным `manifest.jsonl`).
