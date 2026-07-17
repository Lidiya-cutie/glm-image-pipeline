# Категория «Табак» — генерация баннеров

Генерация баннеров для табачной продукции, курительных принадлежностей, кальянов, вейпов и пропаганды ЗОЖ (без табака).

## Файлы категории «Табак»

Полный перечень всех файлов по категориям см. в **[TOBACCO_FILES.md](TOBACCO_FILES.md)**.

| Файл | Назначение |
|------|------------|
| `tobacco_overlay.py` | Наложение текста, пачки, логотипа, бейджа; `build_tobacco_text_bundle`, `TobaccoBannerOverlay` |
| `tobacco_composition_with_products.py` | Композиция из готовых фонов (без SDXL): фон + текст + пачка/логотип/бейдж |
| `generate_tobacco_banners.py` | SDXL-генерация: фон + текст + пачка/логотип/бейдж |
| `build_tobacco_stores_bars.py` | Сборка `tobacco_stores_bars.json` из CSV |
| `configs/tobacco_config.json` | Сценарии (102), заголовки, описания, дисклеймеры, стили, venue_badges |
| `configs/tobacco_stores_bars.json` | Магазины табака, кальян-бары (для venues) |

## Список всех сценариев (102)

### Сигареты и сигары (58 сценариев)

| Сценарий | С людьми |
|----------|----------|
| tobacco_noir_pack_ashtray_smoke | нет |
| tobacco_cigar_luxury | нет |
| tobacco_cigarette_pack_studio | нет |
| tobacco_smoke_ambient | нет |
| tobacco_cigarette_box_wood | нет |
| tobacco_noir_ashtray_solo | нет |
| tobacco_vintage_pack_retro | нет |
| tobacco_cigar_band_macro | нет |
| tobacco_smoke_silk_curtain | нет |
| tobacco_pack_shot_minimal | нет |
| tobacco_ashtray_brass_vintage | нет |
| tobacco_cigars_humidor_open | нет |
| tobacco_studio_soft_shadow | нет |
| tobacco_smoke_blue_hour | нет |
| tobacco_cigar_cut_rest | нет |
| tobacco_noir_smoke_silhouette | нет |
| tobacco_menthol_fresh_ice | нет |
| tobacco_vintage_lighter_matchbook | нет |
| tobacco_pack_fan_display | нет |
| tobacco_cigar_smoke_ring | нет |
| tobacco_luxury_gold_accents | нет |
| tobacco_ashtray_smoke_tendrils | нет |
| tobacco_studio_three_pack | нет |
| tobacco_cigar_box_open | нет |
| tobacco_noir_window_light | нет |
| tobacco_smoke_abstract_white | нет |
| tobacco_vintage_ad_poster | нет |
| tobacco_cigar_holder_silver | нет |
| tobacco_pack_reflection | нет |
| tobacco_smoke_backlit | нет |
| tobacco_ashtray_glass_modern | нет |
| tobacco_cigars_trio_wood | нет |
| tobacco_noir_single_cigarette | нет |
| tobacco_studio_split_light | нет |
| tobacco_vintage_tin_box | нет |
| tobacco_smoke_volumetric | нет |
| tobacco_cigar_glow_ember | нет |
| tobacco_pack_slate_surface | нет |
| tobacco_ashtray_ceramic_art | нет |
| tobacco_luxury_leather_desk | нет |
| tobacco_noir_rain_window | нет |
| tobacco_smoke_double_exposure | нет |
| tobacco_cigar_humidor_interior | нет |
| tobacco_studio_rim_only | нет |
| tobacco_vintage_matchbox_strike | нет |
| tobacco_pack_water_droplets | нет |
| tobacco_smoke_layered_depth | нет |
| tobacco_ashtray_bronze_vintage | нет |
| tobacco_cigars_cedar_drawer | нет |
| tobacco_noir_smoke_screen | нет |
| tobacco_luxury_velvet_box | нет |
| tobacco_studio_flat_lay | нет |
| tobacco_smoke_monochrome_art | нет |
| tobacco_cigar_cutter_detail | нет |
| tobacco_pack_concrete_industrial | нет |
| tobacco_vintage_salon_atmosphere | нет |
| tobacco_cigars_sampler_display | нет |
| tobacco_luxury_silk_background | нет |

### Кальяны (6 сценариев)

| Сценарий | С людьми |
|----------|----------|
| hookah_classic_metal_no_person | нет |
| hookah_modern_minimal_no_person | нет |
| hookah_smoke_rising_no_person | нет |
| hookah_tobacco_bowls_no_person | нет |
| hookah_friends_relaxing_with_person | да |
| hookah_couple_evening_with_person | да |

### Вейпы (4 сценария)

| Сценарий | С людьми |
|----------|----------|
| vape_device_minimal_no_person | нет |
| vape_liquids_display_no_person | нет |
| vape_cloud_artistic_no_person | нет |
| vape_person_outdoor_with_person | да |

### Курительные смеси (2 сценария)

| Сценарий | С людьми |
|----------|----------|
| smoking_mix_herbal_jars_no_person | нет |
| smoking_mix_tobacco_blend_no_person | нет |

### Пропаганда ЗОЖ (5 сценариев)

| Сценарий | С людьми |
|----------|----------|
| propaganda_fresh_air_no_person | нет |
| propaganda_sports_running_no_person | нет |
| propaganda_yoga_meditation_no_person | нет |
| propaganda_happy_family_with_person | да |
| propaganda_athlete_with_person | да |

### Современные кафе и зоны для курения (7 сценариев)

| Сценарий | С людьми |
|----------|----------|
| cafe_hookah_modern_interior_no_person | нет |
| cafe_smoking_terrace_modern_no_person | нет |
| cafe_hookah_loft_industrial_no_person | нет |
| cafe_smoking_lounge_scandinavian_no_person | нет |
| cafe_hookah_guests_with_person | да |
| cafe_terrace_smoking_zone_with_person | да |
| cafe_hookah_bar_counter_with_person | да |

### Референсные 20 типов (для фильтрации/обучения)

| № | Сценарий | Описание |
|---|----------|----------|
| 1 | ref01_cigarettes_on_pure_white | Сигареты на белом фоне, дизайн упаковки |
| 2 | ref02_hookah_with_smoke_aromatic | Кальян с дымом, фрукты/специи |
| 3 | ref03_smoking_pipe_tobacco_bowl | Курительная трубка, табак в чаше |
| 4 | ref04_tobacco_leaves_dried | Табачные листья, поле или обработка |
| 5 | ref05_rolling_paper_roll | Сигаретная бумага, рулон или листы |
| 6 | ref06_lighter_smoking_accessories | Зажигалка среди аксессуаров |
| 7 | ref07_person_holding_cigarette | Человек с сигаретой |
| 8 | ref08_hookah_set_complete | Набор для кальяна (уголь, табак, чаши, шланги) |
| 9 | ref09_cigars_closeup_brand | Сигары, форма, длина, бренд |
| 10 | ref10_tobacco_shop_interior | Табачный магазин, интерьер или вывеска |
| 11 | ref11_neon_hookah_lounge_sign | Неоновая вывеска Hookah Lounge |
| 12 | ref12_couple_smoking_hookah | Пара, курящая кальян |
| 13 | ref13_hand_holding_pipe_smoke | Трубка в руке, дым |
| 14 | ref14_tobacco_packaging_branded | Упаковка табачной продукции |
| 15 | ref15_smoking_process_drag | Процесс курения, затяжка |
| 16 | ref16_smoking_accessories_table | Аксессуары: пепельница, зажигалка, спички |
| 17 | ref17_retro_tobacco_ad_poster | Ретро-реклама табака |
| 18 | ref18_hookah_fruits_bowl | Кальян с фруктовыми добавками |
| 19 | ref19_pipe_tobacco_bowl_smoke | Трубка с табаком в чаше |
| 20 | ref20_tobacco_brand_logo | Логотип табачного бренда |

## Команды

### Список сценариев

```bash
python scripts/generate_tobacco_banners.py --list-scenarios
```

### Генерация

```bash
# Один сценарий
python scripts/generate_tobacco_banners.py --scenario tobacco_noir_pack_ashtray_smoke

# Все сценарии
python scripts/generate_tobacco_banners.py --all-scenarios --output output/tobacco_all

# Только с людьми / без людей
python scripts/generate_tobacco_banners.py --all-scenarios --with-people
python scripts/generate_tobacco_banners.py --all-scenarios --without-people

# Только пропаганда ЗОЖ
python scripts/generate_tobacco_banners.py --all-scenarios --propaganda-only --purpose propaganda

# Конкретные сценарии
python scripts/generate_tobacco_banners.py --scenarios hookah_classic_metal_no_person,ref01_cigarettes_on_pure_white

# Product type: cigarettes (пачка+логотип), venues, hookah, vape, smoking_mixes, propaganda
python scripts/generate_tobacco_banners.py --scenario hookah_smoke_rising_no_person --product-type hookah

# Свой текст
python scripts/generate_tobacco_banners.py --scenario tobacco_cigar_luxury --headline "СИГАРЫ" --description "Премиум." --disclaimer "18+. Курение вредит здоровью."

# Только фоны без текста
python scripts/generate_tobacco_banners.py --all-scenarios --backgrounds-only
```

### Композиция (без SDXL)

```bash
python scripts/tobacco_composition_with_products.py --count 5 --product-type cigarettes
python scripts/tobacco_composition_with_products.py --count 5 --product-type venues
python scripts/tobacco_composition_with_products.py --count 5 --product-type hookah
python scripts/tobacco_composition_with_products.py --count 5 --product-type propaganda
```

## Product type

| Тип | Текст | Наложение |
|-----|-------|-----------|
| cigarettes | headlines_cigarettes | Пачка + логотип из cigarette_images |
| venues | headlines_venues | Бейдж (ЛАУНДЖ, КАЛЬЯННАЯ и др.) |
| hookah | headlines_hookah | Бейдж КАЛЬЯННАЯ |
| vape | headlines_vape | Бейдж ВЕЙП-МАГАЗИН |
| smoking_mixes | headlines_smoking_mixes | Бейдж |
| propaganda | headlines_propaganda | Ничего |

## Требования

- Дисклеймер 18+, предупреждение о вреде курения
- Папка `cigarette_images/` — подпапки по маркам с пачками, `logo/` с логотипами (для product_type=cigarettes)
