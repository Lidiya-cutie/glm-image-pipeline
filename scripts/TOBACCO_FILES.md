# Файлы категории «Табак» — полный перечень по категориям

Все файлы пайплайна, относящиеся к генерации баннеров табачной продукции, кальянов, вейпов и пропаганды ЗОЖ.

---

## 1. Скрипты генерации

| Файл | Путь | Назначение |
|------|------|------------|
| **generate_tobacco_banners.py** | `scripts/generate_tobacco_banners.py` | Главный генератор: SDXL-фоны + текст + пачка/логотип/бейдж. Поддержка 102 сценариев, форматов (square, horizontal, vertical), product types (cigarettes, venues, hookah, vape, smoking_mixes, propaganda). |
| **tobacco_composition_with_products.py** | `scripts/tobacco_composition_with_products.py` | Композиция без SDXL: готовые фоны (solid/pack-based) + текст + пачка/логотип/бейдж. Без генерации изображений. |
| **build_tobacco_stores_bars.py** | `scripts/build_tobacco_stores_bars.py` | Сборка `tobacco_stores_bars.json` из CSV (магазины, кальянные, вейп-шопы). |

---

## 2. Оверлей / отрисовка

| Файл | Путь | Назначение |
|------|------|------------|
| **tobacco_overlay.py** | `scripts/tobacco_overlay.py` | Модуль наложения: `TobaccoBannerOverlay`, `build_tobacco_text_bundle`, `get_tobacco_brands_and_packs`, `get_logo_for_brand`, `get_random_tobacco_venue`, `get_random_tobacco_venue_name`. Рисует заголовок, описание, дисклеймер, бейдж заведения, пачку/логотип из cigarette_images. |

---

## 3. Конфиги

| Файл | Путь | Назначение |
|------|------|------------|
| **tobacco_config.json** | `configs/tobacco_config.json` | Главный конфиг: 102 сценария, промпты, заголовки, описания, дисклеймеры, venue_badges, стили. |
| **tobacco_stores_bars.json** | `configs/tobacco_stores_bars.json` | Данные заведений: название, адрес, часы, телефон, категория (магазин табака, кальянная, вейп-шоп). |

---

## 4. Данные и ресурсы

| Ресурс | Путь | Назначение |
|--------|------|------------|
| **cigarette_images/** | `cigarette_images/` | Пачки сигарет и логотипы. Структура: подпапки по брендам с pack-изображениями, `logo/` с логотипами. Используется при `product_type=cigarettes`. |
| **craft fonts** | `fonts/craft/` | Шрифты для заголовков, venue-названий, дисклеймеров. |

---

## 5. Пайплайн (общий, используется табаком)

| Файл | Путь | Назначение |
|------|------|------------|
| **simple_pipeline.py** | `pipeline/inference/simple_pipeline.py` | SDXL-пайплайн: `SimpleImagePipeline` для генерации фонов. Используется `generate_tobacco_banners.py`. Общий для всех категорий. |

---

## 6. Документация

| Файл | Путь | Назначение |
|------|------|------------|
| **TOBACCO_README.md** | `scripts/TOBACCO_README.md` | Документация по сценариям, командам, product type. |
| **TOBACCO_FILES.md** | `scripts/TOBACCO_FILES.md` | Перечень файлов категории «Табак» по категориям (этот файл). |

---

## Сводная таблица

| Категория | Кол-во | Файлы |
|-----------|--------|-------|
| Скрипты генерации | 3 | generate_tobacco_banners, tobacco_composition_with_products, build_tobacco_stores_bars |
| Оверлей | 1 | tobacco_overlay |
| Конфиги | 2 | tobacco_config.json, tobacco_stores_bars.json |
| Данные | 2 | cigarette_images/, fonts/craft/ |
| Пайплайн | 1 | simple_pipeline.py (общий) |
| Документация | 2 | TOBACCO_README.md, TOBACCO_FILES.md |

**Итого: 11 уникальных сущностей** (без учёта содержимого output).

---

## Зависимости между файлами

```
generate_tobacco_banners.py
  ├── tobacco_overlay.py
  ├── tobacco_config.json
  ├── tobacco_stores_bars.json (через tobacco_overlay)
  ├── cigarette_images/ (через tobacco_overlay)
  ├── fonts/craft/ (через tobacco_overlay)
  └── pipeline/inference/simple_pipeline.py

tobacco_composition_with_products.py
  ├── tobacco_overlay.py
  ├── tobacco_config.json
  ├── tobacco_stores_bars.json (через tobacco_overlay)
  ├── cigarette_images/ (через tobacco_overlay)
  └── fonts/craft/ (через tobacco_overlay)

build_tobacco_stores_bars.py
  └── configs/tobacco_stores_bars.json (создаёт/перезаписывает)
```
